"""Build BPMN 2.0 XML (semantic process + diagram interchange) from a model."""

import logging
import xml.etree.ElementTree as ET

from app.backend.layout_core import _route_edges, _sugiyama_layout

logger = logging.getLogger(__name__)

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


def _bpmn_node_size(tag):
    """Layout box size for a BPMN flow-node tag (gateway / event / task)."""
    if tag.endswith("Gateway"):
        return {"w": _BPMN_GATEWAY_W, "h": _BPMN_GATEWAY_H}
    if tag.endswith("Event"):
        return {"w": _BPMN_EVENT_W, "h": _BPMN_EVENT_H}
    return {"w": _BPMN_TASK_W, "h": _BPMN_TASK_H}


def _extract_graph(process):
    """Read the layout graph from the semantic ``<process>`` tree.

    Returns ``(elements_by_id, flows, node_ids)``: node sizes keyed by id, the
    sequence flows as ``{source, target, id}``, and the node ids in document
    order. The geometry-free tree the diagram decorates is the single source of
    truth -- node size follows the element's tag, the model is not re-read.
    """
    ns = f"{{{_NS['bpmn']}}}"
    elements_by_id: dict[str, dict] = {}
    node_ids: list[str] = []
    flows: list[dict] = []
    for child in process:
        tag = child.tag[len(ns) :] if child.tag.startswith(ns) else child.tag
        if tag == "sequenceFlow":
            flows.append(
                {
                    "source": child.get("sourceRef"),
                    "target": child.get("targetRef"),
                    "id": child.get("id"),
                }
            )
        else:
            nid = child.get("id")
            elements_by_id[nid] = _bpmn_node_size(tag)
            node_ids.append(nid)
    return elements_by_id, flows, node_ids


def _add_diagram(definitions):
    """Add the BPMN diagram interchange (layout + shapes + edges).

    Reads the graph from the semantic ``<process>`` tree it decorates, computes a
    layered layout, then emits a BPMNShape per node and a BPMNEdge per flow.
    Edges are routed orthogonally (see :func:`_route_edges`). ``verify`` upstream
    guarantees every node and flow endpoint exists.
    """
    process = definitions.find(f"{{{_NS['bpmn']}}}process")
    elements_by_id, flows, node_ids = _extract_graph(process)

    bpmn_di = ET.SubElement(
        definitions, f"{{{_NS['bpmndi']}}}BPMNDiagram", attrib={"id": "BPMNDiagram_1"}
    )
    bpmn_plane = ET.SubElement(
        bpmn_di,
        f"{{{_NS['bpmndi']}}}BPMNPlane",
        attrib={"id": "BPMNPlane_1", "bpmnElement": "Process_1"},
    )

    positions, ctx = _sugiyama_layout(
        elements_by_id, flows, h_gap=180, v_gap=90, x_offset=50, y_offset=50
    )

    for nid in node_ids:
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

    if not flows:
        return

    routes = _route_edges(positions, ctx, flows, "full_ortho")
    for idx, flow in enumerate(flows):
        bpmn_edge = ET.SubElement(
            bpmn_plane,
            f"{{{_NS['bpmndi']}}}BPMNEdge",
            attrib={"id": f"{flow['id']}_di", "bpmnElement": flow["id"]},
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
    return _serialize_bpmn(_build_semantic_process(model))


def laid_out_bpmn(model):
    """Convert a model into BPMN XML with diagram interchange (shapes + edges)."""
    _log_conversion("laid-out", model)
    definitions = _build_semantic_process(model)
    _add_diagram(definitions)
    return _serialize_bpmn(definitions)
