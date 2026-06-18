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


def test_conditional_task_split_is_normalized_to_exclusive_gateway():
    model = json.dumps(
        {
            "events": [
                {"id": "start", "type": "startEvent", "name": "Start"},
                {"id": "end", "type": "endEvent", "name": "End"},
            ],
            "tasks": [
                {"id": "record", "type": "Task", "name": "Record Order"},
                {
                    "id": "check",
                    "type": "Task",
                    "name": "Check order completeness",
                },
                {"id": "pick", "type": "Task", "name": "Pick Product"},
                {"id": "notify", "type": "Task", "name": "Notify Customer of Backorder"},
            ],
            "gateways": [],
            "flows": [
                {"id": "f1", "type": "SequenceFlow", "source": "start", "target": "record"},
                {"id": "f2", "type": "SequenceFlow", "source": "record", "target": "check"},
                {"id": "f3", "type": "SequenceFlow", "source": "check", "target": "pick"},
                {"id": "f4", "type": "SequenceFlow", "source": "check", "target": "notify"},
                {"id": "f5", "type": "SequenceFlow", "source": "pick", "target": "end"},
                {"id": "f6", "type": "SequenceFlow", "source": "notify", "target": "end"},
            ],
        }
    )

    result = raw_response_to_bpmn(model)

    assert "exclusiveGateway" in result
    assert "check_decision" in result
    assert 'sourceRef="check" targetRef="check_decision"' in result


def test_disconnected_non_start_task_is_rejected():
    model = json.dumps(
        {
            "events": [
                {"id": "start", "type": "startEvent", "name": "Start"},
                {"id": "end", "type": "endEvent", "name": "End"},
            ],
            "tasks": [
                {"id": "record", "type": "Task", "name": "Record Order"},
                {"id": "pick", "type": "Task", "name": "Pick Product"},
            ],
            "gateways": [],
            "flows": [
                {"id": "f1", "type": "SequenceFlow", "source": "start", "target": "record"},
                {"id": "f2", "type": "SequenceFlow", "source": "record", "target": "end"},
                {"id": "f3", "type": "SequenceFlow", "source": "pick", "target": "end"},
            ],
        }
    )

    with pytest.raises(InvalidModelError, match="unreachable"):
        raw_response_to_bpmn(model)


def test_terminal_task_without_outgoing_flow_is_connected_to_single_end_event():
    model = json.dumps(
        {
            "events": [
                {"id": "start", "type": "startEvent", "name": "Start"},
                {"id": "end", "type": "endEvent", "name": "End"},
            ],
            "tasks": [
                {"id": "record", "type": "Task", "name": "Record Order"},
                {"id": "notify", "type": "Task", "name": "Notify Customer"},
            ],
            "gateways": [],
            "flows": [
                {"id": "f1", "type": "SequenceFlow", "source": "start", "target": "record"},
                {"id": "f2", "type": "SequenceFlow", "source": "record", "target": "notify"},
            ],
        }
    )

    result = raw_response_to_bpmn(model)

    assert 'sourceRef="notify" targetRef="end"' in result


def test_duplicate_task_names_are_merged_before_bpmn_generation():
    model = json.dumps(
        {
            "events": [
                {"id": "start", "type": "startEvent", "name": "Start"},
                {"id": "end", "type": "endEvent", "name": "End"},
            ],
            "tasks": [
                {"id": "check", "type": "Task", "name": "Check Order Completeness"},
                {"id": "ship", "type": "Task", "name": "Ship Order"},
                {"id": "delivered_a", "type": "Task", "name": "Product Delivered"},
                {"id": "notify", "type": "Task", "name": "Notify Customer of Backorder"},
                {"id": "delivered_b", "type": "Task", "name": "Product Delivered"},
            ],
            "gateways": [],
            "flows": [
                {"id": "f1", "type": "SequenceFlow", "source": "start", "target": "check"},
                {"id": "f2", "type": "SequenceFlow", "source": "check", "target": "ship"},
                {"id": "f3", "type": "SequenceFlow", "source": "check", "target": "notify"},
                {"id": "f4", "type": "SequenceFlow", "source": "ship", "target": "delivered_a"},
                {"id": "f5", "type": "SequenceFlow", "source": "notify", "target": "delivered_b"},
                {"id": "f6", "type": "SequenceFlow", "source": "delivered_a", "target": "end"},
            ],
        }
    )

    result = raw_response_to_bpmn(model)

    assert result.count('name="Product Delivered"') == 1
    assert 'sourceRef="notify" targetRef="end"' in result
    assert 'sourceRef="notify" targetRef="delivered_a"' not in result


def test_backorder_branch_does_not_flow_to_product_delivered():
    model = json.dumps(
        {
            "events": [
                {"id": "start", "type": "startEvent", "name": "Start"},
                {"id": "end", "type": "endEvent", "name": "End"},
            ],
            "tasks": [
                {"id": "check", "type": "Task", "name": "Is Product In Stock?"},
                {"id": "notify", "type": "Task", "name": "Notify Customer of Backorder"},
                {"id": "delivered", "type": "Task", "name": "Product Delivered"},
            ],
            "gateways": [],
            "flows": [
                {"id": "f1", "type": "SequenceFlow", "source": "start", "target": "check"},
                {"id": "f2", "type": "SequenceFlow", "source": "check", "target": "notify"},
                {"id": "f3", "type": "SequenceFlow", "source": "notify", "target": "delivered"},
                {"id": "f4", "type": "SequenceFlow", "source": "delivered", "target": "end"},
            ],
        }
    )

    result = raw_response_to_bpmn(model)

    assert 'sourceRef="notify" targetRef="end"' in result
    assert 'sourceRef="notify" targetRef="delivered"' not in result
    assert 'name="Product Delivered"' not in result
