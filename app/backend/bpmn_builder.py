import json

from app.backend.xml_parser import json_to_bpmn

# Element groups that carry id/type/name entries (everything except flows).
_NODE_GROUPS = ("events", "tasks", "gateways")


class InvalidModelError(ValueError):
    """The connector returned a process model that cannot be processed.

    Subclasses ``ValueError`` so existing ValueError handlers keep catching it.
    The route layer maps it to an ``invalid_model`` response.
    """


def _decode(raw_response):
    """Parse the connector's reply into a logical process model (a dict).

    The connector replies with consistent JSON (the provider is called in
    structured-JSON mode), so this only parses the text - it does not strip
    wrappers or accept other formats.
    """
    if not isinstance(raw_response, str):
        raise InvalidModelError("Connector response must be text.")
    try:
        return json.loads(raw_response)
    except json.JSONDecodeError as exc:
        raise InvalidModelError("Connector response is not valid JSON.") from exc


def _verify(model):
    """Quick structural check of the logical model; raises InvalidModelError.

    Confirms shape only - it does not repair or normalize anything:
      * the four element groups are present and are lists,
      * every node carries the fields the build step reads (id/type/name),
      * every flow has id/source/target and connects existing nodes.
    """
    if not isinstance(model, dict):
        raise InvalidModelError("Process model must be a JSON object.")

    for group in (*_NODE_GROUPS, "flows"):
        if not isinstance(model.get(group), list):
            raise InvalidModelError(f"Process model is missing the '{group}' list.")

    node_ids = set()
    for group in _NODE_GROUPS:
        for element in model[group]:
            if not isinstance(element, dict):
                raise InvalidModelError(f"Each '{group}' entry must be an object.")
            for field in ("id", "type", "name"):
                if field not in element:
                    raise InvalidModelError(f"A '{group}' entry is missing '{field}'.")
            node_ids.add(element["id"])

    for flow in model["flows"]:
        if not isinstance(flow, dict):
            raise InvalidModelError("Each 'flows' entry must be an object.")
        for field in ("id", "source", "target"):
            if field not in flow:
                raise InvalidModelError(f"A 'flows' entry is missing '{field}'.")
        for end in ("source", "target"):
            if flow[end] not in node_ids:
                raise InvalidModelError(
                    f"Flow '{flow['id']}' references unknown {end} '{flow[end]}'."
                )


def raw_response_to_bpmn(raw_response):
    """Turn the connector's reply into BPMN XML: decode -> verify -> build.

    Raises ``InvalidModelError`` if the reply cannot be read or is structurally
    invalid; the route layer maps that to an ``invalid_model`` response. This is
    transport-agnostic (no Flask/HTTP), so it can be unit-tested in isolation.
    """
    model = _decode(raw_response)
    _verify(model)
    return json_to_bpmn(model)
