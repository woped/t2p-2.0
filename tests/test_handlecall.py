import pytest
from unittest.mock import patch
from app.backend.app import app

@pytest.fixture
def client():
    with app.test_client() as client:
        yield client

# ---- Test 1: Erfolgreicher Aufruf ----
@patch('app.backend.handlecall.ApiCaller.conversion_pipeline')
@patch('app.backend.handlecall.ModelTransformer.transform')
def test_generate_BPMN_success(mock_transform, mock_conversion_pipeline, client):
    mock_conversion_pipeline.return_value = "<bpmn-xml></bpmn-xml>"
    mock_transform.return_value = "<pnml-xml></pnml-xml>"

    response = client.post('/generate_BPMN', json={
        'text': 'Example process',
        'api_key': 'test_key'
    })

    assert response.status_code == 200
    assert 'result' in response.json
    assert '<pnml-xml>' in response.json['result']

# ---- Test 2: Fehlende Felder ----
def test_generate_BPMN_missing_fields(client):
    response = client.post('/generate_BPMN', json={
        'api_key': 'test_key'  # text fehlt
    })

    assert response.status_code == 400
    assert 'Missing data' in response.json['error']

# ---- Test 3: Transformer RequestException ----
@patch('app.backend.handlecall.ApiCaller.conversion_pipeline')
@patch('app.backend.handlecall.ModelTransformer.transform')
def test_generate_BPMN_transformer_exception(mock_transform, mock_conversion_pipeline, client):
    mock_conversion_pipeline.return_value = "<bpmn-xml></bpmn-xml>"
    mock_transform.side_effect = Exception("Fake Transformer Crash")

    response = client.post('/generate_BPMN', json={
        'text': 'Example process',
        'api_key': 'test_key'
    })

    assert response.status_code == 500
    assert 'InternalServerError' in response.json['details']['type']
