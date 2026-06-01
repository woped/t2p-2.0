import json

from app.backend.xml_parser import json_to_bpmn


def raw_response_to_bpmn(raw_response):
    """Convert the connector's LLM JSON response to BPMN XML.

    This is the post-connector processing step: it decodes the connector's
    ``raw_response`` string and builds the BPMN XML. It is transport-agnostic
    (no Flask/HTTP), so it can be unit-tested in isolation.
    """
    if not isinstance(raw_response, str):
        raise ValueError("LLM API connector response must be text.")

    content = raw_response.strip()
    if content.startswith("<"):
        return content
    if content.startswith("```"):
        content = content.split("\n", 1)[1] if "\n" in content else content[3:]
        if content.endswith("```"):
            content = content.rsplit("```", 1)[0]
        content = content.strip()

    try:
        return json_to_bpmn(json.loads(content))
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError("LLM API connector returned invalid BPMN JSON.") from exc
