from flask import Flask, jsonify
from handlecall import HandleCall

app = Flask(__name__)


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
