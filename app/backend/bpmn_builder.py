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
    """Parse the connector's reply into a logical process model (a dict)."""
    try:
        return json.loads(raw_response)
    except (json.JSONDecodeError, TypeError) as exc:
        raise InvalidModelError("Connector response is not valid JSON.") from exc


def _verify(model):
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


def raw_response_to_bpmn(raw_response):
    """Turn the connector's reply into BPMN XML: decode -> verify -> build.

    Raises ``InvalidModelError`` if the reply is not JSON, or if a flow
    references a node that does not exist; the route maps that to an
    ``invalid_model`` response.
    """
    model = _decode(raw_response)
    _verify(model)
    return json_to_bpmn(model)
