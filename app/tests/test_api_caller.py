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

        self.api_key = os.getenv("API_KEY", "dummy_api_key")  
        self.api_caller = ApiCaller(api_key=self.api_key)


    def test_openai_api_call(self):
        """Integration test for real /call_openai endpoint"""
        os.environ["LLM_PROVIDER"] = "openai"
        result = self.api_caller.call_api("The customer fills out the form, then a clerk checks the information, and finally the application is approved.")

        # Debug output to inspect API response
        print("\n====== API Response ======")
        print(result)
        print("==========================\n")

        self.assertIsInstance(result, str)
        self.assertTrue("events" in result or "An error occurred" in result)

    
    def test_gemini_api_call(self):
        """Integration test for real /call_gemini endpoint"""
        os.environ["LLM_PROVIDER"] = "gemini"
        result = self.api_caller.call_api("The customer fills out the form, then a clerk checks the information, and finally the application is approved.")
        
        # Debug output to inspect API response
        print("\n====== API Response ======")
        print(result)
        print("==========================\n")

        self.assertIsInstance(result, str)
        self.assertTrue("events" in result or "An error occurred" in result)
    

if __name__ == '__main__':
    unittest.main()
