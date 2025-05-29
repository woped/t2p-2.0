from flask import Flask, request, jsonify
import requests

from app.backend.gpt_process import ApiCaller
from app.backend.modeltransformer import ModelTransformer

app = Flask(__name__)

@app.route("/test_connection", methods=["GET"])
def test():
    try:
        return jsonify("Successful"), 200
    except Exception as e:
        app.logger.error(f"Error in /test_connection: {str(e)}")
        return jsonify({"error": "Test connection failed.", "details": str(e)}), 500


@app.route("/api_call", methods=["POST"])
def api_call():
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

        # Call the transform method, which might raise exceptions
        transformed_xml = transformer.transform(result_bpmn)

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
            error_payload["details"]["service_response"] = (
                e_http.response.json()
            )
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
                        "original_error": str(e_req), # Be cautious with exposing raw error strings
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
        ) # exc_info=True logs the stack trace
        return (
            jsonify(
                {
                    "error": "An unexpected internal server error occurred.",
                    "details": {"type": "InternalServerError", "message": str(e)},
                }
            ),
            500,
        )


@app.route("/_/_/echo")
def echo():
    return jsonify(success=True)


if __name__ == "__main__":
    # Basic logging configuration for development
    # For production, use a more robust logging setup (e.g., Gunicorn's logger)
    import logging

    logging.basicConfig(level=logging.INFO)
    app.run(host="0.0.0.0", port=5000) # Default port is 5000
