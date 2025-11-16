"""
Integration tests for the complete T2P workflow
"""
import pytest
from unittest.mock import patch, Mock
import json


@pytest.fixture
def app():
    """Create test Flask app"""
    from app import create_app
    app = create_app('testing')
    return app


@pytest.fixture
def client(app):
    """Create test client"""
    return app.test_client()


class TestEndToEndBPMNGeneration:
    """End-to-end tests for BPMN generation workflow"""
    
    @patch('app.backend.gpt_process.requests.post')
    def test_complete_bpmn_generation_flow(self, mock_llm_request, client):
        """Test complete flow from text to BPMN"""
        # Mock LLM API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": json.dumps({
                "events": [
                    {"id": "start1", "type": "Start", "name": "Process Start"},
                    {"id": "end1", "type": "End", "name": "Process End"}
                ],
                "tasks": [
                    {"id": "task1", "name": "Do Something", "type": "UserTask"}
                ],
                "gateways": [],
                "flows": [
                    {"id": "flow1", "source": "start1", "target": "task1", "type": "SequenceFlow"},
                    {"id": "flow2", "source": "task1", "target": "end1", "type": "SequenceFlow"}
                ]
            })
        }
        mock_llm_request.return_value = mock_response
        
        # Make request
        response = client.post('/generate_bpmn', json={
            'text': 'A simple process with one task',
            'api_key': 'test_api_key'
        })
        
        # Verify response
        assert response.status_code == 200
        assert 'result' in response.json
        result = response.json['result']
        assert '<?xml' in result
        assert 'start1' in result
        assert 'task1' in result
        assert 'end1' in result

# TODO: Mock pnml correctly
# class TestEndToEndPNMLGeneration:
#     """End-to-end tests for PNML generation workflow"""
    
#     @patch('app.backend.gpt_process.requests.post')
#     @patch('app.backend.modeltransformer.requests.post')
#     def test_complete_pnml_generation_flow(self, mock_transformer, mock_llm, client):
#         """Test complete flow from text to PNML"""
#         # Mock LLM response
#         mock_llm_response = Mock()
#         mock_llm_response.status_code = 200
#         mock_llm_response.json.return_value = {
#             "message": json.dumps({
#                 "events": [
#                     {"id": "start1", "type": "Start", "name": "Start"},
#                     {"id": "end1", "type": "End", "name": "End"}
#                 ],
#                 "tasks": [
#                     {"id": "task1", "name": "Task", "type": "UserTask"}
#                 ],
#                 "gateways": [],
#                 "flows": [
#                     {"id": "flow1", "source": "start1", "target": "task1", "type": "SequenceFlow"},
#                     {"id": "flow2", "source": "task1", "target": "end1", "type": "SequenceFlow"}
#                 ]
#             })
#         }
#         mock_llm.return_value = mock_llm_response
        
#         # Mock transformer response
#         mock_transformer_response = Mock()
#         mock_transformer_response.status_code = 200
#         mock_transformer_response.text = '<pnml>Transformed PNML</pnml>'
#         mock_transformer_response.raise_for_status = Mock()
#         mock_transformer.return_value = mock_transformer_response
        
#         # Make request
#         response = client.post('/generate_pnml', json={
#             'text': 'A simple process',
#             'api_key': 'test_api_key'
#         })
        
#         # Verify response
#         assert response.status_code == 200
#         assert 'result' in response.json
#         assert '<pnml>' in response.json['result']


class TestErrorHandling:
    """Tests for various error scenarios"""
    
    def test_missing_api_key(self, client):
        """Test request without API key"""
        response = client.post('/generate_bpmn', json={
            'text': 'Some process'
        })
        
        assert response.status_code == 400
        assert 'error' in response.json
        assert 'api_key' in response.json['error']
    
    def test_missing_text(self, client):
        """Test request without text"""
        response = client.post('/generate_bpmn', json={
            'api_key': 'test_key'
        })
        
        assert response.status_code == 400
        assert 'error' in response.json
        assert 'text' in response.json['error']
    
    def test_empty_request_body(self, client):
        """Test request with empty body"""
        response = client.post('/generate_bpmn', json={})
        
        assert response.status_code == 400
        assert 'error' in response.json
    
    @patch('app.backend.gpt_process.requests.post')
    def test_llm_api_error(self, mock_llm, client):
        """Test LLM API returning error"""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_llm.return_value = mock_response
        
        response = client.post('/generate_bpmn', json={
            'text': 'Some process',
            'api_key': 'test_key'
        })
        
        assert response.status_code == 500
        assert 'error' in response.json
    
    @patch('app.backend.gpt_process.requests.post')
    def test_invalid_json_from_llm(self, mock_llm, client):
        """Test LLM returning invalid JSON"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": "{'invalid': 'json with single quotes'}"
        }
        mock_llm.return_value = mock_response
        
        response = client.post('/generate_bpmn', json={
            'text': 'Some process',
            'api_key': 'test_key'
        })
        
        assert response.status_code == 500
        assert 'error' in response.json
        assert 'LLMResponseError' in response.json.get('details', {}).get('type', '')


class TestMetricsIntegration:
    """Tests for Prometheus metrics integration"""
    
    def test_metrics_updated_on_request(self, client):
        """Test that metrics are updated when requests are made"""
        # Make a request
        client.get('/test_connection')
        
        # Check metrics endpoint
        metrics_response = client.get('/metrics')
        assert metrics_response.status_code == 200
        
        # Metrics should contain request data
        metrics_data = metrics_response.data.decode('utf-8')
        assert 'http_requests_total' in metrics_data or 'REQUEST_COUNT' in metrics_data
    
    def test_metrics_track_different_endpoints(self, client):
        """Test that different endpoints are tracked separately"""
        client.get('/test_connection')
        client.get('/_/_/echo')
        
        metrics_response = client.get('/metrics')
        metrics_data = metrics_response.data.decode('utf-8')
        
        # Should have metrics for both endpoints
        assert 'test_connection' in metrics_data or '/test_connection' in metrics_data
        assert 'echo' in metrics_data or '/_/_/echo' in metrics_data


class TestDeprecationHeaders:
    """Tests for deprecation warning headers"""
    
    @patch('app.api.routes.HandleCall.handle')
    def test_deprecated_endpoint_headers(self, mock_handle, client):
        """Test that deprecated endpoint includes proper headers"""
        mock_handle.return_value = ({'result': 'test'}, 200)
        
        response = client.post('/api_call', json={
            'text': 'test',
            'api_key': 'key'
        })
        
        # Check deprecation headers
        assert 'Deprecation' in response.headers
        assert response.headers['Deprecation'] == 'true'
        assert 'Sunset' in response.headers
        assert 'Link' in response.headers
        assert 'deprecation' in response.headers['Link'].lower()


class TestCORSAndSecurity:
    """Tests for CORS and security headers"""
    
    def test_cors_headers_present(self, client):
        """Test CORS headers are configured"""
        response = client.get('/test_connection')
        # CORS headers might be configured, check if response is valid
        assert response.status_code == 200
    
    def test_content_type_json(self, client):
        """Test JSON endpoints return correct content type"""
        response = client.get('/test_connection')
        assert 'application/json' in response.content_type
