import os

from flask import Flask, jsonify, send_from_directory
from flask_swagger_ui import get_swaggerui_blueprint

from handlecall import HandleCall

app = Flask(__name__)

SWAGGER_URL = '/swagger'
API_URL = '/backend/swagger.yaml'
swaggerui_blueprint = get_swaggerui_blueprint(SWAGGER_URL, API_URL)
app.register_blueprint(swaggerui_blueprint, url_prefix=SWAGGER_URL)

# Serve the swagger.yaml file explicitly
@app.route('/backend/swagger.yaml')
def serve_swagger_yaml():
    return send_from_directory(os.path.dirname(__file__), 'swagger.yaml')


@app.route("/test_connection", methods=["GET"])
def test():
    try:
        return jsonify("Successful"), 200
    except Exception as e:
        app.logger.error(f"Error in /test_connection: {str(e)}")
        return jsonify({"error": "Test connection failed.", "details": str(e)}), 500


# The endpoint will be deprecated in the future.
# For different format use /generate_bpmn and generate_pnml endpoints.
@app.route("/api_call", methods=["POST"])
def api_call():
    return HandleCall.handle(app, {"direction": "bpmntopnml"})


@app.route("/generate_BPMN", methods=["POST"])
def generateBPMN():
    return HandleCall.handle(app, {"direction": "bpmntopnml"})


@app.route("/generate_PNML", methods=["POST"])
def generatePNML():
    return HandleCall.handle(app, {"direction": "pnmltobpmn"})


@app.route("/_/_/echo")
def echo():
    return jsonify(success=True)


if __name__ == "__main__":
    # Basic logging configuration for development
    # For production, use a more robust logging setup (e.g., Gunicorn's logger)
    import logging

    logging.basicConfig(level=logging.INFO)
    app.run(host="0.0.0.0", port=5000)  # Default port is 5000
