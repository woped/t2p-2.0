import pytest
from app.backend.xml_parser import json_to_bpmn

@pytest.fixture
def example_data():
    return {
      "events": [
        {"id": "startEvent1", "type": "Start", "name": "Process Start"},
        {"id": "endEvent1", "type": "End", "name": "Process End"}
      ],
      "tasks": [
        {"id": "task1", "name": "Check for Known Outages", "type": "ServiceTask"}
      ],
      "gateways": [],
      "flows": [
        {"id": "flow1", "source": "startEvent1", "target": "task1", "type": "SequenceFlow"},
        {"id": "flow2", "source": "task1", "target": "endEvent1", "type": "SequenceFlow"}
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


def test_json_to_bpmn_with_gateways():
    """Test BPMN generation with gateways"""
    data = {
        "events": [
            {"id": "start1", "type": "Start", "name": "Start"},
            {"id": "end1", "type": "End", "name": "End"}
        ],
        "tasks": [
            {"id": "task1", "name": "Task 1", "type": "UserTask"}
        ],
        "gateways": [
            {"id": "gateway1", "type": "ExclusiveGateway", "name": "Decision"}
        ],
        "flows": [
            {"id": "flow1", "source": "start1", "target": "task1", "type": "SequenceFlow"},
            {"id": "flow2", "source": "task1", "target": "gateway1", "type": "SequenceFlow"},
            {"id": "flow3", "source": "gateway1", "target": "end1", "type": "SequenceFlow"}
        ]
    }
    
    result = json_to_bpmn(data)
    
    assert "gateway1" in result
    assert "ExclusiveGateway" in result or "exclusiveGateway" in result


def test_json_to_bpmn_with_multiple_tasks():
    """Test BPMN generation with multiple tasks"""
    data = {
        "events": [
            {"id": "start1", "type": "Start", "name": "Start"},
            {"id": "end1", "type": "End", "name": "End"}
        ],
        "tasks": [
            {"id": "task1", "name": "Task 1", "type": "ServiceTask"},
            {"id": "task2", "name": "Task 2", "type": "UserTask"},
            {"id": "task3", "name": "Task 3", "type": "ManualTask"}
        ],
        "gateways": [],
        "flows": [
            {"id": "flow1", "source": "start1", "target": "task1", "type": "SequenceFlow"},
            {"id": "flow2", "source": "task1", "target": "task2", "type": "SequenceFlow"},
            {"id": "flow3", "source": "task2", "target": "task3", "type": "SequenceFlow"},
            {"id": "flow4", "source": "task3", "target": "end1", "type": "SequenceFlow"}
        ]
    }
    
    result = json_to_bpmn(data)
    
    assert "task1" in result
    assert "task2" in result
    assert "task3" in result
    assert "Task 1" in result
    assert "Task 2" in result
    assert "Task 3" in result


def test_json_to_bpmn_with_parallel_gateway():
    """Test BPMN generation with parallel gateway"""
    data = {
        "events": [
            {"id": "start1", "type": "Start", "name": "Start"},
            {"id": "end1", "type": "End", "name": "End"}
        ],
        "tasks": [
            {"id": "task1", "name": "Task 1", "type": "UserTask"}
        ],
        "gateways": [
            {"id": "gateway1", "type": "ParallelGateway", "name": "Split"}
        ],
        "flows": [
            {"id": "flow1", "source": "start1", "target": "gateway1", "type": "SequenceFlow"},
            {"id": "flow2", "source": "gateway1", "target": "task1", "type": "SequenceFlow"},
            {"id": "flow3", "source": "task1", "target": "end1", "type": "SequenceFlow"}
        ]
    }
    
    result = json_to_bpmn(data)
    
    assert "gateway1" in result
    assert "ParallelGateway" in result or "parallelGateway" in result


def test_json_to_bpmn_empty_arrays():
    """Test BPMN generation with minimal data"""
    data = {
        "events": [
            {"id": "start1", "type": "Start", "name": ""},
            {"id": "end1", "type": "End", "name": ""}
        ],
        "tasks": [],
        "gateways": [],
        "flows": [
            {"id": "flow1", "source": "start1", "target": "end1", "type": "SequenceFlow"}
        ]
    }
    
    result = json_to_bpmn(data)
    
    assert isinstance(result, str)
    assert "<?xml" in result
    assert "start1" in result
    assert "end1" in result
