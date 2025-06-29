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

# ---- Test 4: Transformer HTTPError ----
@patch('app.backend.handlecall.ApiCaller.conversion_pipeline')
@patch('app.backend.handlecall.ModelTransformer.transform')
def test_generate_BPMN_transformer_http_error(mock_transform, mock_conversion_pipeline, client):
    mock_conversion_pipeline.return_value = "<bpmn-xml></bpmn-xml>"

    # Fake HTTPError bauen
    response_mock = requests.models.Response()
    response_mock.status_code = 500
    response_mock._content = b'{"error": "Internal Server Error"}'

    http_error = requests.exceptions.HTTPError(response=response_mock)

    mock_transform.side_effect = http_error

    response = client.post('/generate_BPMN', json={
        'text': 'Example process',
        'api_key': 'test_key'
    })

    assert response.status_code == 500
    assert response.json['details']['type'] == 'TransformerServiceError'
    assert response.json['details']['service_status_code'] == 500

# ---- Test 5: Transformer RequestException ----
@patch('app.backend.handlecall.ApiCaller.conversion_pipeline')
@patch('app.backend.handlecall.ModelTransformer.transform')
def test_generate_BPMN_transformer_request_exception(mock_transform, mock_conversion_pipeline, client):
    mock_conversion_pipeline.return_value = "<bpmn-xml></bpmn-xml>"

    mock_transform.side_effect = requests.exceptions.RequestException("Network broken")

    response = client.post('/generate_BPMN', json={
        'text': 'Example process',
        'api_key': 'test_key'
    })

    assert response.status_code == 500
    assert response.json['details']['type'] == 'NetworkError'
    assert 'Network broken' in response.json['details']['original_error']

# ---- Test 6: Kein JSON im Body ----
def test_generate_BPMN_no_json(client):
    response = client.post('/generate_BPMN', data='no-json-here', content_type='text/plain')

    assert response.status_code == 500
    assert 'InternalServerError' in response.json['details']['type']
    assert 'Unsupported Media Type' in response.json['details']['message']


# ---- Test 7: Leeres JSON ----
def test_generate_BPMN_empty_json(client):
    response = client.post('/generate_BPMN', json={})

    assert response.status_code == 400
    assert 'Request body must be JSON' in response.json['error']

# ---- Test 8: /generate_PNML (pnmltobpmn path) ----
@patch('app.backend.handlecall.ApiCaller.conversion_pipeline')
def test_generate_PNML_success(mock_conversion_pipeline, client):
    mock_conversion_pipeline.return_value = "<bpmn-xml></bpmn-xml>"

    response = client.post('/generate_PNML', json={
        'text': 'Example process',
        'api_key': 'test_key'
    })

    assert response.status_code == 200
    assert '<bpmn-xml>' in response.json['result']
