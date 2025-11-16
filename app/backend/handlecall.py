import requests
from flask import jsonify, request
from gpt_process import ApiCaller
from modeltransformer import ModelTransformer


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
                    jsonify({"error": f"Missing data for: {', '.join(missing_fields)}"}), 400
                )

          
            approach = data.get("approach")
            llm_provider = data.get("llm_provider", "openai")  

            ac = ApiCaller(
                api_key=data["api_key"],
                prompting_strategy=approach,
                llm_provider=llm_provider
            )

            transformer = ModelTransformer()
            result_bpmn = ac.conversion_pipeline(data["text"])

            direction = directionParams.get("direction")
            
            if direction == "pnmltobpmn":
                return jsonify({"result": result_bpmn}), 200
            
            transformed_xml = transformer.transform(result_bpmn, directionParams)
            return jsonify({"result": transformed_xml}), 200

        except requests.exceptions.HTTPError as e_http:
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
                    "service_response": e_http.response.text
                },
            }

            return jsonify(error_payload), 500

        except requests.exceptions.RequestException as e_req:
            app.logger.error(
                f"Transformation service RequestException in /api_call: {str(e_req)}"
            )
            return jsonify({
                "error": "Failed to communicate with the BPMN transformation service.",
                "details": {
                    "type": "NetworkError",
                    "message": "Could not connect to or get a response from the transformation service.",
                    "original_error": str(e_req),
                },
            }), 500

        except Exception as e:
            app.logger.error(f"An unexpected error occurred in /api_call: {str(e)}", exc_info=True)
            return jsonify({
                "error": "An unexpected internal server error occurred.",
                "details": {"type": "InternalServerError", "message": str(e)},
            }), 500