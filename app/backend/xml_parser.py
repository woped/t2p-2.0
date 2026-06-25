import xml.etree.ElementTree as ET
import logging
import re
from collections import deque

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Layout constants
# ---------------------------------------------------------------------------
_BPMN_EVENT_W, _BPMN_EVENT_H = 36, 36
_BPMN_TASK_W, _BPMN_TASK_H = 100, 80
_BPMN_GATEWAY_W, _BPMN_GATEWAY_H = 50, 50

_PNML_PLACE_W, _PNML_PLACE_H = 50, 50
_PNML_TRANS_W, _PNML_TRANS_H = 50, 30

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


_TASK_PREFIX_RE = re.compile(r"^\[(?:UserTask|ServiceTask)\]\s*", re.IGNORECASE)
_WS_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^a-z0-9\-\s]")


class PnmlStructureError(ValueError):
    """A PNML net violates structural connectivity constraints.

    Raised when a transition lacks inbound or outbound arcs after the
    BPMN-to-PNML transformation.  Subclasses ``ValueError`` so existing
    ``ValueError`` handlers keep catching it.
    """


def repair_pnml_connectivity_from_bpmn(pnml_xml, bpmn_xml):
    """Repair PNML transition connectivity using BPMN sequence-flow intent.

    The transformer occasionally returns a PNML where one or more transitions
    are missing inbound or outbound arcs. This function compares the PNML graph
    against the original BPMN sequence flows and injects missing place/arc
    structures so each BPMN edge is representable in PNML.

    Repair strategy:
    - For BPMN flow A -> B where both A and B exist as PNML transitions,
      ensure a PNML relay A -> place -> B exists.
    - For BPMN flow A -> X where only A is a PNML transition,
      ensure at least one outbound A -> place anchor exists for that BPMN edge.
    - For BPMN flow X -> B where only B is a PNML transition,
      ensure at least one inbound place -> B anchor exists for that BPMN edge.

    Args:
        pnml_xml: PNML XML string to repair.
        bpmn_xml: Source BPMN XML string to infer expected connectivity.

    Returns:
        Repaired PNML XML string. If parsing fails, returns the input PNML.
    """
    if not isinstance(pnml_xml, str) or not pnml_xml:
        return pnml_xml
    if not isinstance(bpmn_xml, str) or not bpmn_xml:
        return pnml_xml

    try:
        pnml_root = ET.fromstring(pnml_xml)
    except ET.ParseError:
        return pnml_xml

    try:
        bpmn_root = ET.fromstring(bpmn_xml)
    except ET.ParseError:
        return pnml_xml

    pnml_raw_tag = pnml_root.tag
    pnml_ns_prefix = (
        "{" + pnml_raw_tag[1 : pnml_raw_tag.index("}")] + "}"
        if pnml_raw_tag.startswith("{")
        else ""
    )

    if pnml_ns_prefix:
        ET.register_namespace("", pnml_ns_prefix[1:-1])

    def _pnml_tag(local_name):
        return f"{pnml_ns_prefix}{local_name}"

    net = pnml_root.find(f".//{_pnml_tag('net')}")
    if net is None:
        net = pnml_root

    transition_ids = {
        t.get("id")
        for t in pnml_root.iter(_pnml_tag("transition"))
        if t.get("id")
    }
    place_ids = {
        p.get("id") for p in pnml_root.iter(_pnml_tag("place")) if p.get("id")
    }

    if not transition_ids:
        return pnml_xml

    arc_elements = list(pnml_root.iter(_pnml_tag("arc")))
    used_ids = set(transition_ids) | set(place_ids)
    used_arc_ids = {
        arc.get("id")
        for arc in arc_elements
        if isinstance(arc.get("id"), str) and arc.get("id")
    }

    def _next_unique(base_id, used_set):
        candidate = base_id
        suffix = 2
        while candidate in used_set:
            candidate = f"{base_id}_{suffix}"
            suffix += 1
        used_set.add(candidate)
        return candidate

    outgoing_places = {}
    incoming_places = {}
    for arc in arc_elements:
        source = arc.get("source")
        target = arc.get("target")
        if source in transition_ids and target in place_ids:
            outgoing_places.setdefault(source, set()).add(target)
        if source in place_ids and target in transition_ids:
            incoming_places.setdefault(target, set()).add(source)

    relay_pairs = set()
    for transition_id, out_places in outgoing_places.items():
        for place_id in out_places:
            for target_transition in (
                t
                for t in transition_ids
                if place_id in incoming_places.get(t, set())
            ):
                relay_pairs.add((transition_id, target_transition))

    def _add_place(base_id):
        place_id = _next_unique(base_id, used_ids)
        ET.SubElement(net, _pnml_tag("place"), id=place_id)
        place_ids.add(place_id)
        return place_id

    def _add_arc(source, target):
        arc_id = _next_unique(f"{source}TO{target}", used_arc_ids)
        ET.SubElement(net, _pnml_tag("arc"), id=arc_id, source=source, target=target)

    def _ensure_relay(src_transition, tgt_transition, flow_id):
        if (src_transition, tgt_transition) in relay_pairs:
            return
        bridge_place = _add_place(
            f"REPAIR_PLACE_{src_transition}_TO_{tgt_transition}_{flow_id}"
        )
        _add_arc(src_transition, bridge_place)
        _add_arc(bridge_place, tgt_transition)
        relay_pairs.add((src_transition, tgt_transition))
        outgoing_places.setdefault(src_transition, set()).add(bridge_place)
        incoming_places.setdefault(tgt_transition, set()).add(bridge_place)

    def _ensure_outbound_anchor(src_transition, flow_id):
        anchors = outgoing_places.get(src_transition, set())
        if anchors:
            return
        bridge_place = _add_place(f"REPAIR_OUT_{src_transition}_{flow_id}")
        _add_arc(src_transition, bridge_place)
        outgoing_places.setdefault(src_transition, set()).add(bridge_place)

    def _ensure_inbound_anchor(tgt_transition, flow_id):
        anchors = incoming_places.get(tgt_transition, set())
        if anchors:
            return
        bridge_place = _add_place(f"REPAIR_IN_{flow_id}_TO_{tgt_transition}")
        _add_arc(bridge_place, tgt_transition)
        incoming_places.setdefault(tgt_transition, set()).add(bridge_place)

    bpmn_ns = {"bpmn": _NS["bpmn"]}
    flows = bpmn_root.findall(".//bpmn:sequenceFlow", bpmn_ns)
    for index, flow in enumerate(flows, start=1):
        flow_id = flow.get("id") or f"flow{index}"
        source = flow.get("sourceRef")
        target = flow.get("targetRef")
        if not source or not target:
            continue

        src_is_transition = source in transition_ids
        tgt_is_transition = target in transition_ids

        if src_is_transition and tgt_is_transition:
            _ensure_relay(source, target, flow_id)
        elif src_is_transition:
            _ensure_outbound_anchor(source, flow_id)
        elif tgt_is_transition:
            _ensure_inbound_anchor(target, flow_id)

    ET.indent(ET.ElementTree(pnml_root), space="  ", level=0)
    return ET.tostring(pnml_root, encoding="unicode")


def validate_pnml_connectivity(pnml_xml):
    """Validate PNML structural connectivity constraints on transitions.

    After BPMN-to-PNML transformation every transition must have at least one
    inbound arc (a place flows *into* it) and at least one outbound arc (it
    flows *into* a place).  The arc counts convey the gateway role:

    - Exactly 1 inbound + 1 outbound  →  regular transition (task).
    - 1 inbound + N outbound (N > 1)  →  split gateway.
    - N inbound (N > 1) + 1 outbound  →  join gateway.

    A missing inbound or outbound arc is always an error regardless of role.

    Args:
        pnml_xml: PNML XML string to validate.

    Raises:
        PnmlStructureError: if any transition lacks an inbound or outbound arc.
    """
    if not pnml_xml or not isinstance(pnml_xml, str):
        return

    try:
        root = ET.fromstring(pnml_xml)
    except ET.ParseError:
        return  # structural parse errors are handled elsewhere

    raw_tag = root.tag
    ns_prefix = (
        "{" + raw_tag[1 : raw_tag.index("}")] + "}" if raw_tag.startswith("{") else ""
    )

    transition_ids = {
        t.get("id")
        for t in root.iter(f"{ns_prefix}transition")
        if t.get("id")
    }

    inbound: dict = {tid: 0 for tid in transition_ids}
    outbound: dict = {tid: 0 for tid in transition_ids}

    for arc in root.iter(f"{ns_prefix}arc"):
        source = arc.get("source")
        target = arc.get("target")
        if target in transition_ids:
            inbound[target] += 1
        if source in transition_ids:
            outbound[source] += 1

    violations = []
    for tid in sorted(transition_ids):
        if inbound[tid] == 0:
            violations.append(f"transition '{tid}' has no inbound arc")
        if outbound[tid] == 0:
            violations.append(f"transition '{tid}' has no outbound arc")

    if violations:
        raise PnmlStructureError(
            "PNML connectivity check failed: " + "; ".join(violations) + "."
        )


def _normalize_transition_label(text):
    """Normalize transition label text to a plain infinitive-style phrase.

    The transformer decorates task labels with a type prefix
    (e.g. "[UserTask] ..."). Remove that decoration and emit a normalized
    lower-case phrase.
    """
    if not text:
        return text

    normalized = _TASK_PREFIX_RE.sub("", text.strip())
    normalized = _PUNCT_RE.sub(" ", normalized.lower())
    normalized = _WS_RE.sub(" ", normalized).strip()
    return normalized


def _rename_places_and_update_arcs(root, ns_prefix):
    """Rename place IDs to P1..Pn and update arc source/target references."""
    places = [place for place in root.iter(f"{ns_prefix}place") if place.get("id")]
    if not places:
        return

    # Preserve XML order for stable, human-friendly numbering.
    id_map = {place.get("id"): f"P{idx}" for idx, place in enumerate(places, start=1)}

    for place in places:
        old_id = place.get("id")
        place.set("id", id_map[old_id])

    used_arc_ids = set()
    for arc in root.iter(f"{ns_prefix}arc"):
        src = arc.get("source")
        tgt = arc.get("target")
        if src in id_map:
            src = id_map[src]
            arc.set("source", src)
        if tgt in id_map:
            tgt = id_map[tgt]
            arc.set("target", tgt)

        if src and tgt:
            base_id = f"{src}TO{tgt}"
            new_id = base_id
            suffix = 2
            while new_id in used_arc_ids:
                new_id = f"{base_id}_{suffix}"
                suffix += 1
            arc.set("id", new_id)
            used_arc_ids.add(new_id)


def _normalize_transition_labels(root, ns_prefix):
    """Normalize PNML transition labels to a plain lower-case phrase."""
    for transition in root.iter(f"{ns_prefix}transition"):
        name = transition.find(f"{ns_prefix}name")
        if name is None:
            continue

        text_el = name.find(f"{ns_prefix}text")
        if text_el is None or text_el.text is None:
            continue

        normalized = _normalize_transition_label(text_el.text)
        if normalized:
            text_el.text = normalized


def _sanitize_pnml_graph(root, ns_prefix):
    """Enforce a bipartite PNML graph and remove orphan places/transitions.

    Rules applied:
    - Remove arcs with missing/unknown endpoints.
    - Replace transition->transition arcs with transition->place->transition.
    - Replace place->place arcs with place->transition->place.
    - Remove orphan places/transitions (no incident arcs).
    """

    def _tag(local_name):
        return f"{ns_prefix}{local_name}"

    net = root.find(f".//{_tag('net')}")
    if net is None:
        net = root

    def _collect_node_ids(tag_name):
        return {
            node.get("id")
            for node in root.iter(_tag(tag_name))
            if isinstance(node.get("id"), str) and node.get("id")
        }

    place_ids = _collect_node_ids("place")
    transition_ids = _collect_node_ids("transition")

    used_ids = set(place_ids) | set(transition_ids)
    used_arc_ids = {
        arc.get("id")
        for arc in root.iter(_tag("arc"))
        if isinstance(arc.get("id"), str) and arc.get("id")
    }

    def _next_unique(base_id, used_set):
        candidate = base_id
        suffix = 2
        while candidate in used_set:
            candidate = f"{base_id}_{suffix}"
            suffix += 1
        used_set.add(candidate)
        return candidate

    def _add_place(base_id):
        place_id = _next_unique(base_id, used_ids)
        ET.SubElement(net, _tag("place"), id=place_id)
        place_ids.add(place_id)
        return place_id

    def _add_transition(base_id):
        transition_id = _next_unique(base_id, used_ids)
        transition = ET.SubElement(net, _tag("transition"), id=transition_id)
        name = ET.SubElement(transition, _tag("name"))
        text = ET.SubElement(name, _tag("text"))
        text.text = "silent"
        transition_ids.add(transition_id)
        return transition_id

    def _add_arc(source, target):
        arc_id = _next_unique(f"{source}TO{target}", used_arc_ids)
        ET.SubElement(net, _tag("arc"), id=arc_id, source=source, target=target)

    def _remove_element(element):
        for parent in root.iter():
            for child in list(parent):
                if child is element:
                    parent.remove(child)
                    return

    for arc in list(root.iter(_tag("arc"))):
        source = arc.get("source")
        target = arc.get("target")
        if (
            not source
            or not target
            or source == target
            or source not in used_ids
            or target not in used_ids
        ):
            _remove_element(arc)
            continue

        source_is_place = source in place_ids
        target_is_place = target in place_ids
        source_is_transition = source in transition_ids
        target_is_transition = target in transition_ids

        if source_is_transition and target_is_transition:
            _remove_element(arc)
            bridge_place = _add_place(f"BRIDGE_PLACE_{source}_TO_{target}")
            _add_arc(source, bridge_place)
            _add_arc(bridge_place, target)
        elif source_is_place and target_is_place:
            _remove_element(arc)
            bridge_transition = _add_transition(f"bridgeTransition_{source}_TO_{target}")
            _add_arc(source, bridge_transition)
            _add_arc(bridge_transition, target)

    incident_count = {node_id: 0 for node_id in used_ids}
    for arc in root.iter(_tag("arc")):
        source = arc.get("source")
        target = arc.get("target")
        if source in incident_count:
            incident_count[source] += 1
        if target in incident_count:
            incident_count[target] += 1

    for place in list(root.iter(_tag("place"))):
        place_id = place.get("id")
        if place_id and incident_count.get(place_id, 0) == 0:
            _remove_element(place)

    for transition in list(root.iter(_tag("transition"))):
        transition_id = transition.get("id")
        if transition_id and incident_count.get(transition_id, 0) == 0:
            _remove_element(transition)


def _layered_layout(
    elements_by_id, flows, h_gap=80, v_gap=50, x_offset=50, y_offset=50
):
    """Assign top-left (x, y) positions using a left-to-right layered layout.

    Layers are determined by a longest-path computation over the DAG formed by
    *flows*.  Each layer becomes a vertical column of nodes ordered by element
    ID for deterministic output.  Nodes that are part of cycles or are
    disconnected are appended after the main layout.

    Args:
        elements_by_id: ``{id: {"w": int, "h": int}}`` – node sizes in pixels.
        flows: list of ``{"source": str, "target": str}`` dicts.
        h_gap: horizontal gap between adjacent layers (pixels).
        v_gap: vertical gap between nodes within a layer (pixels).
        x_offset: left margin (pixels).
        y_offset: top margin (pixels).

    Returns:
        ``{id: {"x": int, "y": int, "w": int, "h": int}}`` – top-left corners.
    """
    node_ids = list(elements_by_id.keys())
    if not node_ids:
        return {}

    # Build adjacency lists.
    successors: dict[str, list[str]] = {nid: [] for nid in node_ids}
    predecessors: dict[str, list[str]] = {nid: [] for nid in node_ids}
    for flow in flows:
        src, tgt = flow.get("source", ""), flow.get("target", "")
        if src in successors and tgt in predecessors:
            successors[src].append(tgt)
            predecessors[tgt].append(src)

    # Kahn's topological sort for a correct longest-path computation.
    in_degree = {nid: len(predecessors[nid]) for nid in node_ids}
    topo_queue: deque[str] = deque(nid for nid in node_ids if in_degree[nid] == 0)
    topo_order: list[str] = []
    in_degree_work = dict(in_degree)
    while topo_queue:
        node = topo_queue.popleft()
        topo_order.append(node)
        for nxt in successors[node]:
            in_degree_work[nxt] -= 1
            if in_degree_work[nxt] == 0:
                topo_queue.append(nxt)

    # Longest-path layer assignment for acyclic nodes.
    node_layer: dict[str, int] = {nid: 0 for nid in node_ids}
    topo_set = set(topo_order)
    for nid in topo_order:
        for nxt in successors[nid]:
            node_layer[nxt] = max(node_layer[nxt], node_layer[nid] + 1)

    # Append cyclic / disconnected nodes after the main graph.
    if len(topo_order) < len(node_ids):
        max_layer = max(node_layer.values(), default=0) + 1
        for nid in node_ids:
            if nid not in topo_set:
                node_layer[nid] = max_layer
                max_layer += 1

    # Group nodes by layer, sort within each group for stable output.
    layer_groups: dict[int, list[str]] = {}
    for nid in node_ids:
        layer_groups.setdefault(node_layer[nid], []).append(nid)
    for lyr in layer_groups:
        layer_groups[lyr].sort()

    sorted_layers = sorted(layer_groups.keys())

    # Compute the x-start (left edge) of each column.
    layer_x: dict[int, int] = {}
    x = x_offset
    for lyr in sorted_layers:
        layer_x[lyr] = x
        max_w = max(elements_by_id[nid]["w"] for nid in layer_groups[lyr])
        x += max_w + h_gap

    # Compute final positions, centring narrower nodes within their column.
    positions: dict[str, dict] = {}
    for lyr in sorted_layers:
        nodes = layer_groups[lyr]
        max_w_in_layer = max(elements_by_id[nid]["w"] for nid in nodes)
        y = y_offset
        for nid in nodes:
            w = elements_by_id[nid]["w"]
            h = elements_by_id[nid]["h"]
            elem_x = layer_x[lyr] + (max_w_in_layer - w) // 2
            positions[nid] = {"x": elem_x, "y": y, "w": w, "h": h}
            y += h + v_gap

    return positions


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

    _sanitize_pnml_graph(root, ns_prefix)
    _rename_places_and_update_arcs(root, ns_prefix)
    _normalize_transition_labels(root, ns_prefix)

    # Collect all places and transitions from the entire tree (handles
    # nested <pnml><net><page>... hierarchies).
    elements_by_id: dict[str, dict] = {}
    elem_xml_map: dict[str, ET.Element] = {}

    for place in root.iter(f"{ns_prefix}place"):
        pid = place.get("id")
        if pid:
            elements_by_id[pid] = {"w": _PNML_PLACE_W, "h": _PNML_PLACE_H}
            elem_xml_map[pid] = place

    for trans in root.iter(f"{ns_prefix}transition"):
        tid = trans.get("id")
        if tid:
            elements_by_id[tid] = {"w": _PNML_TRANS_W, "h": _PNML_TRANS_H}
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

    for event in model["events"]:
        event_type = _EVENT_TYPE_MAP.get(event["type"], "intermediateCatchEvent")
        ET.SubElement(
            process,
            f"{{{_NS['bpmn']}}}{event_type}",
            id=event["id"],
            name=event["name"],
        )

    for task in model["tasks"]:
        # Convert task type to camelCase (e.g., UserTask -> userTask).
        task_type = task["type"][0].lower() + task["type"][1:]
        ET.SubElement(
            process, f"{{{_NS['bpmn']}}}{task_type}", id=task["id"], name=task["name"]
        )

    for gateway in model["gateways"]:
        gateway_type = gateway["type"][0].lower() + gateway["type"][1:]
        ET.SubElement(
            process,
            f"{{{_NS['bpmn']}}}{gateway_type}",
            id=gateway["id"],
            name=gateway["name"],
        )

    for flow in model["flows"]:
        ET.SubElement(
            process,
            f"{{{_NS['bpmn']}}}sequenceFlow",
            id=flow["id"],
            sourceRef=flow["source"],
            targetRef=flow["target"],
        )

    return definitions


def _add_diagram(definitions, model):
    """Add the BPMN diagram interchange (layout + shapes + edges).

    Sizes every node, computes a layered layout, then emits a BPMNShape for
    each node and a BPMNEdge (right-centre of source to left-centre of target)
    for each flow. ``verify`` upstream guarantees every node and flow endpoint
    exists, so positions are looked up directly.
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

    positions = _layered_layout(
        sizes, model["flows"], h_gap=80, v_gap=50, x_offset=50, y_offset=50
    )

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

    for flow in model["flows"]:
        bpmn_edge = ET.SubElement(
            bpmn_plane,
            f"{{{_NS['bpmndi']}}}BPMNEdge",
            attrib={"id": f"{flow['id']}_di", "bpmnElement": flow["id"]},
        )
        src = positions[flow["source"]]
        tgt = positions[flow["target"]]
        # Connect the right-centre of the source to the left-centre of the target.
        waypoints = [
            {"x": str(src["x"] + src["w"]), "y": str(src["y"] + src["h"] // 2)},
            {"x": str(tgt["x"]), "y": str(tgt["y"] + tgt["h"] // 2)},
        ]
        for waypoint in waypoints:
            ET.SubElement(
                bpmn_edge,
                f"{{{_NS['di']}}}waypoint",
                attrib={"x": waypoint["x"], "y": waypoint["y"]},
            )


def json_to_bpmn(model):
    """Convert a validated logical process model into BPMN 2.0 XML.

    Builds the semantic process, lays it out and draws the diagram, then
    returns the serialized XML string.
    """
    logger.info(
        "Converting model to BPMN",
        extra={k: len(model[k]) for k in ("events", "tasks", "gateways", "flows")},
    )
    definitions = _build_semantic_process(model)
    _add_diagram(definitions, model)

    tree = ET.ElementTree(definitions)
    ET.indent(tree, space="  ", level=0)
    return ET.tostring(definitions, encoding="utf-8", xml_declaration=True).decode(
        "utf-8"
    )
