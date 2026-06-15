import json

import pytest

from app.backend.bpmn_builder import InvalidModelError, raw_response_to_bpmn
from tests.sample_models import RAW_MODEL_JSON as VALID_MODEL


def test_valid_model_builds_bpmn():
    result = raw_response_to_bpmn(VALID_MODEL)
    assert "<definitions" in result
    assert "start" in result and "end" in result


def test_non_string_is_rejected():
    with pytest.raises(InvalidModelError):
        raw_response_to_bpmn({"events": []})


def test_non_json_is_rejected():
    # The raw-XML passthrough tolerance was removed: XML is no longer accepted.
    with pytest.raises(InvalidModelError):
        raw_response_to_bpmn("<bpmn>already xml</bpmn>")


def test_markdown_fenced_json_is_rejected():
    # The code-fence stripping tolerance was removed: the connector is expected
    # to return clean JSON.
    with pytest.raises(InvalidModelError):
        raw_response_to_bpmn("```json\n" + VALID_MODEL + "\n```")


def test_flow_referencing_unknown_node_is_rejected():
    model = (
        '{"events": [{"id": "start", "type": "startEvent", "name": "Start"}],'
        ' "tasks": [], "gateways": [],'
        ' "flows": [{"id": "f", "source": "start", "target": "ghost"}]}'
    )
    with pytest.raises(InvalidModelError):
        raw_response_to_bpmn(model)


def test_flow_with_unknown_source_is_rejected():
    # The dangling endpoint can be the *source*, not only the target: both ends
    # of every flow must resolve to a real node.
    model = (
        '{"events": [{"id": "end", "type": "endEvent", "name": "End"}],'
        ' "tasks": [], "gateways": [],'
        ' "flows": [{"id": "f", "source": "ghost", "target": "end"}]}'
    )
    with pytest.raises(InvalidModelError):
        raw_response_to_bpmn(model)


def test_flow_endpoints_may_be_gateways():
    # Cross-reference resolution must consider all node groups, not just events
    # and tasks: a flow whose endpoint is a gateway is valid and must build.
    model = json.dumps(
        {
            "events": [
                {"id": "start", "type": "startEvent", "name": "Start"},
                {"id": "end", "type": "endEvent", "name": "End"},
            ],
            "tasks": [],
            "gateways": [{"id": "gw", "type": "ExclusiveGateway", "name": "Decide"}],
            "flows": [
                {"id": "f1", "source": "start", "target": "gw"},
                {"id": "f2", "source": "gw", "target": "end"},
            ],
        }
    )
    result = raw_response_to_bpmn(model)
    assert "gw" in result


def test_valid_model_returns_wellformed_xml():
    # The validator's success path must yield XML the downstream tooling can
    # parse, not merely a string that contains "<definitions".
    import xml.etree.ElementTree as ET

    ET.fromstring(raw_response_to_bpmn(VALID_MODEL))
