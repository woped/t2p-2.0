import json
import logging

from app.backend import config
import requests
from json2xml import json2xml

# Configure a logger for this module
logger = logging.getLogger(__name__)


class ModelTransformer:
    def __init__(self):
        self.transformer_url = config.TRANSFORMER_BASE_URL + "/transform"

    def transform(self, bpmn_xml, directionParams=None):
        """
        Transform the BPMN XML using the transformer model.
        :param bpmn_xml: The BPMN XML to transform.
        :return: The transformed BPMN XML.
        :raises requests.exceptions.HTTPError: If the transformer service returns a 4xx or 5xx error.
        :raises requests.exceptions.RequestException: For other network or request-related issues.
        """
        xml = bpmn_xml

        query_params = directionParams
        request_body_data = {"bpmn": xml}

        try:
            response = requests.post(
                self.transformer_url,
                params=query_params,
                data=request_body_data,  # Use 'data' for form-urlencoded body
                timeout=60,  # Set a reasonable timeout (e.g., 60 seconds)
            )

            # Raise an HTTPError for bad responses (4xx or 5xx)
            response.raise_for_status()

            # If successful, the response content is the transformed XML
            response_json = json.loads(response.text)
            logger.debug(response_json["pnml"])
            return response_json["pnml"]

        except requests.exceptions.HTTPError as e_http:
            # Log the detailed error from the transformer service
            logger.error(
                f"Transformer service returned HTTP error: {e_http.response.status_code} "
                f"- URL: {e_http.request.url} - Response: {e_http.response.text}"
            )
            # Re-raise the exception to be handled by the caller (app.py)
            raise
        except requests.exceptions.RequestException as e_req:
            # Handle other errors that occurred during the request (e.g., network issues, timeout)
            logger.error(
                f"RequestException during transformation: {str(e_req)} - URL: {self.transformer_url}"
            )
            # Re-raise the exception to be handled by the caller (app.py)
            raise
