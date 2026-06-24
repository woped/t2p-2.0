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
