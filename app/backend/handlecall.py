import requests
import logging
import time
from flask import jsonify, request
from .gpt_process import ApiCaller
from .modeltransformer import ModelTransformer


class HandleCall:
    """
    This class is responsible for handling calls to the backend.
    It processes the request and returns a response.
    """

    # Module-level logger
    logger = logging.getLogger(__name__)

    def handle(app, directionParams):
        start_time = time.time()
        HandleCall.logger.info(
            "HandleCall.handle invoked",
            extra={
                "endpoint": request.path if request else None,
                "direction": directionParams.get("direction") if directionParams else None,
            },
        )
        try:
            data = request.json
            if not data:
                HandleCall.logger.warning(
                    "Request body missing or not JSON",
                    extra={"content_type": request.headers.get("Content-Type")},
                )
                return jsonify({"error": "Request body must be JSON."}), 400

            missing_fields = []
            if "text" not in data:
                missing_fields.append("text")
            if "api_key" not in data:
                missing_fields.append("api_key")

            if missing_fields:
                HandleCall.logger.warning(
                    "Missing required fields",
                    extra={"missing": missing_fields},
                )
                return (
                    jsonify(
                        {"error": f"Missing data for: {', '.join(missing_fields)}"}
                    ),
                    400,
                )

            # Avoid logging secrets; only log masked characteristics
            masked_key = f"{data['api_key'][:4]}...len={len(data['api_key'])}"
            HandleCall.logger.debug(
                "Creating ApiCaller and ModelTransformer",
                extra={
                    "text_length": len(data.get("text", "")),
                    "api_key_masked": masked_key,
                },
            )
            ac = ApiCaller(api_key=data["api_key"])
            transformer = ModelTransformer()

            # This part could also raise exceptions.
            # Consider specific error handling for conversion_pipeline if needed.
            HandleCall.logger.info("Starting conversion_pipeline (text -> BPMN XML)")
            result_bpmn = ac.conversion_pipeline(data["text"])
            HandleCall.logger.info(
                "conversion_pipeline completed",
                extra={
                    "bpmn_length": len(result_bpmn) if isinstance(result_bpmn, str) else None
                },
            )
            if directionParams.get("direction") == "pnmltobpmn":
                HandleCall.logger.info("Returning BPMN result (pnmltobpmn mode)")
                HandleCall.logger.debug(
                    "HandleCall duration",
                    extra={"duration_seconds": round(time.time() - start_time, 4)},
                )
                return jsonify({"result": result_bpmn}), 200

            HandleCall.logger.info("Starting transformer.transform (BPMN -> PNML)")
            transformed_xml = transformer.transform(result_bpmn, directionParams)
            HandleCall.logger.info(
                "Transformation completed",
                extra={
                    "pnml_length": len(transformed_xml) if isinstance(transformed_xml, str) else None
                },
            )
            HandleCall.logger.debug(
                "HandleCall duration",
                extra={"duration_seconds": round(time.time() - start_time, 4)},
            )
            return jsonify({"result": transformed_xml}), 200

        except requests.exceptions.HTTPError as e_http:
            # Error response from the transformer service (4xx or 5xx)
            app.logger.error(
                f"Transformation service HTTPError in /api_call: "
                f"Status: {e_http.response.status_code}, Response: {e_http.response.text}"
            )
            HandleCall.logger.exception("HTTPError raised by transformer service")
            error_payload = {
                "error": "BPMN to PNML transformation failed.",
                "details": {
                    "type": "TransformerServiceError",
                    "message": "The transformation service responded with an error.",
                    "service_status_code": e_http.response.status_code,
                },
            }
            # Try to include parsed error from transformer if it's JSON
            try:
                error_payload["details"]["service_response"] = e_http.response.json()
            except ValueError:
                error_payload["details"]["service_response"] = e_http.response.text

            HandleCall.logger.debug(
                "HandleCall duration (HTTPError)",
                extra={"duration_seconds": round(time.time() - start_time, 4)},
            )
            return jsonify(error_payload), 500

        except requests.exceptions.RequestException as e_req:
            # Network error or other issue connecting to the transformer service
            app.logger.error(
                f"Transformation service RequestException in /api_call: {str(e_req)}"
            )
            HandleCall.logger.exception("RequestException contacting transformer service")
            return (
                jsonify(
                    {
                        "error": "Failed to communicate with the BPMN transformation service.",
                        "details": {
                            "type": "NetworkError",
                            "message": "Could not connect to or get a response from the transformation service.",
                            "original_error": str(
                                e_req
                            ),  # Be cautious with exposing raw error strings
                        },
                    }
                ),
                500,
            )
        except ValueError as e_val:
            # JSON parsing errors or validation errors from LLM responses
            HandleCall.logger.exception("ValueError - likely invalid JSON from LLM API")
            return (
                jsonify(
                    {
                        "error": "Invalid response from LLM API.",
                        "details": {
                            "type": "LLMResponseError",
                            "message": "The LLM API returned a response that could not be parsed or processed.",
                            "original_error": str(e_val),
                        },
                    }
                ),
                500,
            )
        except RuntimeError as e_runtime:
            # Runtime errors from LLM API connector (connection/HTTP errors)
            HandleCall.logger.exception("RuntimeError - LLM API connector issue")
            return (
                jsonify(
                    {
                        "error": "LLM API connector error.",
                        "details": {
                            "type": "LLMConnectorError",
                            "message": "Failed to successfully communicate with the LLM API connector.",
                            "original_error": str(e_runtime),
                        },
                    }
                ),
                500,
            )
        except Exception as e:
            # Catch-all for other unexpected errors (e.g., in ApiCaller, or other logic)
            app.logger.error(
                f"An unexpected error occurred in /api_call: {str(e)}",
                exc_info=True,
            )  # exc_info=True logs the stack trace
            HandleCall.logger.exception("Unhandled exception in HandleCall.handle")
            return (
                jsonify(
                    {
                        "error": "An unexpected internal server error occurred.",
                        "details": {"type": "InternalServerError", "message": str(e)},
                    }
                ),
                500,
            )
        finally:
            # Ensure we always record the overall duration in logs
            HandleCall.logger.debug(
                "HandleCall total duration (finally)",
                extra={"duration_seconds": round(time.time() - start_time, 4)},
            )
