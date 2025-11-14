from flask import jsonify, send_from_directory, current_app
import time, logging, os
from app.api import api_bp
from app.__init__ import REQUEST_COUNT, REQUEST_LATENCY
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from app.backend.handlecall import HandleCall

@api_bp.route('/example')
def example_route():
    return "This is an example route"

@api_bp.route('/api/swagger.yaml')
def serve_swagger_yaml():
    return send_from_directory(os.path.dirname(__file__), 'swagger.yaml')

@api_bp.route('/metrics')
def metrics():
    return generate_latest(), 200, {'Content-Type': CONTENT_TYPE_LATEST}

@api_bp.route('/test_connection', methods=['GET'])
def test():
    start_time = time.time()
    try:
        logging.info("Test connection endpoint called")
        REQUEST_COUNT.labels(method='GET', endpoint='/test_connection', status='200').inc()
        return jsonify("Successful"), 200
    except Exception as e:
        logging.error("Test connection failed", extra={"error": str(e)})
        REQUEST_COUNT.labels(method='GET', endpoint='/test_connection', status='500').inc()
        return jsonify({"error": str(e)}), 500
    finally:
        REQUEST_LATENCY.labels(method='GET', endpoint='/test_connection').observe(time.time() - start_time)

@api_bp.route("/api_call", methods=["POST"])
def api_call():
    start_time = time.time()
    try:
        logging.info("API call received")
        REQUEST_COUNT.labels(method='POST', endpoint='/api_call', status='200').inc()
        return HandleCall.handle(current_app, {"direction": "pnmltobpmn"})
    except Exception as e:
        logging.error("API call failed", extra={"error": str(e)})
        REQUEST_COUNT.labels(method='POST', endpoint='/api_call', status='500').inc()
        return jsonify({"error": str(e)}), 500
    finally:
        REQUEST_LATENCY.labels(method='POST', endpoint='/api_call').observe(time.time() - start_time)

@api_bp.route("/generate_BPMN", methods=["POST"])
def generateBPMN():
    return HandleCall.handle(current_app, {"direction": "pnmltobpmn"})

@api_bp.route("/generate_PNML", methods=["POST"])
def generatePNML():
    start_time = time.time()
    try:
        logging.info("Generate PNML endpoint called")
        REQUEST_COUNT.labels(method='POST', endpoint='/generate_PNML', status='200').inc()
        return HandleCall.handle(current_app, {"direction": "bpmntopnml"})
    except Exception as e:
        logging.error("Generate PNML failed", extra={"error": str(e)})
        REQUEST_COUNT.labels(method='POST', endpoint='/generate_PNML', status='500').inc()
        return jsonify({"error": str(e)}), 500
    finally:
        REQUEST_LATENCY.labels(method='POST', endpoint='/generate_PNML').observe(time.time() - start_time)

@api_bp.route("/_/_/echo")
def echo():
    start_time = time.time()
    try:
        REQUEST_COUNT.labels(method='GET', endpoint='/_/_/echo', status='200').inc()
        return jsonify(success=True)
    finally:
        REQUEST_LATENCY.labels(method='GET', endpoint='/_/_/echo').observe(time.time() - start_time)

