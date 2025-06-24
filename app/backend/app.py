from flask import Flask, request, jsonify, send_from_directory
from gpt_process import ApiCaller
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
import time
from pythonjsonlogger import jsonlogger
import logging
import os
from handlecall import HandleCall
from flask_swagger_ui import get_swaggerui_blueprint

# Prometheus Metriken
REQUEST_COUNT = Counter('http_requests_total', 'Total HTTP requests', ['method', 'endpoint', 'status'])
REQUEST_LATENCY = Histogram('http_request_duration_seconds', 'HTTP request latency', ['method', 'endpoint'])
API_CALL_DURATION = Histogram('api_call_duration_seconds', 'API call processing duration')

# Logging Setup
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Console handler with JSON format
console_handler = logging.StreamHandler()
console_formatter = jsonlogger.JsonFormatter(
    '%(asctime)s %(levelname)s %(name)s %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
console_handler.setFormatter(console_formatter)
logger.addHandler(console_handler)

app = Flask(__name__)

@app.before_request
def suppress_metrics_logging():
    """Suppress logging for /metrics endpoint to avoid log spam."""
    if request.path == '/metrics':
        # Disable logging for this request
        app.logger.disabled = True

@app.after_request
def restore_logging(response):
    """Restore logging after request is processed."""
    app.logger.disabled = False
    return response

SWAGGER_URL = '/swagger'
API_URL = '/api/swagger.yaml'
swaggerui_blueprint = get_swaggerui_blueprint(SWAGGER_URL, API_URL)
app.register_blueprint(swaggerui_blueprint, url_prefix=SWAGGER_URL)

# Serve the swagger.yaml file explicitly
@app.route('/api/swagger.yaml')
def serve_swagger_yaml():
    return send_from_directory(os.path.dirname(__file__), 'swagger.yaml')

@app.route('/metrics')
def metrics():
    return generate_latest(), 200, {'Content-Type': CONTENT_TYPE_LATEST}

@app.route('/test_connection', methods=['GET'])
def test():
    start_time = time.time()
    try:
        logger.info("Test connection endpoint called")
        REQUEST_COUNT.labels(method='GET', endpoint='/test_connection', status='200').inc()
        return jsonify("Successful"), 200
    except Exception as e:
        logger.error("Test connection failed", extra={"error": str(e)})
        REQUEST_COUNT.labels(method='GET', endpoint='/test_connection', status='500').inc()
        return jsonify({"error": str(e)}), 500
    finally:
        REQUEST_LATENCY.labels(method='GET', endpoint='/test_connection').observe(time.time() - start_time)

# The endpoint will be deprecated in the future.
# For different format use /generate_bpmn and generate_pnml endpoints.
@app.route("/api_call", methods=["POST"])
def api_call():
    start_time = time.time()
    try:
        logger.info("API call received")
        REQUEST_COUNT.labels(method='POST', endpoint='/api_call', status='200').inc()
        return HandleCall.handle(app, {"direction": "bpmntopnml"})
    except Exception as e:
        logger.error("API call failed", extra={"error": str(e)})
        REQUEST_COUNT.labels(method='POST', endpoint='/api_call', status='500').inc()
        return jsonify({"error": str(e)}), 500
    finally:
        REQUEST_LATENCY.labels(method='POST', endpoint='/api_call').observe(time.time() - start_time)


@app.route("/generate_BPMN", methods=["POST"])
def generateBPMN():
    return HandleCall.handle(app, {"direction": "bpmntopnml"})


@app.route("/generate_PNML", methods=["POST"])
def generatePNML():
    start_time = time.time()
    try:
        logger.info("Generate PNML endpoint called")
        REQUEST_COUNT.labels(method='POST', endpoint='/generate_PNML', status='200').inc()
        return HandleCall.handle(app, {"direction": "pnmltobpmn"})
    except Exception as e:
        logger.error("Generate PNML failed", extra={"error": str(e)})
        REQUEST_COUNT.labels(method='POST', endpoint='/generate_PNML', status='500').inc()
        return jsonify({"error": str(e)}), 500
    finally:
        REQUEST_LATENCY.labels(method='POST', endpoint='/generate_PNML').observe(time.time() - start_time)


@app.route("/_/_/echo")
def echo():
    start_time = time.time()
    try:
        REQUEST_COUNT.labels(method='GET', endpoint='/_/_/echo', status='200').inc()
        return jsonify(success=True)
    finally:
        REQUEST_LATENCY.labels(method='GET', endpoint='/_/_/echo').observe(time.time() - start_time)

if __name__ == "__main__":
    # Basic logging configuration for development
    # For production, use a more robust logging setup (e.g., Gunicorn's logger)
    import logging

    logging.basicConfig(level=logging.INFO)
    app.run(host="0.0.0.0", port=5000)  # Default port is 5000
