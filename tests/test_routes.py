"""
Comprehensive tests for API routes in app.api.routes
"""
import pytest
from unittest.mock import patch, Mock
from flask import Flask


@pytest.fixture
def app():
    """Create test Flask app"""
    from app import create_app
    app = create_app('testing')
    app.config['TESTING'] = True
    return app


@pytest.fixture
def client(app):
    """Create test client"""
    return app.test_client()


class TestExampleRoute:
    """Tests for /example endpoint"""
    
    def test_example_route_success(self, client):
        response = client.get('/example')
        assert response.status_code == 200
        assert b'This is an example route' in response.data


class TestMetrics:
    """Tests for /metrics endpoint"""
    
    def test_metrics_endpoint(self, client):
        response = client.get('/metrics')
        assert response.status_code == 200
        assert response.content_type.startswith('text/plain')
        # Prometheus metrics should contain these
        assert b'http_requests_total' in response.data or b'REQUEST_COUNT' in response.data


class TestConnectionEndpoint:
    """Tests for /test_connection endpoint"""
    
    def test_connection_success(self, client):
        response = client.get('/test_connection')
        assert response.status_code == 200
        assert response.json == "Successful"
    
    @patch('app.api.routes.REQUEST_COUNT')
    def test_connection_increments_counter(self, mock_counter, client):
        response = client.get('/test_connection')
        assert response.status_code == 200
        # Verify counter was incremented
        mock_counter.labels.assert_called()


class TestDeprecatedAPICall:
    """Tests for deprecated /api_call endpoint"""
    
    @patch('app.api.routes.HandleCall.handle')
    def test_api_call_returns_deprecation_headers(self, mock_handle, client):
        mock_handle.return_value = ({'result': 'test'}, 200)
        
        response = client.post('/api_call', json={
            'text': 'test process',
            'api_key': 'test_key'
        })
        
        assert response.status_code == 200
        assert 'Deprecation' in response.headers
        assert response.headers['Deprecation'] == 'true'
        assert 'Sunset' in response.headers
        assert 'Link' in response.headers
    
    @patch('app.api.routes.HandleCall.handle')
    def test_api_call_handles_exception(self, mock_handle, client):
        mock_handle.side_effect = Exception("Test error")
        
        response = client.post('/api_call', json={
            'text': 'test process',
            'api_key': 'test_key'
        })
        
        assert response.status_code == 500
        assert 'error' in response.json


class TestGenerateBPMN:
    """Tests for /generate_bpmn and /generate_BPMN endpoints"""
    
    @patch('app.api.routes.HandleCall.handle')
    def test_generate_bpmn_lowercase_success(self, mock_handle, client):
        mock_handle.return_value = ({'result': '<bpmn>test</bpmn>'}, 200)
        
        response = client.post('/generate_bpmn', json={
            'text': 'test process',
            'api_key': 'test_key'
        })
        
        assert response.status_code == 200
        mock_handle.assert_called_once()
    
    @patch('app.api.routes.HandleCall.handle')
    def test_generate_bpmn_uppercase_success(self, mock_handle, client):
        mock_handle.return_value = ({'result': '<bpmn>test</bpmn>'}, 200)
        
        response = client.post('/generate_BPMN', json={
            'text': 'test process',
            'api_key': 'test_key'
        })
        
        assert response.status_code == 200
        mock_handle.assert_called_once()
    
    @patch('app.api.routes.HandleCall.handle')
    def test_generate_bpmn_with_tuple_response(self, mock_handle, client):
        # HandleCall can return (response, status_code) tuple
        mock_handle.return_value = ({'result': '<bpmn>test</bpmn>'}, 201)
        
        response = client.post('/generate_bpmn', json={
            'text': 'test process',
            'api_key': 'test_key'
        })
        
        assert response.status_code == 201
    
    @patch('app.api.routes.HandleCall.handle')
    def test_generate_bpmn_exception(self, mock_handle, client):
        mock_handle.side_effect = Exception("Processing error")
        
        response = client.post('/generate_bpmn', json={
            'text': 'test process',
            'api_key': 'test_key'
        })
        
        assert response.status_code == 500
        assert 'error' in response.json


class TestGeneratePNML:
    """Tests for /generate_pnml and /generate_PNML endpoints"""
    
    @patch('app.api.routes.HandleCall.handle')
    def test_generate_pnml_lowercase_success(self, mock_handle, client):
        mock_handle.return_value = ({'result': '<pnml>test</pnml>'}, 200)
        
        response = client.post('/generate_pnml', json={
            'text': 'test process',
            'api_key': 'test_key'
        })
        
        assert response.status_code == 200
        mock_handle.assert_called_once()
        # Verify correct direction parameter
        call_args = mock_handle.call_args
        assert call_args[0][1]['direction'] == 'bpmntopnml'
    
    @patch('app.api.routes.HandleCall.handle')
    def test_generate_pnml_uppercase_success(self, mock_handle, client):
        mock_handle.return_value = ({'result': '<pnml>test</pnml>'}, 200)
        
        response = client.post('/generate_PNML', json={
            'text': 'test process',
            'api_key': 'test_key'
        })
        
        assert response.status_code == 200
    
    @patch('app.api.routes.HandleCall.handle')
    def test_generate_pnml_with_tuple_response(self, mock_handle, client):
        mock_handle.return_value = ({'result': '<pnml>test</pnml>'}, 201)
        
        response = client.post('/generate_pnml', json={
            'text': 'test process',
            'api_key': 'test_key'
        })
        
        assert response.status_code == 201
    
    @patch('app.api.routes.HandleCall.handle')
    def test_generate_pnml_exception(self, mock_handle, client):
        mock_handle.side_effect = ValueError("Invalid data")
        
        response = client.post('/generate_pnml', json={
            'text': 'test process',
            'api_key': 'test_key'
        })
        
        assert response.status_code == 500
        assert 'error' in response.json


class TestEchoEndpoint:
    """Tests for /_/_/echo endpoint"""
    
    def test_echo_success(self, client):
        response = client.get('/_/_/echo')
        assert response.status_code == 200
        assert response.json == {'success': True}
    
    @patch('app.api.routes.REQUEST_COUNT')
    @patch('app.api.routes.REQUEST_LATENCY')
    def test_echo_increments_metrics(self, mock_latency, mock_counter, client):
        response = client.get('/_/_/echo')
        assert response.status_code == 200
        # Verify metrics were updated
        mock_counter.labels.assert_called()
        mock_latency.labels.assert_called()
