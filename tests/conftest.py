"""
Shared pytest fixtures and configuration
"""
import pytest
import os
import sys
from unittest.mock import Mock

# Add the project root to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


@pytest.fixture(scope='session')
def app():
    """Create application for the tests."""
    from app import create_app
    app = create_app('testing')
    return app


@pytest.fixture(scope='function')
def client(app):
    """Create a test client for the app."""
    return app.test_client()


@pytest.fixture(scope='function')
def runner(app):
    """Create a test runner for the app's Click commands."""
    return app.test_cli_runner()


@pytest.fixture
def mock_llm_response():
    """Mock LLM API response"""
    import json
    return {
        "message": json.dumps({
            "events": [
                {"id": "startEvent1", "type": "Start", "name": "Process Start"},
                {"id": "endEvent1", "type": "End", "name": "Process End"}
            ],
            "tasks": [
                {"id": "task1", "name": "Example Task", "type": "UserTask"}
            ],
            "gateways": [],
            "flows": [
                {"id": "flow1", "source": "startEvent1", "target": "task1", "type": "SequenceFlow"},
                {"id": "flow2", "source": "task1", "target": "endEvent1", "type": "SequenceFlow"}
            ]
        })
    }


@pytest.fixture
def sample_bpmn_json():
    """Sample BPMN JSON data"""
    return {
        "events": [
            {"id": "start1", "type": "Start", "name": "Start"},
            {"id": "end1", "type": "End", "name": "End"}
        ],
        "tasks": [
            {"id": "task1", "name": "Task 1", "type": "UserTask"}
        ],
        "gateways": [],
        "flows": [
            {"id": "flow1", "source": "start1", "target": "task1", "type": "SequenceFlow"},
            {"id": "flow2", "source": "task1", "target": "end1", "type": "SequenceFlow"}
        ]
    }


@pytest.fixture
def sample_bpmn_xml():
    """Sample BPMN XML string"""
    return """<?xml version='1.0' encoding='UTF-8'?>
<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL"
             xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI"
             xmlns:dc="http://www.omg.org/spec/DD/20100524/DC"
             xmlns:di="http://www.omg.org/spec/DD/20100524/DI">
  <process id="process1">
    <startEvent id="start1" name="Start"/>
    <task id="task1" name="Task 1"/>
    <endEvent id="end1" name="End"/>
    <sequenceFlow id="flow1" sourceRef="start1" targetRef="task1"/>
    <sequenceFlow id="flow2" sourceRef="task1" targetRef="end1"/>
  </process>
</definitions>"""


@pytest.fixture
def mock_transformer_response():
    """Mock transformer API response"""
    return '<pnml><net>Transformed PNML</net></pnml>'


@pytest.fixture(autouse=True)
def reset_environment():
    """Reset environment variables after each test"""
    original_env = os.environ.copy()
    yield
    os.environ.clear()
    os.environ.update(original_env)


@pytest.fixture
def mock_request():
    """Mock Flask request object"""
    mock = Mock()
    mock.json = {"text": "test", "api_key": "test_key"}
    mock.path = "/test"
    mock.remote_addr = "127.0.0.1"
    mock.headers = {"Content-Type": "application/json", "User-Agent": "test"}
    return mock
