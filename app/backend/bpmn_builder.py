import json

from app.backend.bpmn_writer import laid_out_bpmn, semantic_bpmn


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


def _build(raw_response, build):
    """Decode the connector's reply and run *build* (a bpmn_writer function).

    Graph validity (flows referencing real nodes, reachability, ...) is the
    connector's contract to guarantee and is no longer re-checked here. This
    keeps only a crash-safety net: a malformed model that would otherwise raise
    a ``KeyError`` while building is surfaced as a clean ``invalid_model`` error.
    """
    model = _decode(raw_response)
    try:
        return build(model)
    except KeyError as exc:
        raise InvalidModelError(
            "Process model could not be built (malformed graph)."
        ) from exc


def raw_response_to_bpmn(raw_response):
    """Connector reply -> BPMN XML with diagram layout."""
    return _build(raw_response, laid_out_bpmn)


def raw_response_to_semantic_bpmn(raw_response):
    """Connector reply -> geometry-free BPMN XML (input for the PNML path)."""
    return _build(raw_response, semantic_bpmn)
