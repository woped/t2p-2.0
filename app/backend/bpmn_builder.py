import json

from app.backend.xml_parser import json_to_bpmn

# Element groups that carry id/type/name entries (everything except flows).
_NODE_GROUPS = ("events", "tasks", "gateways")


class InvalidModelError(ValueError):
    """The connector returned a process model that cannot be processed.

    Subclasses ``ValueError`` so existing ValueError handlers keep catching it.
    The route layer maps it to an ``invalid_model`` response.
    """


def _require(ok, message):
    if not ok:
        raise InvalidModelError(message)


def _decode(raw_response):
    """Parse the connector's reply into a logical process model (a dict).

    The connector replies with consistent, provider-enforced JSON, so this only
    parses the text - it does not strip wrappers or accept other formats.
    """
    _require(isinstance(raw_response, str), "Connector response must be text.")
    try:
        return json.loads(raw_response)
    except json.JSONDecodeError as exc:
        raise InvalidModelError("Connector response is not valid JSON.") from exc


def _verify(model):
    """Quick structural check of the logical model; raises InvalidModelError.

    Confirms shape only (it does not repair anything): the four element groups
    are lists, every node has id, a non-empty type and name, and every flow has
    id/source/target and connects existing nodes.
    """
    _require(isinstance(model, dict), "Process model must be a JSON object.")
    for group in (*_NODE_GROUPS, "flows"):
        _require(isinstance(model.get(group), list), f"Missing '{group}' list.")

    node_ids = set()
    for group in _NODE_GROUPS:
        for el in model[group]:
            _require(
                isinstance(el, dict)
                and all(k in el for k in ("id", "type", "name"))
                and el["type"],
                f"Each '{group}' entry needs id, a non-empty type, and name.",
            )
            node_ids.add(el["id"])

    for flow in model["flows"]:
        _require(
            isinstance(flow, dict)
            and all(k in flow for k in ("id", "source", "target")),
            "Each 'flows' entry needs id, source and target.",
        )
        _require(
            flow["source"] in node_ids and flow["target"] in node_ids,
            f"Flow '{flow['id']}' references an unknown node.",
        )


def raw_response_to_bpmn(raw_response):
    """Turn the connector's reply into BPMN XML: decode -> verify -> build.

    Raises ``InvalidModelError`` if the reply cannot be read or is structurally
    invalid; the route layer maps that to an ``invalid_model`` response.
    """
    model = _decode(raw_response)
    _verify(model)
    return json_to_bpmn(model)
