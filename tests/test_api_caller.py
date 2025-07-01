import unittest
import os
from unittest.mock import patch, Mock
from app.backend.gpt_process import ApiCaller
import pytest

class TestApiCaller(unittest.TestCase):

    def setUp(self):
        # Test setup without requiring real API
        self.api_key = "test_api_key"  
        self.api_caller = ApiCaller(api_key=self.api_key, llm_provider="openai", prompting_strategy="few_shot")

    @patch('app.backend.gpt_process.requests.post')
    def test_openai_api_call_success(self, mock_post):
        """Unit test for OpenAI API call with mocked response"""
        # Mock successful API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'message': '{"events": [{"id": "start1", "type": "startEvent", "name": "Start"}]}'
        }
        mock_post.return_value = mock_response

        prompt = "A simple description of a business process."
        result = self.api_caller.call_api(prompt)

        self.assertIsInstance(result, str)
        self.assertIn("events", result)
        mock_post.assert_called_once()

    @patch('app.backend.gpt_process.requests.post')
    def test_api_call_error_handling(self, mock_post):
        """Test API error handling"""
        # Mock API error response
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_post.return_value = mock_response

        result = self.api_caller.call_api("test prompt")
        
        self.assertIsInstance(result, str)
        self.assertIn("An error occurred", result)

    @patch('app.backend.gpt_process.requests.post')
    def test_api_call_connection_error(self, mock_post):
        """Test connection error handling"""
        # Mock connection error
        mock_post.side_effect = ConnectionError("Connection failed")

        result = self.api_caller.call_api("test prompt")
        
        self.assertIsInstance(result, str)
        self.assertIn("An exception occurred", result)

    @patch('app.backend.gpt_process.ApiCaller.call_api')
    @patch('app.backend.gpt_process.json_to_bpmn')
    def test_conversion_pipeline_success(self, mock_json_to_bpmn, mock_call_api):
        """Test successful conversion pipeline"""
        # Mock API response with valid JSON
        mock_call_api.return_value = '{"events": [{"id": "start1", "type": "startEvent"}], "tasks": [], "gateways": [], "flows": []}'
        # Mock BPMN conversion
        mock_json_to_bpmn.return_value = '<?xml version="1.0" encoding="UTF-8"?><definitions>...</definitions>'

        result = self.api_caller.conversion_pipeline("Customer reports issue")
        
        self.assertIsInstance(result, str)
        self.assertTrue(result.startswith("<?xml") or result.startswith("<"))
        mock_call_api.assert_called_once()
        mock_json_to_bpmn.assert_called_once()

    @patch('app.backend.gpt_process.ApiCaller.call_api')
    def test_conversion_pipeline_invalid_json(self, mock_call_api):
        """Test conversion pipeline with invalid JSON response"""
        # Mock API response with invalid JSON
        mock_call_api.return_value = "Invalid JSON response"

        result = self.api_caller.conversion_pipeline("Test prompt")
        
        self.assertIsInstance(result, str)
        self.assertIn("error occurred", result)  # Fixed assertion

    def test_resolve_endpoint_openai(self):
        """Test endpoint resolution for OpenAI"""
        api_caller = ApiCaller(api_key="test", llm_provider="openai")
        self.assertEqual(api_caller.endpoint, "call_openai")

    def test_resolve_endpoint_gemini(self):
        """Test endpoint resolution for Gemini"""
        api_caller = ApiCaller(api_key="test", llm_provider="gemini")
        self.assertEqual(api_caller.endpoint, "call_gemini")

    def test_resolve_endpoint_invalid(self):
        """Test endpoint resolution with invalid provider"""
        with self.assertRaises(ValueError):
            ApiCaller(api_key="test", llm_provider="invalid_provider")


# Mocked Integration Tests (frühere Integration Tests jetzt mit Mocks)
class TestApiCallerMockedIntegration(unittest.TestCase):
    """Mocked integration tests - simulate real API behavior without actual calls"""

    def setUp(self):
        self.api_key = "test_api_key"
        self.api_caller = ApiCaller(api_key=self.api_key, llm_provider="openai", prompting_strategy="few_shot")

    @patch('app.backend.gpt_process.requests.post')
    def test_openai_api_call_integration_mock(self, mock_post):
        """Mocked integration test for OpenAI API call"""
        # Mock successful OpenAI-like response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'message': '{"events": [{"id": "start1", "type": "startEvent", "name": "Process Started"}], "tasks": [{"id": "task1", "type": "userTask", "name": "Review Application"}], "gateways": [], "flows": [{"id": "flow1", "type": "sequenceFlow", "source": "start1", "target": "task1"}]}'
        }
        mock_post.return_value = mock_response

        prompt = "A simple description of a business process."
        result = self.api_caller.call_api(prompt)

        self.assertIsInstance(result, str)
        self.assertIn("events", result)
        self.assertIn("Process Started", result)
        mock_post.assert_called_once()

    @patch('app.backend.gpt_process.requests.post')
    def test_gemini_api_call_integration_mock(self, mock_post):
        """Mocked integration test for Gemini API call"""
        # Create Gemini API caller
        gemini_caller = ApiCaller(api_key=self.api_key, llm_provider="gemini", prompting_strategy="few_shot")
        
        # Mock successful Gemini-like response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'message': '{"events": [{"id": "start1", "type": "startEvent", "name": "Customer Request"}], "tasks": [{"id": "task1", "type": "serviceTask", "name": "Process Request"}], "gateways": [], "flows": [{"id": "flow1", "type": "sequenceFlow", "source": "start1", "target": "task1"}]}'
        }
        mock_post.return_value = mock_response

        result = gemini_caller.call_api("A process that begins with a customer request.")
        
        self.assertIsInstance(result, str)
        self.assertIn("events", result)
        self.assertIn("Customer Request", result)
        mock_post.assert_called_once()

    @patch('app.backend.gpt_process.ApiCaller.call_api')
    @patch('app.backend.gpt_process.json_to_bpmn')
    def test_conversion_pipeline_integration_mock(self, mock_json_to_bpmn, mock_call_api):
        """Mocked integration test for full conversion pipeline"""
        # Mock realistic API response
        mock_call_api.return_value = '''
        {
            "events": [
                {"id": "start1", "type": "startEvent", "name": "Issue Reported"},
                {"id": "end1", "type": "endEvent", "name": "Issue Resolved"}
            ],
            "tasks": [
                {"id": "task1", "type": "userTask", "name": "Analyze Issue"},
                {"id": "task2", "type": "serviceTask", "name": "Process Issue"}
            ],
            "gateways": [
                {"id": "gateway1", "type": "exclusiveGateway", "name": "Decision Point"}
            ],
            "flows": [
                {"id": "flow1", "type": "sequenceFlow", "source": "start1", "target": "task1"},
                {"id": "flow2", "type": "sequenceFlow", "source": "task1", "target": "gateway1"},
                {"id": "flow3", "type": "sequenceFlow", "source": "gateway1", "target": "task2"},
                {"id": "flow4", "type": "sequenceFlow", "source": "task2", "target": "end1"}
            ]
        }
        '''
        
        # Mock realistic BPMN XML output
        mock_json_to_bpmn.return_value = '''<?xml version="1.0" encoding="UTF-8"?>
<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL" 
             xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI"
             targetNamespace="http://example.bpmn.com/schema/bpmn">
  <process id="Process_1" isExecutable="false">
    <startEvent id="start1" name="Issue Reported" />
    <userTask id="task1" name="Analyze Issue" />
    <serviceTask id="task2" name="Process Issue" />
    <exclusiveGateway id="gateway1" name="Decision Point" />
    <endEvent id="end1" name="Issue Resolved" />
    <sequenceFlow id="flow1" sourceRef="start1" targetRef="task1" />
    <sequenceFlow id="flow2" sourceRef="task1" targetRef="gateway1" />
    <sequenceFlow id="flow3" sourceRef="gateway1" targetRef="task2" />
    <sequenceFlow id="flow4" sourceRef="task2" targetRef="end1" />
  </process>
</definitions>'''

        result = self.api_caller.conversion_pipeline("Customer reports issue, system processes it.")
        
        self.assertIsInstance(result, str)
        self.assertTrue(result.startswith("<?xml"))
        self.assertIn("Issue Reported", result)
        self.assertIn("Process_1", result)
        mock_call_api.assert_called_once()
        mock_json_to_bpmn.assert_called_once()

    @patch('app.backend.gpt_process.requests.post')
    def test_api_error_integration_mock(self, mock_post):
        """Mocked integration test for API error scenarios"""
        # Mock API error response
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized: Invalid API key"
        mock_post.return_value = mock_response

        result = self.api_caller.call_api("test prompt")
        
        self.assertIsInstance(result, str)
        self.assertIn("An error occurred", result)
        self.assertIn("401", result)

    @patch('app.backend.gpt_process.requests.post')
    def test_connection_error_integration_mock(self, mock_post):
        """Mocked integration test for connection error scenarios"""
        # Mock connection error
        mock_post.side_effect = ConnectionError("Connection failed")

        result = self.api_caller.call_api("test prompt")
        
        self.assertIsInstance(result, str)
        self.assertIn("An exception occurred", result)


if __name__ == '__main__':
    unittest.main()
