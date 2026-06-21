import json
import re

from app.backend.xml_parser import json_to_bpmn

# Element groups that carry id/type/name entries (everything except flows).
_NODE_GROUPS = ("events", "tasks", "gateways")
_CONDITIONAL_TERMS = (
    "if",
    "whether",
    "decision",
    "decide",
    "choose",
    "choice",
    "condition",
    "available",
    "availability",
    "unavailable",
    "stock",
    "complete",
    "completeness",
    "incomplete",
    "approved",
    "rejected",
    "accepted",
    "declined",
    "backorder",
)
_PARALLEL_TERMS = ("parallel", "simultaneous", "both")


class InvalidModelError(ValueError):
    """The connector returned a process model that cannot be processed.

    Subclasses ``ValueError`` so existing ValueError handlers keep catching it.
    The route layer maps it to an ``invalid_model`` response.
    """


def _decode(raw_response):
    """Parse the connector's reply into a logical process model (a dict)."""
    try:
        return json.loads(raw_response)
    except (json.JSONDecodeError, TypeError) as exc:
        raise InvalidModelError("Connector response is not valid JSON.") from exc


def _verify(model, verify_graph=True):
    """Catch the one inconsistency the connector's schema cannot express.

    The provider's structured output already guarantees the shape (the four
    lists and each element's fields), so this does not re-check that. A per-field
    schema cannot guarantee a *cross-reference*, so the only check here is that
    every flow connects nodes that actually exist.
    """
    node_ids = {el["id"] for group in _NODE_GROUPS for el in model[group]}
    for flow in model["flows"]:
        for end in ("source", "target"):
            if flow[end] not in node_ids:
                raise InvalidModelError(
                    f"Flow '{flow['id']}' references an unknown node '{flow[end]}'."
                )

    if verify_graph:
        _verify_reachability(model, node_ids)


def _contains_term(text, terms):
    normalized = (text or "").lower()
    return any(re.search(rf"\b{re.escape(term)}\b", normalized) for term in terms)


def _node_map(model):
    return {el["id"]: el for group in _NODE_GROUPS for el in model[group]}


def _flow_degrees(model):
    node_ids = set(_node_map(model))
    incoming = {node_id: [] for node_id in node_ids}
    outgoing = {node_id: [] for node_id in node_ids}
    for flow in model["flows"]:
        outgoing[flow["source"]].append(flow)
        incoming[flow["target"]].append(flow)
    return incoming, outgoing


def _event_type(event):
    return (event.get("type") or "").lower()


def _verify_reachability(model, node_ids):
    """Reject disconnected process fragments before they become odd PNML."""
    start_ids = {
        event["id"] for event in model["events"] if "start" in _event_type(event)
    }
    if not start_ids or not node_ids:
        return

    _, outgoing = _flow_degrees(model)
    reachable = set()
    stack = list(start_ids)
    while stack:
        node_id = stack.pop()
        if node_id in reachable:
            continue
        reachable.add(node_id)
        stack.extend(flow["target"] for flow in outgoing.get(node_id, []))

    unreachable = sorted(node_ids - reachable)
    if unreachable:
        raise InvalidModelError(
            "Process model contains node(s) unreachable from the start event: "
            + ", ".join(unreachable)
            + "."
        )

    incoming, outgoing = _flow_degrees(model)
    dangling_sources = sorted(
        node_id for node_id in node_ids - start_ids if not incoming.get(node_id)
    )
    if dangling_sources:
        raise InvalidModelError(
            "Process model contains non-start node(s) without incoming flow: "
            + ", ".join(dangling_sources)
            + "."
        )


def _unique_id(existing_ids, base):
    if base not in existing_ids:
        existing_ids.add(base)
        return base

    index = 1
    while f"{base}_{index}" in existing_ids:
        index += 1
    node_id = f"{base}_{index}"
    existing_ids.add(node_id)
    return node_id


def _is_implicit_xor_split(node, target_nodes):
    if _contains_term(node.get("name"), _PARALLEL_TERMS):
        return False
    if _contains_term(node.get("name"), _CONDITIONAL_TERMS):
        return True
    return any(
        _contains_term(target.get("name"), _CONDITIONAL_TERMS)
        for target in target_nodes
    )


def _normalize_implicit_gateways(model):
    """Normalize common LLM graph omissions before BPMN XML generation."""
    normalized = {
        "events": [dict(item) for item in model["events"]],
        "tasks": [dict(item) for item in model["tasks"]],
        "gateways": [dict(item) for item in model["gateways"]],
        "flows": [dict(item) for item in model["flows"]],
    }
    nodes = _node_map(normalized)
    incoming, outgoing = _flow_degrees(normalized)
    existing_ids = set(nodes) | {flow["id"] for flow in normalized["flows"]}
    end_ids = [
        event["id"] for event in normalized["events"] if "end" in _event_type(event)
    ]

    if len(end_ids) == 1:
        end_id = end_ids[0]
        for node_id in sorted(set(nodes) - {end_id}):
            if not outgoing.get(node_id):
                new_flow_id = _unique_id(existing_ids, f"{node_id}_{end_id}")
                normalized["flows"].append(
                    {
                        "id": new_flow_id,
                        "type": "SequenceFlow",
                        "source": node_id,
                        "target": end_id,
                    }
                )

    new_flows = []
    flows_to_remove = set()
    for task in normalized["tasks"]:
        task_outgoing = outgoing.get(task["id"], [])
        if len(task_outgoing) <= 1:
            continue

        targets = [nodes[flow["target"]] for flow in task_outgoing]
        if not _is_implicit_xor_split(task, targets):
            continue

        gateway_id = _unique_id(existing_ids, f"{task['id']}_decision")
        normalized["gateways"].append(
            {
                "id": gateway_id,
                "type": "ExclusiveGateway",
                "name": task.get("name") or "Decision",
            }
        )

        for flow in task_outgoing:
            flows_to_remove.add(flow["id"])
            new_flows.append(
                {
                    **flow,
                    "id": _unique_id(existing_ids, f"{gateway_id}_{flow['target']}"),
                    "source": gateway_id,
                }
            )
        new_flows.append(
            {
                "id": _unique_id(existing_ids, f"{task['id']}_{gateway_id}"),
                "type": "SequenceFlow",
                "source": task["id"],
                "target": gateway_id,
            }
        )

    if flows_to_remove:
        normalized["flows"] = [
            flow for flow in normalized["flows"] if flow["id"] not in flows_to_remove
        ]
        normalized["flows"].extend(new_flows)

    return normalized


def raw_response_to_bpmn(raw_response, include_layout=True):
    """Turn the connector's reply into BPMN XML: decode -> verify -> build.

    Raises ``InvalidModelError`` if the reply is not JSON, or if a flow
    references a node that does not exist; the route maps that to an
    ``invalid_model`` response. ``include_layout=False`` skips diagram layout
    for the PNML path, which lays out the PNML separately.
    """
    model = _decode(raw_response)
    _verify(model, verify_graph=False)
    model = _normalize_implicit_gateways(model)
    _verify(model)
    return json_to_bpmn(model, include_layout=include_layout)
