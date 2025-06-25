import json
import requests
from xml_parser import json_to_bpmn
from config import API_HOST, API_PORT


class ApiCaller:
    def __init__(self, api_key, prompting_strategie=None, llm_provider=None):
        self.api_key = api_key
        self.prompting_strategie = prompting_strategie
        self.llm_provider = llm_provider

        # Use HTTPS only if standard secure port 443 is used
        protocol = "https" if API_PORT == 443 else "http"
        self.base_url = f"{protocol}://{API_HOST}:{API_PORT}"

        # Determine endpoint for the selected LLM provider
        self.endpoint = self._resolve_endpoint(self.llm_provider)
        self.flask_app_url = f"{self.base_url}/{self.endpoint}"

    def _resolve_endpoint(self, provider):
        match provider:
            case "openai":
                return "call_openai"
            case "gemini":
                return "call_gemini"
            case _:
                raise ValueError(f"Unsupported LLM provider: {provider}")

    def call_api(self, user_text):
        data_payload = {
            "api_key": self.api_key,
            "user_text": user_text,
            "prompting_strategie": self.prompting_strategie
        }
        headers = {
            "Content-Type": "application/json"
        }
        try:
            response = requests.post(self.flask_app_url, headers=headers, json=data_payload)
            if response.status_code == 200:
                response_data = response.json()
                return response_data['message']
            else:
                return f"An error occurred: {response.status_code} - {response.text}"
        except Exception as e:
            return f"An exception occurred: {str(e)}"

    def conversion_pipeline(self, process_description):
        try:
            json_data = self.generate_bpmn_json(process_description)
            xml_data = json_to_bpmn(json.loads(json_data))
            return xml_data
        except Exception as e:
            return f"An error occurred during conversion: {str(e)}"

    def generate_bpmn_json(self, user_description):
        return self.call_api(user_text=user_description)
