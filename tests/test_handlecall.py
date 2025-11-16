import pytest
import requests
from unittest.mock import patch
from app import create_app

@pytest.fixture
def client():
    app = create_app()  
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

# ---- Test 1: Erfolgreicher Aufruf (BPMN aus Text) ----
@patch('app.backend.handlecall.ApiCaller.conversion_pipeline')
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
    assert response.status_code == 400
    assert 'Request body must be JSON' in response.json['error']

# ---- Test 4: Leeres JSON ----
def test_generate_BPMN_empty_json(client):
    response = client.post('/generate_BPMN', json={})
    assert response.status_code == 400
    assert 'Request body must be JSON' in response.json['error']


# ---- Test 5: HTTPError from transformer ----
@patch('app.backend.handlecall.ApiCaller.conversion_pipeline')
@patch('app.backend.handlecall.ModelTransformer.transform')
def test_generate_PNML_http_error(mock_transform, mock_conversion, client):
    from requests.exceptions import HTTPError
    from unittest.mock import Mock
    
    mock_conversion.return_value = "<bpmn>Test</bpmn>"
    mock_response = Mock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"
    mock_transform.side_effect = HTTPError(response=mock_response)

    response = client.post('/generate_PNML', json={
        'text': 'Example process',
        'api_key': 'test_key'
    })

    assert response.status_code == 500
    assert 'TransformerServiceError' in response.json['details']['type']


# ---- Test 6: RequestException from transformer ----
@patch('app.backend.handlecall.ApiCaller.conversion_pipeline')
@patch('app.backend.handlecall.ModelTransformer.transform')
def test_generate_PNML_request_exception(mock_transform, mock_conversion, client):
    from requests.exceptions import RequestException
    
    mock_conversion.return_value = "<bpmn>Test</bpmn>"
    mock_transform.side_effect = RequestException("Network error")

    response = client.post('/generate_PNML', json={
        'text': 'Example process',
        'api_key': 'test_key'
    })

    assert response.status_code == 500
    assert 'NetworkError' in response.json['details']['type']


# ---- Test 7: ValueError from LLM ----
@patch('app.backend.handlecall.ApiCaller.conversion_pipeline')
def test_generate_BPMN_value_error(mock_conversion, client):
    mock_conversion.side_effect = ValueError("Invalid JSON from LLM")

    response = client.post('/generate_BPMN', json={
        'text': 'Example process',
        'api_key': 'test_key'
    })

    assert response.status_code == 500
    assert 'LLMResponseError' in response.json['details']['type']


# ---- Test 8: RuntimeError from LLM connector ----
@patch('app.backend.handlecall.ApiCaller.conversion_pipeline')
def test_generate_BPMN_runtime_error(mock_conversion, client):
    mock_conversion.side_effect = RuntimeError("LLM API connector failed")

    response = client.post('/generate_BPMN', json={
        'text': 'Example process',
        'api_key': 'test_key'
    })

    assert response.status_code == 500
    assert 'LLMConnectorError' in response.json['details']['type']


# ---- Test 9: Successful PNML generation ----
@patch('app.backend.handlecall.ApiCaller.conversion_pipeline')
@patch('app.backend.handlecall.ModelTransformer.transform')
def test_generate_PNML_success(mock_transform, mock_conversion, client):
    mock_conversion.return_value = "<bpmn>Test</bpmn>"
    mock_transform.return_value = "<pnml>Test-PNML</pnml>"

    response = client.post('/generate_PNML', json={
        'text': 'Example process',
        'api_key': 'test_key'
    })

    assert response.status_code == 200
    assert 'result' in response.json
    assert '<pnml>Test-PNML</pnml>' in response.json['result']
