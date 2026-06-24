import json

from app.backend.bpmn_writer import json_to_bpmn


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


def raw_response_to_bpmn(raw_response, include_layout=True):
    """Turn the connector's reply into BPMN XML: decode -> build.

    Graph validity (flows referencing real nodes, reachability, ...) is the
    connector's contract to guarantee and is no longer re-checked here. This
    keeps only a crash-safety net: a malformed model that would otherwise raise
    a ``KeyError`` while building is surfaced as a clean ``invalid_model`` error.
    ``include_layout=False`` skips diagram layout for the PNML path, which lays
    out the PNML separately.
    """
    model = _decode(raw_response)
    try:
        return json_to_bpmn(model, include_layout=include_layout)
    except KeyError as exc:
        raise InvalidModelError(
            "Process model could not be built (malformed graph)."
        ) from exc
