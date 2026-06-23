import xml.etree.ElementTree as ET
import logging
from collections import deque, defaultdict

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Layout constants
# ---------------------------------------------------------------------------
_BPMN_EVENT_W, _BPMN_EVENT_H = 36, 36
_BPMN_TASK_W, _BPMN_TASK_H = 100, 80
_BPMN_GATEWAY_W, _BPMN_GATEWAY_H = 50, 50

_PNML_PLACE_W, _PNML_PLACE_H = 50, 50
_PNML_TRANS_W, _PNML_TRANS_H = 50, 30

# Approximate glyph width (px) of WoPeD's small label font (~11px). Labels are
# drawn centred BELOW the node, so the layout must reserve at least the label's
# width per column or adjacent labels overlap. Used to widen columns to fit the
# text instead of the node box alone.
_LABEL_CHAR_PX = 7

# Maps a model event "type" to its BPMN element tag; anything unrecognised
# becomes a generic intermediateCatchEvent.
_EVENT_TYPE_MAP = {
    "Start": "startEvent",
    "startEvent": "startEvent",
    "End": "endEvent",
    "endEvent": "endEvent",
}

# BPMN namespaces, registered once so ET.tostring emits the expected prefixes.
_NS = {
    "bpmn": "http://www.omg.org/spec/BPMN/20100524/MODEL",
    "bpmndi": "http://www.omg.org/spec/BPMN/20100524/DI",
    "di": "http://www.omg.org/spec/DD/20100524/DI",
    "dc": "http://www.omg.org/spec/DD/20100524/DC",
    "xsi": "http://www.w3.org/2001/XMLSchema-instance",
}
ET.register_namespace("", _NS["bpmn"])
ET.register_namespace("bpmndi", _NS["bpmndi"])
ET.register_namespace("di", _NS["di"])
ET.register_namespace("dc", _NS["dc"])
ET.register_namespace("xsi", _NS["xsi"])


def _sugiyama_layout(
    elements_by_id, flows, h_gap=80, v_gap=50, x_offset=50, y_offset=50
):
    """Compute a layered (Sugiyama-style) layout plus orthogonal edge routing.

    The layout runs in the classic stages, each of which exists to keep edges
    from crossing nodes or stacking on top of one another:

    1.  **Layering** – a longest-path assignment over the DAG of *flows* puts
        every node in a column (layer). Cyclic or disconnected nodes are
        appended to trailing layers so they are still placed.
    2.  **Dummy nodes** – every forward edge that spans more than one layer is
        split into unit-length hops by inserting a routing-only *dummy* node in
        each layer it passes over. The dummy claims its own slot in that layer,
        which reserves a clear lane for the edge so it never runs across the
        nodes it skips.
    3.  **Ordering** – a few barycenter sweeps reorder nodes within each layer to
        reduce edge crossings.
    4.  **Coordinates** – columns are placed left to right; each column is
        stacked top to bottom and centred on a common midline so the layers stay
        vertically aligned.

    Args:
        elements_by_id: ``{id: {"w": int, "h": int}}`` – node sizes in pixels.
        flows: list of ``{"source": str, "target": str}`` dicts.
        h_gap: horizontal gap between adjacent layers (pixels).
        v_gap: vertical gap between nodes within a layer (pixels).
        x_offset: left margin (pixels).
        y_offset: top margin (pixels).

    Returns:
        ``(positions, ctx)`` where *positions* is
        ``{real_id: {"x", "y", "w", "h"}}`` (top-left corners, dummy nodes
        excluded) and *ctx* carries the routing metadata
        (``centers``, per-flow ``chains``, ``col_x``/``col_w`` column geometry,
        ``node_layer`` and the ``is_dummy`` set) that :func:`_add_diagram` turns
        into waypoints.
    """
    empty_ctx = {
        "centers": {},
        "chains": [],
        "col_x": {},
        "col_w": {},
        "node_layer": {},
        "is_dummy": set(),
    }
    real_ids = list(elements_by_id.keys())
    if not real_ids:
        return {}, empty_ctx

    # Build adjacency lists over the real nodes only.
    successors: dict[str, list[str]] = {nid: [] for nid in real_ids}
    predecessors: dict[str, list[str]] = {nid: [] for nid in real_ids}
    for flow in flows:
        src, tgt = flow.get("source", ""), flow.get("target", "")
        if src in successors and tgt in predecessors:
            successors[src].append(tgt)
            predecessors[tgt].append(src)

    # --- 1. Layering ---
    # Break cycles first: a depth-first traversal classifies edges, and any edge
    # pointing back to a node still on the DFS stack is a *back edge*. Removing
    # those yields a DAG that lays out cleanly left-to-right; the back edges are
    # drawn as loops by _add_diagram. Without this, every node on a rework loop
    # (e.g. "reopen claim -> reassess") never reaches in-degree zero and used to
    # be scattered into its own trailing column, wrecking the whole diagram.
    _WHITE, _GRAY, _BLACK = 0, 1, 2
    color = {nid: _WHITE for nid in real_ids}
    back_edges: set[tuple[str, str]] = set()
    for root_node in real_ids:
        if color[root_node] != _WHITE:
            continue
        color[root_node] = _GRAY
        dfs_stack = [(root_node, iter(successors[root_node]))]
        while dfs_stack:
            node, succ_iter = dfs_stack[-1]
            for nxt in succ_iter:
                if color[nxt] == _GRAY:
                    back_edges.add((node, nxt))
                elif color[nxt] == _WHITE:
                    color[nxt] = _GRAY
                    dfs_stack.append((nxt, iter(successors[nxt])))
                    break
            else:
                color[node] = _BLACK
                dfs_stack.pop()

    # Longest-path layering (Kahn) over the acyclic skeleton. Relaxing each edge
    # only after its source is dequeued keeps the longest-path layers correct.
    acyclic_succ = {
        nid: [t for t in successors[nid] if (nid, t) not in back_edges]
        for nid in real_ids
    }
    indeg = {nid: 0 for nid in real_ids}
    for nid in real_ids:
        for tgt in acyclic_succ[nid]:
            indeg[tgt] += 1
    topo_queue: deque[str] = deque(nid for nid in real_ids if indeg[nid] == 0)
    indeg_work = dict(indeg)
    node_layer: dict[str, int] = {nid: 0 for nid in real_ids}
    while topo_queue:
        node = topo_queue.popleft()
        for nxt in acyclic_succ[node]:
            node_layer[nxt] = max(node_layer[nxt], node_layer[node] + 1)
            indeg_work[nxt] -= 1
            if indeg_work[nxt] == 0:
                topo_queue.append(nxt)

    # --- 2. Dummy nodes for forward edges that span more than one layer ---
    node_w = {nid: elements_by_id[nid]["w"] for nid in real_ids}
    node_h = {nid: elements_by_id[nid]["h"] for nid in real_ids}
    is_dummy: set[str] = set()
    chains: list[list[str]] = []  # one node chain per flow, index-aligned
    dummy_seq = 0
    for flow in flows:
        src, tgt = flow.get("source", ""), flow.get("target", "")
        if src not in node_layer or tgt not in node_layer:
            # Missing endpoint: keep a direct chain; the absent shape surfaces
            # as a KeyError in _add_diagram (mapped to invalid_model upstream).
            chains.append([src, tgt])
            continue
        span = node_layer[tgt] - node_layer[src]
        if span >= 2:
            chain = [src]
            for layer in range(node_layer[src] + 1, node_layer[tgt]):
                dummy = f"__dummy_{dummy_seq}"
                dummy_seq += 1
                node_w[dummy] = 0
                node_h[dummy] = 0
                node_layer[dummy] = layer
                is_dummy.add(dummy)
                chain.append(dummy)
            chain.append(tgt)
            chains.append(chain)
        else:
            chains.append([src, tgt])

    # --- 3. Ordering within layers (barycenter sweeps) ---
    layers: dict[int, list[str]] = {}
    for nid, lyr in node_layer.items():
        layers.setdefault(lyr, []).append(nid)
    # Deterministic start order: real nodes by id, dummies after.
    for lyr in layers:
        layers[lyr].sort(key=lambda n: (n in is_dummy, n))

    up_adj: dict[str, list[str]] = {nid: [] for nid in node_layer}
    down_adj: dict[str, list[str]] = {nid: [] for nid in node_layer}
    for chain in chains:
        for a, b in zip(chain, chain[1:]):
            if a in node_layer and b in node_layer and node_layer[b] == node_layer[a] + 1:
                down_adj[a].append(b)
                up_adj[b].append(a)

    max_layer = max(layers)
    rank: dict[str, int] = {}
    for lyr in layers:
        for i, nid in enumerate(layers[lyr]):
            rank[nid] = i

    def _sweep(layer_indices, neighbours):
        for lyr in layer_indices:
            nodes = layers.get(lyr)
            if not nodes:
                continue
            scored = []
            for nid in nodes:
                ne = neighbours[nid]
                bary = sum(rank[x] for x in ne) / len(ne) if ne else rank[nid]
                scored.append((bary, rank[nid], nid))
            scored.sort()
            layers[lyr] = [nid for _, _, nid in scored]
            for i, nid in enumerate(layers[lyr]):
                rank[nid] = i

    for _ in range(4):
        _sweep(range(1, max_layer + 1), up_adj)  # top-down using upper neighbours
        _sweep(range(max_layer - 1, -1, -1), down_adj)  # bottom-up using lower

    # --- 4. Coordinate assignment ---
    sorted_layers = sorted(layers)
    col_w = {lyr: max((node_w[n] for n in layers[lyr]), default=0) for lyr in sorted_layers}
    col_x: dict[int, int] = {}
    x = x_offset
    for lyr in sorted_layers:
        col_x[lyr] = x
        x += col_w[lyr] + h_gap

    def _layer_height(lyr):
        nodes = layers[lyr]
        if not nodes:
            return 0
        return sum(node_h[n] for n in nodes) + (len(nodes) - 1) * v_gap

    max_height = max((_layer_height(lyr) for lyr in sorted_layers), default=0)
    center_y = y_offset + max_height / 2

    positions: dict[str, dict] = {}
    centers: dict[str, tuple] = {}
    for lyr in sorted_layers:
        y = center_y - _layer_height(lyr) / 2
        for nid in layers[lyr]:
            w, h = node_w[nid], node_h[nid]
            elem_x = col_x[lyr] + (col_w[lyr] - w) // 2
            centers[nid] = (elem_x + w / 2, y + h / 2)
            if nid not in is_dummy:
                positions[nid] = {"x": int(elem_x), "y": int(round(y)), "w": w, "h": h}
            y += h + v_gap

    ctx = {
        "centers": centers,
        "chains": chains,
        "col_x": col_x,
        "col_w": col_w,
        "node_layer": node_layer,
        "is_dummy": is_dummy,
    }
    return positions, ctx


def _layered_layout(
    elements_by_id, flows, h_gap=80, v_gap=50, x_offset=50, y_offset=50
):
    """Return top-left ``{id: {x, y, w, h}}`` positions for *elements_by_id*.

    Thin wrapper over :func:`_sugiyama_layout` for callers (the PNML path) that
    only need node coordinates and route their own edges.
    """
    positions, _ = _sugiyama_layout(
        elements_by_id, flows, h_gap, v_gap, x_offset, y_offset
    )
    return positions


def _label_width(elem, ns_prefix):
    """Estimate the rendered width (px) of a node's label from ``<name><text>``.

    WoPeD draws the name centred below the node, so a long name needs a wider
    column than the node box to keep it from overlapping its neighbours.
    Returns 0 for unnamed nodes (e.g. silent places).
    """
    name = elem.find(f"{ns_prefix}name")
    text = name.find(f"{ns_prefix}text") if name is not None else None
    if text is None or not text.text:
        return 0
    return len(text.text.strip()) * _LABEL_CHAR_PX


def assign_pnml_coordinates(pnml_xml):
    """Parse a PNML XML string and assign proper layout coordinates to all
    places and transitions.

    Uses the same layered layout algorithm as the BPMN generator.  In PNML,
    ``<graphics><position>`` holds *centre* coordinates, so positions returned
    by ``_layered_layout`` (top-left) are shifted by half the element size.

    If *pnml_xml* is not valid XML the original string is returned unchanged.

    Args:
        pnml_xml: PNML XML string (with or without ``<?xml ...?>`` declaration).

    Returns:
        Updated PNML XML string.
    """
    if not pnml_xml or not isinstance(pnml_xml, str):
        return pnml_xml

    try:
        root = ET.fromstring(pnml_xml)
    except ET.ParseError:
        logger.warning("assign_pnml_coordinates: not valid XML – layout skipped")
        return pnml_xml

    # Detect Clark-notation namespace prefix, e.g. '{http://www.pnml.org/...}'.
    raw_tag = root.tag
    ns_prefix = (
        "{" + raw_tag[1 : raw_tag.index("}")] + "}" if raw_tag.startswith("{") else ""
    )

    # Register the namespace so ET.tostring() preserves the default namespace.
    if ns_prefix:
        ET.register_namespace("", ns_prefix[1:-1])

    # Collect all places and transitions from the entire tree (handles
    # nested <pnml><net><page>... hierarchies).
    elements_by_id: dict[str, dict] = {}
    elem_xml_map: dict[str, ET.Element] = {}

    for place in root.iter(f"{ns_prefix}place"):
        pid = place.get("id")
        if pid:
            w = max(_PNML_PLACE_W, _label_width(place, ns_prefix))
            elements_by_id[pid] = {"w": w, "h": _PNML_PLACE_H}
            elem_xml_map[pid] = place

    for trans in root.iter(f"{ns_prefix}transition"):
        tid = trans.get("id")
        if tid:
            w = max(_PNML_TRANS_W, _label_width(trans, ns_prefix))
            elements_by_id[tid] = {"w": w, "h": _PNML_TRANS_H}
            elem_xml_map[tid] = trans

    if not elements_by_id:
        return pnml_xml  # nothing to lay out

    flows = [
        {"source": arc.get("source", ""), "target": arc.get("target", "")}
        for arc in root.iter(f"{ns_prefix}arc")
        if arc.get("source") and arc.get("target")
    ]

    positions = _layered_layout(
        elements_by_id, flows, h_gap=80, v_gap=50, x_offset=100, y_offset=100
    )

    for nid, pos in positions.items():
        elem = elem_xml_map.get(nid)
        if elem is None:
            continue

        # PNML <position> stores centre coordinates.
        cx = pos["x"] + pos["w"] // 2
        cy = pos["y"] + pos["h"] // 2

        graphics = elem.find(f"{ns_prefix}graphics")
        if graphics is None:
            graphics = ET.SubElement(elem, f"{ns_prefix}graphics")

        position_el = graphics.find(f"{ns_prefix}position")
        if position_el is None:
            position_el = ET.SubElement(graphics, f"{ns_prefix}position")
        position_el.set("x", str(cx))
        position_el.set("y", str(cy))

        # Drop the node name's <graphics>: the transformer stamps a constant
        # name offset (e.g. (20,20)) on every node, which the WoPeD fat client
        # reads as the label's ABSOLUTE canvas position -> all labels collapse
        # onto that one point. We carry no real per-label position, so removing
        # it lets each client place the label by its own native rule (the fat
        # client centres it just below the node). Clients that ignore the offset
        # are unaffected. Anonymous nodes (silent/start/end places, operator
        # helper transitions) carry no <name>, so WoPeD falls back to showing
        # the raw id ("SILENTFROMxTOy", "startEvent1", ...) as a label -- long,
        # ugly and overlapping. Give them an empty <name> so they render
        # unlabelled instead.
        name_el = elem.find(f"{ns_prefix}name")
        if name_el is None:
            name_el = ET.Element(f"{ns_prefix}name")
            ET.SubElement(name_el, f"{ns_prefix}text").text = ""
            elem.insert(0, name_el)
        else:
            name_graphics = name_el.find(f"{ns_prefix}graphics")
            if name_graphics is not None:
                name_el.remove(name_graphics)

        # The transformer stamps the same (20,20) default on the WoPeD
        # <trigger>/<transitionResource> it attaches to every UserTask, and the
        # fat client reads those as ABSOLUTE positions too -> they stack just
        # like the names did. The <graphics> cannot simply be dropped: the fat
        # client dereferences trigger.getGraphics().getPosition() without a
        # null-check (NPE). So an empty resource marker (no role/orga) is pure
        # noise and is removed outright; a real trigger/resource is repositioned
        # next to its transition (WoPeD's own offsets) so it no longer collapses.
        for ts in elem.findall(f"{ns_prefix}toolspecific"):
            trigger = ts.find(f"{ns_prefix}trigger")
            resource = ts.find(f"{ns_prefix}transitionResource")
            resource_empty = resource is not None and not (
                resource.get("roleName") or resource.get("organizationalUnitName")
            )
            if trigger is not None and trigger.get("type") == "200" and resource_empty:
                ts.remove(trigger)
                ts.remove(resource)
            else:
                for sub, dx, dy in ((trigger, 10, -22), (resource, -5, -45)):
                    if sub is None:
                        continue
                    sub_graphics = sub.find(f"{ns_prefix}graphics")
                    if sub_graphics is None:
                        continue
                    sub_pos = sub_graphics.find(f"{ns_prefix}position")
                    if sub_pos is None:
                        sub_pos = ET.SubElement(sub_graphics, f"{ns_prefix}position")
                    sub_pos.set("x", str(cx + dx))
                    sub_pos.set("y", str(cy + dy))
            # A <toolspecific> left with only the transformer's default time
            # block (no operator/trigger/resource/subprocess) carries no
            # information -- e.g. a UserTask whose empty resource marker was just
            # removed. Drop it so plain transitions stay clean.
            if not any(
                ts.find(f"{ns_prefix}{tag}") is not None
                for tag in ("operator", "trigger", "transitionResource", "subprocess")
            ):
                elem.remove(ts)

    # Strip empty id="" attributes: the transformer's pydantic-xml models give
    # every element a default empty id, so <name>/<toolspecific>/<offset>/...
    # carry a meaningless id="". Real node/arc ids are never empty.
    for el in root.iter():
        if el.get("id") == "":
            del el.attrib["id"]

    ET.indent(ET.ElementTree(root), space="  ", level=0)
    return ET.tostring(root, encoding="unicode")


def _build_semantic_process(model):
    """Build the semantic BPMN ``<definitions>``/``<process>`` tree.

    Translates each element's type into its BPMN tag and adds every event,
    task, gateway and sequence flow. No diagram geometry is produced here.
    """
    definitions = ET.Element(
        f"{{{_NS['bpmn']}}}definitions",
        attrib={
            f"{{{_NS['xsi']}}}schemaLocation": "http://www.omg.org/spec/BPMN/20100524/MODEL https://www.omg.org/spec/BPMN/20100501/BPMN20.xsd",
            "targetNamespace": "http://example.bpmn.com/schema/bpmn",
        },
    )
    process = ET.SubElement(
        definitions,
        f"{{{_NS['bpmn']}}}process",
        attrib={"id": "Process_1", "isExecutable": "false"},
    )

    semantic_elements = {}

    for event in model["events"]:
        event_type = _EVENT_TYPE_MAP.get(event["type"], "intermediateCatchEvent")
        semantic_elements[event["id"]] = ET.SubElement(
            process,
            f"{{{_NS['bpmn']}}}{event_type}",
            id=event["id"],
            name=event["name"],
        )

    for task in model["tasks"]:
        # Convert task type to camelCase (e.g., UserTask -> userTask).
        task_type = task["type"][0].lower() + task["type"][1:]
        semantic_elements[task["id"]] = ET.SubElement(
            process, f"{{{_NS['bpmn']}}}{task_type}", id=task["id"], name=task["name"]
        )

    for gateway in model["gateways"]:
        gateway_type = gateway["type"][0].lower() + gateway["type"][1:]
        semantic_elements[gateway["id"]] = ET.SubElement(
            process,
            f"{{{_NS['bpmn']}}}{gateway_type}",
            id=gateway["id"],
            name=gateway["name"],
        )

    for flow in model["flows"]:
        source = semantic_elements[flow["source"]]
        target = semantic_elements[flow["target"]]
        # These per-node <incoming>/<outgoing> tags look redundant with the
        # sequenceFlow's source/target below, but the model-transformer needs
        # them: its get_in_degree/get_out_degree read the node tags, not the
        # edges. Without them it does not error -- it silently builds a wrong
        # net (gateways look degree-0 and get pruned). Do not remove.
        ET.SubElement(source, f"{{{_NS['bpmn']}}}outgoing").text = flow["id"]
        ET.SubElement(target, f"{{{_NS['bpmn']}}}incoming").text = flow["id"]
        ET.SubElement(
            process,
            f"{{{_NS['bpmn']}}}sequenceFlow",
            id=flow["id"],
            sourceRef=flow["source"],
            targetRef=flow["target"],
        )

    return definitions


def _loop_waypoints(src, tgt, lane_y):
    """Route a back-edge / same-layer edge as a U through the *lane_y* corridor.

    Such edges point against the left-to-right flow, so a straight orthogonal
    route would cut back across the columns. Dropping into a dedicated lane
    beneath the diagram keeps them clear of every shape and forward edge; the
    caller picks a distinct *lane_y* per loop so multiple loops do not overlap.
    """
    sx = src["x"] + src["w"]
    sy = src["y"] + src["h"] // 2
    tx = tgt["x"]
    ty = tgt["y"] + tgt["h"] // 2
    margin = 30
    return [
        (sx, sy),
        (sx + margin, sy),
        (sx + margin, lane_y),
        (tx - margin, lane_y),
        (tx - margin, ty),
        (tx, ty),
    ]


def _add_diagram(definitions, model):
    """Add the BPMN diagram interchange (layout + shapes + edges).

    Sizes every node, computes a layered layout, then emits a BPMNShape per node
    and a BPMNEdge per flow. Edges are routed orthogonally: vertical segments
    ("risers") live in the gaps between columns, never inside one, and each riser
    in a gap gets its own channel so arrows do not run on top of one another.
    Edges that skip layers are threaded through reserved dummy lanes (see
    :func:`_sugiyama_layout`) so they do not cross the nodes in between.
    ``verify`` upstream guarantees every node and flow endpoint exists, so
    positions are looked up directly.
    """
    bpmn_di = ET.SubElement(
        definitions, f"{{{_NS['bpmndi']}}}BPMNDiagram", attrib={"id": "BPMNDiagram_1"}
    )
    bpmn_plane = ET.SubElement(
        bpmn_di,
        f"{{{_NS['bpmndi']}}}BPMNPlane",
        attrib={"id": "BPMNPlane_1", "bpmnElement": "Process_1"},
    )

    sizes: dict[str, dict] = {}
    for event in model["events"]:
        sizes[event["id"]] = {"w": _BPMN_EVENT_W, "h": _BPMN_EVENT_H}
    for task in model["tasks"]:
        sizes[task["id"]] = {"w": _BPMN_TASK_W, "h": _BPMN_TASK_H}
    for gateway in model["gateways"]:
        sizes[gateway["id"]] = {"w": _BPMN_GATEWAY_W, "h": _BPMN_GATEWAY_H}

    positions, ctx = _sugiyama_layout(
        sizes, model["flows"], h_gap=180, v_gap=90, x_offset=50, y_offset=50
    )
    centers = ctx["centers"]
    chains = ctx["chains"]
    col_x = ctx["col_x"]
    col_w = ctx["col_w"]
    node_layer = ctx["node_layer"]
    is_dummy = ctx["is_dummy"]

    for element in model["tasks"] + model["events"] + model["gateways"]:
        bpmn_shape = ET.SubElement(
            bpmn_plane,
            f"{{{_NS['bpmndi']}}}BPMNShape",
            attrib={"id": f"{element['id']}_di", "bpmnElement": element["id"]},
        )
        pos = positions[element["id"]]
        ET.SubElement(
            bpmn_shape,
            f"{{{_NS['dc']}}}Bounds",
            attrib={
                "x": str(pos["x"]),
                "y": str(pos["y"]),
                "width": str(pos["w"]),
                "height": str(pos["h"]),
            },
        )

    if not model["flows"]:
        return

    # Edge geometry helpers: a real node connects at its right/left border, a
    # routing dummy is a single point at its centre.
    def _exit_x(nid):
        return centers[nid][0] if nid in is_dummy else positions[nid]["x"] + positions[nid]["w"]

    def _entry_x(nid):
        return centers[nid][0] if nid in is_dummy else positions[nid]["x"]

    def _is_regular(chain):
        """True when *chain* is a forward run of adjacent-layer hops."""
        if not chain or len(chain) < 2:
            return False
        for a, b in zip(chain, chain[1:]):
            if a not in node_layer or b not in node_layer:
                return False
            if node_layer[b] != node_layer[a] + 1:
                return False
        return True

    # Pass 1: gather every hop needing a vertical riser, grouped by the gap it
    # crosses (keyed by the hop's source layer) so each gap can hand out its own
    # channels.
    hops_by_flow: dict[int, list] = {}
    risers_by_gap: dict[int, list] = defaultdict(list)
    for idx, flow in enumerate(model["flows"]):
        chain = chains[idx]
        if not _is_regular(chain):
            hops_by_flow[idx] = None
            continue
        hop_list = []
        for a, b in zip(chain, chain[1:]):
            hop = {"a": a, "b": b, "layer": node_layer[a],
                   "y1": centers[a][1], "y2": centers[b][1], "channel": None}
            hop_list.append(hop)
            if abs(hop["y1"] - hop["y2"]) >= 1:
                risers_by_gap[node_layer[a]].append(hop)
        hops_by_flow[idx] = hop_list

    for lyr, hops in risers_by_gap.items():
        gap_lo = col_x[lyr] + col_w[lyr]
        gap_hi = col_x[lyr + 1]
        # Bundle hops that should bend together: edges sharing a target (a join)
        # or a source (a split) collapse onto one shared channel, so they turn at
        # the same x and meet at a single point instead of stair-stepping. Other
        # hops each get their own channel.
        out_count: dict[str, int] = defaultdict(int)
        in_count: dict[str, int] = defaultdict(int)
        for hop in hops:
            out_count[hop["a"]] += 1
            in_count[hop["b"]] += 1
        bundles: dict[tuple, list] = {}
        for hop in hops:
            if in_count[hop["b"]] > 1:
                key = ("in", hop["b"])
            elif out_count[hop["a"]] > 1:
                key = ("out", hop["a"])
            else:
                key = ("single", id(hop))
            bundles.setdefault(key, []).append(hop)
        # Lay the channels out left-to-right: splits near their source, joins near
        # their target, singletons in between; break ties by mean height.
        kind_rank = {"out": 0, "single": 1, "in": 2}

        def _bundle_key(key):
            ys = [(h["y1"] + h["y2"]) / 2 for h in bundles[key]]
            return (kind_rank[key[0]], sum(ys) / len(ys))

        ordered = sorted(bundles, key=_bundle_key)
        count = len(ordered)
        for i, key in enumerate(ordered):
            channel = gap_lo + (i + 1) * (gap_hi - gap_lo) / (count + 1)
            for hop in bundles[key]:
                hop["channel"] = channel

    bottom_y = max((p["y"] + p["h"] for p in positions.values()), default=0)

    # Give every loop/back edge its own horizontal lane beneath the diagram so
    # they never share a corridor. Narrower loops take the shallower lanes, so
    # wider loops nest cleanly underneath them.
    def _loop_span(idx):
        src, tgt = positions[model["flows"][idx]["source"]], positions[model["flows"][idx]["target"]]
        return abs((src["x"] + src["w"]) - tgt["x"])

    loop_indices = sorted(
        (i for i, hops in hops_by_flow.items() if hops is None), key=_loop_span
    )
    loop_lane = {idx: bottom_y + 50 + k * 45 for k, idx in enumerate(loop_indices)}

    # Pass 2: emit each edge as a de-duplicated orthogonal polyline.
    for idx, flow in enumerate(model["flows"]):
        bpmn_edge = ET.SubElement(
            bpmn_plane,
            f"{{{_NS['bpmndi']}}}BPMNEdge",
            attrib={"id": f"{flow['id']}_di", "bpmnElement": flow["id"]},
        )

        hop_list = hops_by_flow[idx]
        if hop_list is None:
            points = _loop_waypoints(
                positions[flow["source"]], positions[flow["target"]], loop_lane[idx]
            )
        else:
            chain = chains[idx]
            points = [(_exit_x(chain[0]), centers[chain[0]][1])]
            for hop in hop_list:
                target_pt = (_entry_x(hop["b"]), hop["y2"])
                if abs(hop["y1"] - hop["y2"]) < 1:
                    points.append(target_pt)
                else:
                    channel = hop["channel"]
                    points.append((channel, hop["y1"]))
                    points.append((channel, hop["y2"]))
                    points.append(target_pt)

        prev = None
        for px, py in points:
            point = (str(int(round(px))), str(int(round(py))))
            if point == prev:
                continue
            ET.SubElement(
                bpmn_edge,
                f"{{{_NS['di']}}}waypoint",
                attrib={"x": point[0], "y": point[1]},
            )
            prev = point


def json_to_bpmn(model, include_layout=True):
    """Convert a validated logical process model into BPMN 2.0 XML.

    Builds the semantic process and serializes it. When ``include_layout`` is
    true it also draws the diagram (shapes and waypoints). The PNML path passes
    ``include_layout=False``: the transformer ignores BPMN layout and we lay the
    PNML out separately, so computing a BPMN layout there would be wasted work.
    """
    logger.info(
        "Converting model to BPMN",
        extra={k: len(model[k]) for k in ("events", "tasks", "gateways", "flows")},
    )
    definitions = _build_semantic_process(model)
    if include_layout:
        _add_diagram(definitions, model)

    tree = ET.ElementTree(definitions)
    ET.indent(tree, space="  ", level=0)
    return ET.tostring(definitions, encoding="utf-8", xml_declaration=True).decode(
        "utf-8"
    )
