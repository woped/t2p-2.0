import unittest
import os
import sys
from unittest.mock import MagicMock, patch
import app.backend.config as config
import requests

from app.backend.app import app
from app.backend.modeltransformer import ModelTransformer

# Add the app/backend directory to the Python path.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend')))

# The following is the test for the app.py file.
class TestApp(unittest.TestCase):
    """
    This class contains unit tests for the Flask app endpoints.
    """

    def setUp(self):
        """
        Set up the test client.
        """
        self.app = app.test_client()
        self.app.testing = True

    def test_test_connection(self):
        """
        Test the /test_connection endpoint. It should return "Successful".
        """
        response = self.app.get('/test_connection')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, "Successful")

    def test_api_call_missing_data(self):
        """
        Test the /api_call endpoint with missing data. It should return a 400 error.
        """
        response = self.app.post('/api_call', json={})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json, {"error": "Request body must be JSON."})

    def test_api_call_error_500(self):
        """
        Test the /api_call endpoint with an invalid content type. It should return a 500 error.
        """
        response = self.app.post('/api_call', data="This is not json", content_type='text/plain')
        self.assertEqual(response.status_code, 500)

    @patch('app.backend.gpt_process.ApiCaller')
    @patch('app.backend.modeltransformer.ModelTransformer.transform')
    def test_api_call_success(self, mock_transform, mock_api_caller):
        """
        Test the /api_call endpoint with valid input and a successful transformation.
        """
        mock_api_caller.return_value.conversion_pipeline.return_value = "Mocked BPMN output"
        mock_transform.return_value = "<pnml>mocked result</pnml>"

        response = self.app.post('/api_call', json={"text": "Hello", "api_key": "123"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"result": "<pnml>mocked result</pnml>"})


class TestModelTransformer(unittest.TestCase):
    """
    This class tests the ModelTransformer logic directly.
    """

    def setUp(self):
        self.transformer = ModelTransformer()
        self.bpmn_xml = "<bpmn>dummy content</bpmn>"
        config.TRANSFORMER_BASE_URL = "http://localhost:1234"

    @patch("requests.post")
    def test_transform_success(self, mock_post):
        """
        Test successful transformation with mocked POST response.
        """
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"pnml": "<pnml>mocked result</pnml>"}'
        mock_post.return_value = mock_response

        result = self.transformer.transform(self.bpmn_xml)

        self.assertEqual(result, "<pnml>mocked result</pnml>")
        mock_post.assert_called_once()

    @patch("requests.post")
    def test_transform_http_error(self, mock_post):
        """
        Simulate HTTPError from transformer service.
        """
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(response=mock_response)
        mock_post.return_value = mock_response

        with self.assertRaises(requests.exceptions.HTTPError):
            self.transformer.transform(self.bpmn_xml)

        mock_post.assert_called_once()

    @patch("requests.post")
    def test_transform_request_exception(self, mock_post):
        """
        Simulate network-related exception.
        """
        mock_post.side_effect = requests.exceptions.RequestException("Network error")

        with self.assertRaises(requests.exceptions.RequestException):
            self.transformer.transform(self.bpmn_xml)

        mock_post.assert_called_once()


if __name__ == "__main__":
    unittest.main()
