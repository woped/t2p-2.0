import requests
import json
import logging
import time
from .xml_parser import json_to_bpmn
from flask import current_app

# Module-level logger for this module
logger = logging.getLogger(__name__)

class ApiCaller:
    def __init__(self, api_key):
        self.api_key = api_key
        self.llm_api_connector_url = current_app.config['T2P_LLM_API_CONNECTOR_URL'] + "/call_openai"
        # Do not log secrets; only log the target URL
        logger.debug("ApiCaller initialized", extra={"connector_url": self.llm_api_connector_url})

    def call_api(self, system_prompt, user_text):
        start_time = time.time()
        # Construct the data payload to send to the Flask API
        data_payload = {
            "api_key": self.api_key,
            "system_prompt": system_prompt,
            "user_text": user_text
        }
        headers = {
            "Content-Type": "application/json"
        }
        try:
            # Make a POST request to the other API
            logger.info("Calling LLM API connector", extra={"url": self.llm_api_connector_url})
            response = requests.post(self.llm_api_connector_url, headers=headers, json=data_payload)
            duration = round(time.time() - start_time, 4)
            logger.info("LLM API connector responded", extra={"status": response.status_code, "duration_seconds": duration})
            
            # Raise exception for non-200 responses
            if response.status_code != 200:
                logger.error("LLM API connector error", extra={"status": response.status_code, "response_preview": response.text[:500]})
                raise RuntimeError(f"LLM API connector returned status {response.status_code}: {response.text}")
            
            # Process the response from your Flask API
            response_data = response.json()
            # Log size/type but not full content
            msg = response_data.get('message')
            if not msg:
                logger.error("LLM API response missing 'message' field", extra={"response_keys": list(response_data.keys())})
                raise ValueError("LLM API response does not contain 'message' field")
            
            logger.debug("LLM API message received", extra={"message_type": type(msg).__name__, "message_length": len(msg) if isinstance(msg, str) else None})
            return msg
            
        except requests.exceptions.RequestException as e:
            logger.exception("Network exception during call to LLM API connector")
            raise RuntimeError(f"Failed to connect to LLM API connector: {str(e)}") from e
        except json.JSONDecodeError as e:
            logger.exception("Failed to parse JSON response from LLM API connector")
            raise ValueError(f"LLM API connector returned invalid JSON: {str(e)}") from e
        except Exception as e:
            logger.exception("Unexpected exception during call to LLM API connector")
            raise
            
    def conversion_pipeline(self, process_description):
        logger.info("Starting conversion pipeline", extra={"description_length": len(process_description) if isinstance(process_description, str) else None})
        start_time = time.time()
        try:
            json_data = self.generate_bpmn_json(process_description)
            logger.debug("BPMN JSON generated", extra={"json_length": len(json_data) if isinstance(json_data, str) else None})
            
            # Clean up the response - remove markdown code blocks if present
            if isinstance(json_data, str):
                json_data = json_data.strip()
                # Remove markdown code blocks (```json ... ``` or ``` ... ```)
                if json_data.startswith('```'):
                    logger.debug("Removing markdown code block wrapper from LLM response")
                    # Remove opening ```json or ```
                    json_data = json_data.split('\n', 1)[1] if '\n' in json_data else json_data[3:]
                    # Remove closing ```
                    if json_data.endswith('```'):
                        json_data = json_data.rsplit('```', 1)[0]
                    json_data = json_data.strip()
                    logger.debug("Cleaned JSON", extra={"cleaned_preview": json_data[:200]})
            
            # Parse and validate JSON response
            try:
                json_obj = json.loads(json_data)
                logger.debug("JSON parsed successfully", extra={"keys": list(json_obj.keys()) if isinstance(json_obj, dict) else None})
            except json.JSONDecodeError as e:
                logger.error("Failed to parse BPMN JSON from LLM", extra={"json_preview": json_data[:500], "error": str(e)})
                raise ValueError(f"LLM returned invalid JSON: {str(e)}. Response preview: {json_data[:200]}") from e
            
            xml_data = json_to_bpmn(json_obj)
            logger.info("Conversion pipeline finished", extra={"duration_seconds": round(time.time() - start_time, 4), "xml_length": len(xml_data) if isinstance(xml_data, str) else None})
            return xml_data
        except Exception as e:
            logger.exception("Error in conversion pipeline")
            raise  


    def generate_bpmn_json(self, user_description):
        # Generate a prompt to transform detailed summary into JSON structure suitable for BPMN XML conversion
        logger.debug("Generating BPMN JSON prompt", extra={"description_length": len(user_description) if isinstance(user_description, str) else None})
        system_prompt = (
            """You are an assistant for breaking down complex process descriptions into BPMN 2.0 elements. Your task is to provide a detailed and accurate breakdown of the business process in a structured format. Ensure that the process flow is clearly delineated, and all decision points are systematically resolved as per BPMN standards.

                Details to include:

                Events:
                - Start Event: Describe the initial event that triggers the process.
                - End Event: Describe the final event that concludes the process.

                Tasks/Activities:
                - List all tasks and activities involved in the process along with a brief description of each.

                Gateways (Splitting/Joining Points):
                - Exclusive Gateways: Describe any points within the process where the flow can ONLY go in ONE direction, including the conditions that determine the direction the flow needs to take.
                - Parallel Gateways: Describe any points within the process where the flow MUST go in MULTIPLE directions.
                Note: Ensure each gateway opened in the process is correspondingly closed, exclusive splits must eventually meet in exclusive joins (with ending process within a direction of exclusive gateway being the only exception), and parallel splits must meet with parralel joins.

                Flows:
                - Sequence Flows: Detail all sequence flows, explaining how tasks and events are interconnected. Ensure accurate representation of the flow, maintaining the order of activities as described. Confirm that each element is connected with only two sequence flows, except for end events and start events, these have only one sequence flow. Flows arent allowed to bi-directional, so there has to be a check exclusive gateway if a recurring activity is needed to be done"""

            "Create a structured JSON output that conforms to the following schema suitable for BPMN XML conversion. "
            "CRITICAL: You MUST use valid JSON format with DOUBLE QUOTES for all keys and string values, NOT single quotes. "
            "Format the output as valid JSON with the following keys: \"events\", \"tasks\", \"gateways\", and \"flows\". "
            "Only return the raw JSON text - do NOT use markdown code blocks, backticks, or any other formatting. "
            "Each key should contain a list of elements, each with properties that define their roles in the BPMN diagram. "
            "For example, tasks should include \"id\", \"name\", and \"type\"; flows should include \"source\", \"target\", and \"type\"; "
            "and events should include \"id\", \"type\", and \"name\". Regard opening gateways as SPLITS and closing gateways as JOINS.\n\n"
            "Expected JSON structure example (only generate the relevant content, not all elements need to be used):\n\n"
            "{\n"
            "  \"events\": [\n"
            "    {\"id\": \"startEvent1\", \"type\": \"Start\", \"name\": \"\"},\n"
            "    {\"id\": \"endEvent1\", \"type\": \"End\", \"name\": \"\"}\n"
            "  ],\n"
            "  \"tasks\": [\n"
            "    {\"id\": \"task1\", \"type\": \"UserTask\", \"name\": \"Check Outage\"},\n"
            "    {\"id\": \"task2\", \"type\": \"ServiceTask\", \"name\": \"Inform Customer\"}\n"
            "  ],\n"
            "  \"gateways\": [\n"
            "    {\"id\": \"gateway1\", \"type\": \"ExclusiveGateway\", \"name\": \"Split1\"},\n"
            "    {\"id\": \"gateway2\", \"type\": \"ParallelGateway\", \"name\": \"ParallelSplit1\"}\n"
            "  ],\n"
            "  \"flows\": [\n"
            "    {\"id\": \"flow1\", \"type\": \"SequenceFlow\", \"source\": \"startEvent1\", \"target\": \"task1\"},\n"
            "    {\"id\": \"flow2\", \"type\": \"SequenceFlow\", \"source\": \"task1\", \"target\": \"gateway1\"},\n"
            "    {\"id\": \"flow3\", \"type\": \"SequenceFlow\", \"source\": \"gateway1\", \"target\": \"task2\"},\n"
            "    {\"id\": \"flow4\", \"type\": \"SequenceFlow\", \"source\": \"task2\", \"target\": \"endEvent1\"}\n"
            "  ]\n"
            "}\n\n"
            "IMPORTANT: Use DOUBLE QUOTES (\") for all JSON keys and string values. Do NOT use single quotes (').\n\n"
            f"Here is the process description again, for clarification: {user_description}"
        )
        # Call the 'run' method with the generated prompt and return the result
        json_output = self.call_api(system_prompt=system_prompt, user_text="")
        logger.debug("Received BPMN JSON from LLM API", extra={"json_length": len(json_output) if isinstance(json_output, str) else None})
        
        # Log preview of response for debugging (first 300 chars)
        if isinstance(json_output, str) and len(json_output) > 0:
            logger.debug("LLM response preview", extra={"preview": json_output[:300]})
        
        return json_output

