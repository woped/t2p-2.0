import unittest
import os
from backend.gpt_process import ApiCaller

class TestApiCaller(unittest.TestCase):

    def setUp(self):
        # These values must match the running instance of the API server
        os.environ["API_HOST"] = "localhost"
        os.environ["API_PORT"] = "5000"
        os.environ["LLM_PROVIDER"] = "openai"  
        os.environ["PROMPTING_STRATEGIE"] = "few_shot"

        self.api_key = os.getenv("API_KEY", "dummy-key")  
        self.api_caller = ApiCaller(api_key=self.api_key)

    def test_openai_api_call(self):
        """Integration test for real /call_openai endpoint"""
        os.environ["LLM_PROVIDER"] = "openai"
        result = self.api_caller.call_api("A simple description of a business process.")
        self.assertIsInstance(result, str)
        self.assertTrue("events" in result or "An error occurred" in result)

    def test_gemini_api_call(self):
        """Integration test for real /call_gemini endpoint"""
        os.environ["LLM_PROVIDER"] = "gemini"
        result = self.api_caller.call_api("A process that begins with a customer request.")
        self.assertIsInstance(result, str)
        self.assertTrue("events" in result or "An error occurred" in result)

    def test_conversion_pipeline_real_api(self):
        """Runs the full pipeline including JSON → BPMN XML conversion (real LLM + parser)"""
        result = self.api_caller.conversion_pipeline("Customer reports issue, system processes it.")
        self.assertIsInstance(result, str)
        self.assertTrue(result.startswith("<") or "An error occurred" in result)


if __name__ == '__main__':
    unittest.main()
