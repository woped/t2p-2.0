import requests
from flask import jsonify, request
from .gpt_process import ApiCaller
from .modeltransformer import ModelTransformer


class HandleCall:
    """
    This class is responsible for handling calls to the backend.
    It processes the request and returns a response.
    """

    def handle(app, directionParams):
        try:
            data = request.json
            if not data:
                return jsonify({"error": "Request body must be JSON."}), 400

            missing_fields = []
            if "text" not in data:
                missing_fields.append("text")
            if "api_key" not in data:
                missing_fields.append("api_key")

            if missing_fields:
                return (
                    jsonify(
                        {"error": f"Missing data for: {', '.join(missing_fields)}"}
                    ),
                    400,
                )

            ac = ApiCaller(api_key=data["api_key"])
            transformer = ModelTransformer()

            # This part could also raise exceptions.
            # Consider specific error handling for conversion_pipeline if needed.
            result_bpmn = ac.conversion_pipeline(data["text"])
            if directionParams.get("direction") == "pnmltobpmn":
                return jsonify({"result": result_bpmn}), 200

            transformed_xml = transformer.transform(result_bpmn, directionParams)
            return jsonify({"result": transformed_xml}), 200

        except requests.exceptions.HTTPError as e_http:
            # Error response from the transformer service (4xx or 5xx)
            app.logger.error(
                f"Transformation service HTTPError in /api_call: "
                f"Status: {e_http.response.status_code}, Response: {e_http.response.text}"
            )
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

            return jsonify(error_payload), 500

        except requests.exceptions.RequestException as e_req:
            # Network error or other issue connecting to the transformer service
            app.logger.error(
                f"Transformation service RequestException in /api_call: {str(e_req)}"
            )
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
        except Exception as e:
            # Catch-all for other unexpected errors (e.g., in ApiCaller, or other logic)
            app.logger.error(
                f"An unexpected error occurred in /api_call: {str(e)}",
                exc_info=True,
            )  # exc_info=True logs the stack trace
            return (
                jsonify(
                    {
                        "error": "An unexpected internal server error occurred.",
                        "details": {"type": "InternalServerError", "message": str(e)},
                    }
                ),
                500,
            )
