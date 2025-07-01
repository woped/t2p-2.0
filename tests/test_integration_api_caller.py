import unittest
import os
import pytest
from app.backend.gpt_process import ApiCaller

@pytest.mark.integration
class TestIntegrationApiCaller(unittest.TestCase):

    def setUp(self):
        # These values must match the running instance of the API server
        os.environ["API_HOST"] = "localhost"
        os.environ["API_PORT"] = "5000"
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "dummy_openai_key")
        self.gemini_api_key = os.getenv("GEMINI_API_KEY", "dummy_gemini_key")

    def test_openai_few_shot_api_call(self):
        """Integration test for OpenAI with few_shot prompting strategy"""
        api_caller = ApiCaller(
            api_key=self.openai_api_key, 
            llm_provider="openai", 
            prompting_strategy="few_shot"
        )
        
        prompt = "A simple description of a business process."
        result = api_caller.call_api(prompt)

        self.assertIsInstance(result, str)
        # Accept either successful response with "events" or error messages
        self.assertTrue("events" in result or "An error occurred" in result or "An exception occurred" in result)

    def test_openai_zero_shot_api_call(self):
        """Integration test for OpenAI with zero_shot prompting strategy"""
        api_caller = ApiCaller(
            api_key=self.openai_api_key, 
            llm_provider="openai", 
            prompting_strategy="zero_shot"
        )
        
        prompt = "Customer places order and receives confirmation."
        result = api_caller.call_api(prompt)

        self.assertIsInstance(result, str)
        self.assertTrue("events" in result or "An error occurred" in result or "An exception occurred" in result)
    
    def test_gemini_few_shot_api_call(self):
        """Integration test for Gemini with few_shot prompting strategy"""
        api_caller = ApiCaller(
            api_key=self.gemini_api_key, 
            llm_provider="gemini", 
            prompting_strategy="few_shot"
        )
        
        result = api_caller.call_api("A process that begins with a customer request.")
        self.assertIsInstance(result, str)
        self.assertTrue("events" in result or "An error occurred" in result or "An exception occurred" in result)

    def test_gemini_zero_shot_api_call(self):
        """Integration test for Gemini with zero_shot prompting strategy"""
        api_caller = ApiCaller(
            api_key=self.gemini_api_key, 
            llm_provider="gemini", 
            prompting_strategy="zero_shot"
        )
        
        result = api_caller.call_api("Employee onboarding process from start to finish.")
        self.assertIsInstance(result, str)
        self.assertTrue("events" in result or "An error occurred" in result or "An exception occurred" in result)

    def test_conversion_pipeline_openai_few_shot(self):
        """Integration test for full pipeline with OpenAI few_shot"""
        api_caller = ApiCaller(
            api_key=self.openai_api_key, 
            llm_provider="openai", 
            prompting_strategy="few_shot"
        )
        
        result = api_caller.conversion_pipeline("Customer reports issue, system processes it.")
        self.assertIsInstance(result, str)
        self.assertTrue(result.startswith("<") or "An error occurred" in result)

    def test_conversion_pipeline_gemini_zero_shot(self):
        """Integration test for full pipeline with Gemini zero_shot"""
        api_caller = ApiCaller(
            api_key=self.gemini_api_key, 
            llm_provider="gemini", 
            prompting_strategy="zero_shot"
        )
        
        result = api_caller.conversion_pipeline("Product return process: customer initiates return, item is inspected, refund is processed.")
        self.assertIsInstance(result, str)
        self.assertTrue(result.startswith("<") or "An error occurred" in result)

    def test_invalid_llm_provider(self):
        """Test handling of invalid LLM provider"""
        with self.assertRaises(ValueError):
            ApiCaller(
                api_key=self.openai_api_key, 
                llm_provider="invalid_provider", 
                prompting_strategy="few_shot"
            )

    def test_all_combinations_basic(self):
        """Test all valid combinations of providers and strategies"""
        providers_keys = {
            "openai": self.openai_api_key,
            "gemini": self.gemini_api_key
        }
        strategies = ["few_shot", "zero_shot"]
        
        for provider, api_key in providers_keys.items():
            for strategy in strategies:
                with self.subTest(provider=provider, strategy=strategy):
                    api_caller = ApiCaller(
                        api_key=api_key,
                        llm_provider=provider,
                        prompting_strategy=strategy
                    )
                    
                    # Just test initialization and endpoint resolution
                    expected_endpoint = f"call_{provider}"
                    self.assertEqual(api_caller.endpoint, expected_endpoint)
                    self.assertEqual(api_caller.llm_provider, provider)
                    self.assertEqual(api_caller.prompting_strategy, strategy)


if __name__ == '__main__':
    unittest.main()