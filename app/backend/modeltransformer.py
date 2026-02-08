import json
import logging
import time
import requests
from json2xml import json2xml
from flask import current_app

# Configure a logger for this module
logger = logging.getLogger(__name__)


class ModelTransformer:
    def __init__(self):
        self.transformer_url = current_app.config['T2P_TRANSFORMER_BASE_URL'] + "/transform"
        logger.debug("ModelTransformer initialized", extra={"transformer_url": self.transformer_url})

    def transform(self, bpmn_xml, directionParams=None):
        """
        Transform the BPMN XML using the transformer model.
        :param bpmn_xml: The BPMN XML to transform.
        :return: The transformed BPMN XML.
        :raises requests.exceptions.HTTPError: If the transformer service returns a 4xx or 5xx error.
        :raises requests.exceptions.RequestException: For other network or request-related issues.
        """
        start_time = time.time()
        logger.info(
            "Starting transformation",
            extra={
                "direction": directionParams.get("direction") if directionParams else None,
                "bpmn_xml_length": len(bpmn_xml) if isinstance(bpmn_xml, str) else None
            }
        )
        
        query_params = directionParams

        try:
            logger.debug(
                "Sending transformation request",
                extra={
                    "url": self.transformer_url,
                    "params": query_params,
                    "timeout": 60
                }
            )
            
            # Read the bpmn_output.xml file as a string
            with open('bpmn_output.xml', 'r', encoding='utf-8') as f:
                bpmn_content = f.read()
                logger.debug(
                    "Reading bpmn_output.xml file as string",
                    extra={
                        "filename": "bpmn_output.xml",
                        "content_length": len(bpmn_content)
                    }
                )
            
            # Send the BPMN content as x-www-form-urlencoded
            form_data = {"bpmn": bpmn_content}
            headers = {"Content-Type": "application/x-www-form-urlencoded"}
            
            logger.debug(
                "Sending data as x-www-form-urlencoded",
                extra={
                    "field_name": "bpmn",
                    "content_type": "application/x-www-form-urlencoded",
                    "data_length": len(bpmn_content)
                }
            )
            
            response = requests.post(
                self.transformer_url,
                params=query_params,
                data=form_data,  # Use 'data' for x-www-form-urlencoded
                headers=headers,
                timeout=60,  # Set a reasonable timeout (e.g., 60 seconds)
                verify=False,  # Disable SSL certificate verification
            )
            
            duration = round(time.time() - start_time, 4)
            logger.info(
                "Transformation service responded",
                extra={
                    "status": response.status_code,
                    "duration_seconds": duration
                }
            )

            # Raise an HTTPError for bad responses (4xx or 5xx)
            response.raise_for_status()

            # If successful, the response content is the transformed XML
            response_json = json.loads(response.text)
            pnml_output = response_json["pnml"]
            
            logger.info(
                "Transformation completed successfully",
                extra={
                    "pnml_length": len(pnml_output) if isinstance(pnml_output, str) else None,
                    "total_duration_seconds": round(time.time() - start_time, 4)
                }
            )
            logger.debug("PNML output preview", extra={"pnml_preview": pnml_output[:200] if isinstance(pnml_output, str) else None})
            return pnml_output

        except FileNotFoundError as e_file:
            # Handle case where bpmn_output.bpmn file does not exist
            duration = round(time.time() - start_time, 4)
            logger.error(
                f"BPMN output file not found: {str(e_file)}",
                extra={
                    "duration_seconds": duration,
                    "error_type": type(e_file).__name__
                }
            )
            logger.exception("FileNotFoundError during transformation")
            raise
        except requests.exceptions.HTTPError as e_http:
            # Log the detailed error from the transformer service
            duration = round(time.time() - start_time, 4)
            logger.error(
                f"Transformer service returned HTTP error: {e_http.response.status_code} "
                f"- URL: {e_http.request.url} - Response: {e_http.response.text}",
                extra={
                    "status_code": e_http.response.status_code,
                    "url": e_http.request.url,
                    "duration_seconds": duration,
                    "response_preview": e_http.response.text[:500] if e_http.response.text else None
                }
            )
            logger.exception("HTTPError during transformation")
            # Re-raise the exception to be handled by the caller (app.py)
            raise
        except requests.exceptions.RequestException as e_req:
            # Handle other errors that occurred during the request (e.g., network issues, timeout)
            duration = round(time.time() - start_time, 4)
            logger.error(
                f"RequestException during transformation: {str(e_req)} - URL: {self.transformer_url}",
                extra={
                    "url": self.transformer_url,
                    "duration_seconds": duration,
                    "error_type": type(e_req).__name__
                }
            )
            logger.exception("RequestException during transformation")
            # Re-raise the exception to be handled by the caller (app.py)
            raise
