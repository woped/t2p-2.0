"""Build BPMN 2.0 XML (semantic process + diagram interchange) from a model."""

import logging
import xml.etree.ElementTree as ET

from app.backend.layout_core import _route_edges, _sugiyama_layout

logger = logging.getLogger(__name__)

# Node sizes match bpmn-js getDefaultSize (ElementFactory.js) -- the de-facto
# BPMN rendering standard. They are written as <dc:Bounds> and rendered 1:1 by
# woped-web (bpmn-js) and any external BPMN tool, so they stay conventional.
_BPMN_EVENT_W, _BPMN_EVENT_H = 36, 36
_BPMN_TASK_W, _BPMN_TASK_H = 100, 80
_BPMN_GATEWAY_W, _BPMN_GATEWAY_H = 50, 50

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

    node_ids: set[str] = set()

    for event in model["events"]:
        node_ids.add(event["id"])
        event_type = _EVENT_TYPE_MAP.get(event["type"], "intermediateCatchEvent")
        ET.SubElement(
            process,
            f"{{{_NS['bpmn']}}}{event_type}",
            id=event["id"],
            name=event["name"],
        )

    for task in model["tasks"]:
        node_ids.add(task["id"])
        # Convert task type to camelCase (e.g., UserTask -> userTask).
        task_type = task["type"][0].lower() + task["type"][1:]
        ET.SubElement(
            process, f"{{{_NS['bpmn']}}}{task_type}", id=task["id"], name=task["name"]
        )

    for gateway in model["gateways"]:
        node_ids.add(gateway["id"])
        gateway_type = gateway["type"][0].lower() + gateway["type"][1:]
        ET.SubElement(
            process,
            f"{{{_NS['bpmn']}}}{gateway_type}",
            id=gateway["id"],
            name=gateway["name"],
        )

    for flow in model["flows"]:
        # A flow to/from an unknown node is a malformed model; the KeyError is
        # surfaced as invalid_model by the caller.
        for endpoint in (flow["source"], flow["target"]):
            if endpoint not in node_ids:
                raise KeyError(endpoint)
        ET.SubElement(
            process,
            f"{{{_NS['bpmn']}}}sequenceFlow",
            id=flow["id"],
            sourceRef=flow["source"],
            targetRef=flow["target"],
        )

    return definitions


def _add_flow_references(definitions):
    """Add the redundant per-node ``<incoming>``/``<outgoing>`` refs.

    They duplicate the sequence flows and are pure noise for a BPMN client, but
    the model-transformer needs them: its in/out-degree reads these node tags,
    not the edges (without them gateways look degree-0 and get pruned). So they
    are added only on the transformer-feeding path, never in the laid-out BPMN.
    """
    ns = f"{{{_NS['bpmn']}}}"
    process = definitions.find(f"{ns}process")
    nodes = {el.get("id"): el for el in process if not el.tag.endswith("sequenceFlow")}
    for flow in process.findall(f"{ns}sequenceFlow"):
        fid = flow.get("id")
        ET.SubElement(nodes[flow.get("sourceRef")], f"{ns}outgoing").text = fid
        ET.SubElement(nodes[flow.get("targetRef")], f"{ns}incoming").text = fid


def _bpmn_node_size(tag):
    """Layout box size for a BPMN flow-node tag (gateway / event / task)."""
    if tag.endswith("Gateway"):
        return {"w": _BPMN_GATEWAY_W, "h": _BPMN_GATEWAY_H}
    if tag.endswith("Event"):
        return {"w": _BPMN_EVENT_W, "h": _BPMN_EVENT_H}
    return {"w": _BPMN_TASK_W, "h": _BPMN_TASK_H}


def _extract_graph(process):
    """Read the raw graph from the semantic ``<process>`` tree -- topology only.

    The tree the diagram decorates is the single source of truth (the model is
    not re-read). Returns ``(nodes, edges)``: nodes as ``{id, element}`` in
    document order, edges (sequence flows) as ``{source, target, element}``.
    Anything derived (the box size from the tag, the edge id) is left to the
    later steps.
    """
    ns = f"{{{_NS['bpmn']}}}"
    nodes: list[dict] = []
    edges: list[dict] = []
    for child in process:
        tag = child.tag[len(ns) :] if child.tag.startswith(ns) else child.tag
        if tag == "sequenceFlow":
            edges.append(
                {
                    "source": child.get("sourceRef"),
                    "target": child.get("targetRef"),
                    "element": child,
                }
            )
        else:
            nodes.append({"id": child.get("id"), "element": child})
    return nodes, edges


def _node_sizes(nodes):
    """Box ``{w, h}`` per node, derived from its BPMN kind (the element's tag)."""
    return {
        n["id"]: _bpmn_node_size(n["element"].tag.rpartition("}")[2]) for n in nodes
    }


def _add_diagram(definitions):
    """Add the BPMN diagram interchange (layout + shapes + edges).

    Reads the graph from the semantic ``<process>`` tree it decorates, computes a
    layered layout, then emits a BPMNShape per node and a BPMNEdge per flow.
    Edges are routed orthogonally (see :func:`_route_edges`). ``verify`` upstream
    guarantees every node and flow endpoint exists.
    """
    process = definitions.find(f"{{{_NS['bpmn']}}}process")
    nodes, edges = _extract_graph(process)
    elements_by_id = _node_sizes(nodes)

    bpmn_di = ET.SubElement(
        definitions, f"{{{_NS['bpmndi']}}}BPMNDiagram", attrib={"id": "BPMNDiagram_1"}
    )
    bpmn_plane = ET.SubElement(
        bpmn_di,
        f"{{{_NS['bpmndi']}}}BPMNPlane",
        attrib={"id": "BPMNPlane_1", "bpmnElement": "Process_1"},
    )

    positions, ctx = _sugiyama_layout(
        elements_by_id, edges, h_gap=180, v_gap=90, x_offset=50, y_offset=50
    )

    for node in nodes:
        nid = node["id"]
        bpmn_shape = ET.SubElement(
            bpmn_plane,
            f"{{{_NS['bpmndi']}}}BPMNShape",
            attrib={"id": f"{nid}_di", "bpmnElement": nid},
        )
        pos = positions[nid]
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

    if not edges:
        return

    routes = _route_edges(positions, ctx, edges, "full_ortho")
    for idx, edge in enumerate(edges):
        fid = edge["element"].get("id")
        bpmn_edge = ET.SubElement(
            bpmn_plane,
            f"{{{_NS['bpmndi']}}}BPMNEdge",
            attrib={"id": f"{fid}_di", "bpmnElement": fid},
        )
        prev = None
        for px, py in routes[idx]:
            point = (str(int(round(px))), str(int(round(py))))
            if point == prev:
                continue
            ET.SubElement(
                bpmn_edge,
                f"{{{_NS['di']}}}waypoint",
                attrib={"x": point[0], "y": point[1]},
            )
            prev = point


def _serialize_bpmn(definitions):
    """Serialize a BPMN ``<definitions>`` tree to an indented XML string."""
    tree = ET.ElementTree(definitions)
    ET.indent(tree, space="  ", level=0)
    return ET.tostring(definitions, encoding="utf-8", xml_declaration=True).decode(
        "utf-8"
    )


def _log_conversion(kind, model):
    logger.info(
        f"Converting model to {kind} BPMN",
        extra={k: len(model[k]) for k in ("events", "tasks", "gateways", "flows")},
    )


def semantic_bpmn(model):
    """Convert a model into geometry-free BPMN XML (structure only, no diagram).

    Used by the PNML path: the transformer ignores BPMN layout, so drawing one
    here would be wasted work -- the PNML is laid out separately downstream.
    """
    _log_conversion("semantic", model)
    definitions = _build_semantic_process(model)
    _add_flow_references(definitions)
    return _serialize_bpmn(definitions)


def laid_out_bpmn(model):
    """Convert a model into BPMN XML with diagram interchange (shapes + edges)."""
    _log_conversion("laid-out", model)
    definitions = _build_semantic_process(model)
    _add_diagram(definitions)
    return _serialize_bpmn(definitions)
