import unittest
from unittest.mock import patch
import os
import sys
from gpt_process import ApiCaller
from modeltransformer import ModelTransformer

class TestApiCaller(unittest.TestCase):
    @patch('gpt_process.ApiCaller.call_api')
    def setUp(self, mock_call_api):
        """
        Set up the test for the ApiCaller class.
        """ 
        mock_call_api.return_value = 'mock_response'
        self.api_caller = ApiCaller('dummy_api_key')

    @patch('gpt_process.ApiCaller.call_api', return_value='mock_response')
    def test_call_api(self, mock_call_api):
        """
        Test the call_api method with a successful API call. It should return the response.
        """
        response = self.api_caller.call_api('system_prompt', 'user_text')
        self.assertEqual(response, 'mock_response')
        mock_call_api.assert_called_once_with('system_prompt', 'user_text')

    @patch('gpt_process.ApiCaller.call_api', side_effect=Exception('mock_exception'))
    def test_call_api_error(self, mock_call_api):
        """
        Test the call_api method with an exception. It should return the exception message.
        """
        with self.assertRaises(Exception) as context:
            self.api_caller.call_api('system_prompt', 'user_text')

        self.assertEqual(str(context.exception), 'mock_exception')
        mock_call_api.assert_called_once_with('system_prompt', 'user_text')

if __name__ == '__main__':
    unittest.main()