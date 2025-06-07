import unittest
from unittest.mock import patch, MagicMock
import os
import sys
import importlib
from backend.gpt_process import ApiCaller
import backend.config as config_module
import backend.gpt_process as gpt_process_module

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

class TestGptProcess(unittest.TestCase):

    def setUp(self):
        self.api_key = "dummy_key"
        self.api_caller = ApiCaller(self.api_key)

    # Tests a successful API call
    @patch('backend.gpt_process.requests.post')
    def test_call_api_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'message': 'mocked response'}
        mock_post.return_value = mock_response

        result = self.api_caller.call_api('describe a process')
        self.assertEqual(result, 'mocked response')
        mock_post.assert_called_once()

    # Verifies that prompting_strategie is passed in the payload
    @patch('backend.gpt_process.requests.post')
    def test_call_api_includes_prompting_strategie(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'message': 'ok'}
        mock_post.return_value = mock_response

        self.api_caller.call_api("example input")

        _, kwargs = mock_post.call_args
        payload = kwargs["json"]
        self.assertIn("prompting_strategie", payload)
        self.assertEqual(payload["prompting_strategie"], "few_shot")

    # Tests whether PROMPTING_STRATEGIE from environment variable is applied
    @patch.dict(os.environ, {"PROMPTING_STRATEGIE": "one_shot"})
    @patch('backend.gpt_process.requests.post')
    def test_call_api_with_custom_prompting_strategie(self, mock_post):
        importlib.reload(config_module)
        importlib.reload(gpt_process_module)
        ApiCallerReloaded = gpt_process_module.ApiCaller
        api_caller = ApiCallerReloaded("test_key")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'message': 'ok'}
        mock_post.return_value = mock_response

        api_caller.call_api("testing prompting")

        _, kwargs = mock_post.call_args
        payload = kwargs["json"]
        self.assertEqual(payload["prompting_strategie"], "one_shot")

    # Tests when the API returns an error status code
    @patch('backend.gpt_process.requests.post')
    def test_call_api_error_status(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = 'Internal Server Error'
        mock_post.return_value = mock_response

        result = self.api_caller.call_api('fail test')
        self.assertIn("An error occurred", result)

    # Tests behavior when a request exception is raised
    @patch('backend.gpt_process.requests.post', side_effect=Exception("Connection error"))
    def test_call_api_exception(self, mock_post):
        result = self.api_caller.call_api('test error')
        self.assertIn("An exception occurred", result)

    # Tests whether generate_bpmn_json returns the result of call_api
    @patch.object(ApiCaller, 'call_api', return_value='{"step":"1"}')
    def test_generate_bpmn_json(self, mock_call_api):
        result = self.api_caller.generate_bpmn_json("test process")
        self.assertEqual(result, '{"step":"1"}')
        mock_call_api.assert_called_once()

    # Tests full conversion pipeline: input → JSON → BPMN XML
    @patch('backend.gpt_process.json_to_bpmn', return_value="<xml>BPMN</xml>")
    @patch.object(ApiCaller, 'call_api', return_value='{"step":"1"}')
    def test_conversion_pipeline_success(self, mock_call_api, mock_json_to_bpmn):
        result = self.api_caller.conversion_pipeline("describe process")
        self.assertEqual(result, "<xml>BPMN</xml>")
        mock_call_api.assert_called_once()
        mock_json_to_bpmn.assert_called_once_with({"step": "1"})

    # Tests error handling when invalid JSON is returned by call_api
    @patch.object(ApiCaller, 'call_api', return_value="invalid json")
    def test_conversion_pipeline_invalid_json(self, mock_call_api):
        result = self.api_caller.conversion_pipeline("invalid")
        self.assertIn("An error occurred", result)


if __name__ == '__main__':
    unittest.main()
