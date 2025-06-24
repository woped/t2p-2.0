from flask import jsonify
import pytest
from app.backend.app import app
from unittest.mock import patch

@pytest.fixture
def client():
    with app.test_client() as client:
        yield client

def test_test_connection(client):
    response = client.get('/test_connection')
    assert response.status_code == 200
    assert response.json == "Successful"

def test_echo(client):
    response = client.get('/_/_/echo')
    assert response.status_code == 200
    assert response.json['success'] is True

def test_metrics(client):
    response = client.get('/metrics')
    assert response.status_code == 200
    assert b'http_requests_total' in response.data

def test_swagger_yaml(client):
    response = client.get('/api/swagger.yaml')
    assert response.status_code == 200
    assert b'openapi' in response.data or b'openAPI' in response.data or b'swagger' in response.data

def test_api_call(client):
    response = client.post('/api_call', json={})
    assert response.status_code in (400, 500)

def test_generate_BPMN_call(client):
    response = client.post('/generate_BPMN', json={})
    assert response.status_code in (400, 500)

def test_generate_PNML_call(client):
    response = client.post('/generate_PNML', json={})
    assert response.status_code in (400, 500)

@patch('app.backend.handlecall.HandleCall.handle', side_effect=Exception("Simulated Crash"))
def test_api_call_exception(mock_handle, client):
    response = client.post('/api_call', json={"text": "example", "api_key": "key"})
    assert response.status_code == 500
    assert 'error' in response.json


