import pytest
import requests
from unittest.mock import patch
from app.backend.app import create_app

@pytest.fixture
def client():
    app = create_app()  
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

# ---- Test 1: Erfolgreicher Aufruf (BPMN aus Text) ----
@patch('app.backend.app.ApiCaller.conversion_pipeline')
def test_generate_BPMN_success(mock_conversion_pipeline, client):
    mock_conversion_pipeline.return_value = "<bpmn-xml></bpmn-xml>"

    response = client.post('/generate_BPMN', json={
        'text': 'Example process',
        'api_key': 'test_key'
    })

    assert response.status_code == 200
    assert 'result' in response.json
    assert '<bpmn-xml>' in response.json['result']

# ---- Test 2: Fehlende Felder ----
def test_generate_BPMN_missing_fields(client):
    response = client.post('/generate_BPMN', json={
        'api_key': 'test_key'
    })
    assert response.status_code == 400
    assert 'Missing data' in response.json['error']

# ---- Test 3: Kein JSON im Body ----
def test_generate_BPMN_no_json(client):
    response = client.post('/generate_BPMN', data='no-json-here', content_type='text/plain')
    assert response.status_code == 500
    assert 'InternalServerError' in response.json['details']['type']
    assert 'Unsupported Media Type' in response.json['details']['message']

# ---- Test 4: Leeres JSON ----
def test_generate_BPMN_empty_json(client):
    response = client.post('/generate_BPMN', json={})
    assert response.status_code == 400
    assert 'Request body must be JSON' in response.json['error']
