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
