import json
import requests
from backend.xml_parser import json_to_bpmn
from backend.config import PROMPTING_STRATEGIE, API_HOST, API_PORT, LLM_PROVIDER


class ApiCaller:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = f"https://{API_HOST}"
        if API_PORT != 443:
            self.base_url += f":{API_PORT}"

        self.endpoint = self._resolve_endpoint(LLM_PROVIDER)
        self.flask_app_url = f"{self.base_url}/llm-api-connector/{self.endpoint}"

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
            "prompting_strategie": PROMPTING_STRATEGIE
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
                return f"An error occurred: {response.text}"
        except Exception as e:
            return f"An exception occurred: {str(e)}"

    def conversion_pipeline(self, process_description):
        try:
            json_data = self.generate_bpmn_json(process_description)
            xml_data = json_to_bpmn(json.loads(json_data))
            return xml_data
        except Exception as e:
            return f"An error occurred: {str(e)}"

    def generate_bpmn_json(self, user_description):
        json_output = self.call_api(user_text=user_description)
        return json_output
