import unittest
import os
import sys
from unittest.mock import MagicMock, patch

import requests

from app.backend.app import app
from app.backend.modeltransformer import ModelTransformer

# Add the app/backend directory to the Python path.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend')))


# The following is the test for the app.py file.
class TestApp(unittest.TestCase):
    """
    This class contains unit tests for the app.
    """

    def setUp(self):
        """
        Set up the test client.
        """
        self.app = app.test_client()
        self.app.testing = True

    def test_test_connection(self):
        """
        Test the test_connection endpoint. It should return "Successful".
        """
        response = self.app.get('/test_connection')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, "Successful")

    def test_api_call_missing_data(self):
        """
        Test the api_call endpoint with missing data. It should return a 400 error.
        """
        response = self.app.post('/api_call', json={})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json, {"error": "Missing data for: text, api_key"})

    def test_api_call_error_500(self):
        """
        Test the api_call endpoint with a wrong content type. It should return a 500 error.
        """
        response = self.app.post('/api_call', "This is not json")
        self.assertEqual(response.status_code, 500)

    def test_api_call_success(self):
        """
        Test the api_call endpoint with a successful API call.
        """
        with patch('backend.gpt_process.ApiCaller') as mock:
            mock.return_value = MagicMock()
            mock.return_value.conversion_pipeline.return_value = "Success"
            response = self.app.post('/api_call', json={"text": "Hello", "api_key": "123"})
            self.assertEqual(response.status_code, 200)


class TestModelTransformer(unittest.TestCase):
    def setUp(self):
        self.transformer = ModelTransformer()
        self.bpmn_file_path = "app/backend/bpmn_output.bpmn"
        with open(self.bpmn_file_path, "r") as file:
            self.bpmn_xml = file.read()

    @patch("requests.post")
    def test_transform_success(self, mock_post):
        # Mock a successful API response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<transformed>BPMN</transformed>"
        mock_post.return_value = mock_response

        # Call the transform method
        result = self.transformer.transform(self.bpmn_xml)

        # Assertions
        self.assertEqual(result, "<transformed>BPMN</transformed>")
        mock_post.assert_called_once()

    @patch("requests.post")
    def test_transform_http_error(self, mock_post):
        # Mock an HTTP error response
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=mock_response
        )
        mock_post.return_value = mock_response

        # Call the transform method and expect an exception
        with self.assertRaises(requests.exceptions.HTTPError):
            self.transformer.transform(self.bpmn_xml)

        mock_post.assert_called_once()

    @patch("requests.post")
    def test_transform_request_exception(self, mock_post):
        # Mock a network-related exception
        mock_post.side_effect = requests.exceptions.RequestException("Network error")

        # Call the transform method and expect an exception
        with self.assertRaises(requests.exceptions.RequestException):
            self.transformer.transform(self.bpmn_xml)

        mock_post.assert_called_once()


if __name__ == '__main__':
    unittest.main()
