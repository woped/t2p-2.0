import pytest
from app.backend.xml_parser import json_to_bpmn

@pytest.fixture
def example_data():
    return {
      "events": [
        {"id": "startEvent1", "type": "startEvent", "name": "Process Start"},
        {"id": "endEvent1", "type": "endEvent", "name": "Process End"}
      ],
      "tasks": [
        {"id": "task1", "name": "Check for Known Outages", "type": "serviceTask"}
      ],
      "gateways": [],
      "flows": [
        {"id": "flow1", "source": "startEvent1", "target": "task1", "type": "sequenceFlow"},
        {"id": "flow2", "source": "task1", "target": "endEvent1", "type": "sequenceFlow"}
      ],
      "participants": []
    }

def test_json_to_bpmn_generates_xml(example_data):
    result = json_to_bpmn(example_data)

    # Prüfen, ob der Output ein gültiger XML-String ist
    assert isinstance(result, str)
    assert "<?xml" in result
    assert "<definitions" in result   # nicht mehr '<bpmn:definitions'
    assert "startEvent1" in result
    assert "task1" in result
    assert "endEvent1" in result
