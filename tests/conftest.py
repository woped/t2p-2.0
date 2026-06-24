"""
Shared pytest fixtures and configuration
"""

import json
import os
import socket
import sys
import threading
from pathlib import Path
from unittest.mock import Mock

import pytest
from flask import Flask, jsonify, request
from werkzeug.serving import make_server

# Add the project root to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

_PROCESS_TEXT_DIR = Path(__file__).resolve().parent / "process_texts"


def _build_mock_raw_response(user_text):
    normalized_text = user_text.lower()
    if "atm" in normalized_text:
        task_name = "ATM Withdrawal"
    elif "bicycle" in normalized_text or "bike" in normalized_text:
        task_name = "Bicycle Repair"
    else:
        task_name = "Ice Cream Service"

    return json.dumps(
        {
            "events": [
                {"id": "start", "type": "startEvent", "name": "Start"},
                {"id": "end", "type": "endEvent", "name": "End"},
            ],
            "tasks": [{"id": "task1", "name": task_name, "type": "UserTask"}],
            "gateways": [],
            "flows": [
                {"id": "flow1", "type": "SequenceFlow", "source": "start", "target": "task1"},
                {"id": "flow2", "type": "SequenceFlow", "source": "task1", "target": "end"},
            ],
        }
    )


def _reserve_local_port(host):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="session")
def app():
    """Create application for the tests."""
    from app import create_app

    app = create_app("testing")
    return app


@pytest.fixture(scope="function")
def client(app):
    """Create a test client for the app."""
    return app.test_client()


@pytest.fixture(scope="function")
def runner(app):
    """Create a test runner for the app's Click commands."""
    return app.test_cli_runner()


@pytest.fixture
def mock_llm_response():
    """Mock LLM API response"""
    import json

    return {
        "message": json.dumps(
            {
                "events": [
                    {"id": "startEvent1", "type": "Start", "name": "Process Start"},
                    {"id": "endEvent1", "type": "End", "name": "Process End"},
                ],
                "tasks": [{"id": "task1", "name": "Example Task", "type": "UserTask"}],
                "gateways": [],
                "flows": [
                    {
                        "id": "flow1",
                        "source": "startEvent1",
                        "target": "task1",
                        "type": "SequenceFlow",
                    },
                    {
                        "id": "flow2",
                        "source": "task1",
                        "target": "endEvent1",
                        "type": "SequenceFlow",
                    },
                ],
            }
        )
    }


@pytest.fixture
def sample_bpmn_json():
    """Sample BPMN JSON data"""
    return {
        "events": [
            {"id": "start1", "type": "Start", "name": "Start"},
            {"id": "end1", "type": "End", "name": "End"},
        ],
        "tasks": [{"id": "task1", "name": "Task 1", "type": "UserTask"}],
        "gateways": [],
        "flows": [
            {
                "id": "flow1",
                "source": "start1",
                "target": "task1",
                "type": "SequenceFlow",
            },
            {
                "id": "flow2",
                "source": "task1",
                "target": "end1",
                "type": "SequenceFlow",
            },
        ],
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
    return "<pnml><net>Transformed PNML</net></pnml>"


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


@pytest.fixture
def process_texts():
    """Load the sample process descriptions used by integration tests."""
    return {
        path.name: path.read_text(encoding="utf-8").strip()
        for path in sorted(_PROCESS_TEXT_DIR.glob("*.txt"))
    }


@pytest.fixture
def mock_connector_server():
    """Run a local Flask connector stub on an ephemeral port."""
    host = os.environ.get("T2P_TEST_CONNECTOR_HOST", "127.0.0.1")
    port = _reserve_local_port(host)
    received_requests = {"generate": [], "models": 0}

    connector_app = Flask("mock_connector")

    @connector_app.post("/generate")
    def generate():
        payload = request.get_json(silent=True) or {}
        received_requests["generate"].append(payload)

        if payload.get("provider") is None or payload.get("model") is None:
            return (
                jsonify(
                    {
                        "error": {
                            "code": "invalid_request",
                            "message": "Missing provider or model.",
                        }
                    }
                ),
                400,
            )

        user_text = payload.get("user_text", "")
        return jsonify({"raw_response": _build_mock_raw_response(user_text)}), 200

    @connector_app.get("/models")
    def models():
        received_requests["models"] += 1
        return (
            jsonify(
                {
                    "models": [
                        {"provider": "openai", "model": "gpt-4o"},
                        {"provider": "anthropic", "model": "claude-3.5-sonnet"},
                    ]
                }
            ),
            200,
        )

    server = make_server(host, port, connector_app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    yield {
        "base_url": f"http://{host}:{port}",
        "received_requests": received_requests,
    }

    server.shutdown()
    server.server_close()
    thread.join(timeout=5)
