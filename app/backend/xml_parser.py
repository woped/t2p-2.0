import xml.etree.ElementTree as ET
import logging
from collections import deque

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Layout constants
# ---------------------------------------------------------------------------
_BPMN_EVENT_W, _BPMN_EVENT_H = 36, 36
_BPMN_TASK_W, _BPMN_TASK_H = 100, 80
_BPMN_GATEWAY_W, _BPMN_GATEWAY_H = 50, 50

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
        event_type = {
            "Start": "startEvent",
            "startEvent": "startEvent",
            "End": "endEvent",
            "endEvent": "endEvent",
        }.get(event["type"], "intermediateCatchEvent")
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
