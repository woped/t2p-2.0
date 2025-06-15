from flask import Flask, request, jsonify
from gpt_process import ApiCaller
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
import time
from pythonjsonlogger import jsonlogger
import logging
import os

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
# app.config['APPLICATION_ROOT'] = '/t2p-2.0'

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

@app.route('/api_call', methods=['POST'])
def api_call():
    start_time = time.time()
    try:
        data = request.json
        logger.info("API call received", extra={"text_length": len(data.get('text', ''))})
        
        # Check for missing 'text' or 'api_key' in the request data
        if 'text' not in data or 'api_key' not in data:
            missing = []
            if 'text' not in data:
                missing.append('text')
            if 'api_key' not in data:
                missing.append('api_key')
            logger.warning("Missing data in request", extra={"missing_fields": missing})
            REQUEST_COUNT.labels(method='POST', endpoint='/api_call', status='400').inc()
            return jsonify({"error": f"Missing data for: {', '.join(missing)}"}), 400
        
        # Create the ApiCaller class object with the extracted API key
        ac = ApiCaller(api_key=data['api_key'])

        # Process the data using the run method of ApiCaller
        api_start_time = time.time()
        result = ac.conversion_pipeline(data['text'])
        API_CALL_DURATION.observe(time.time() - api_start_time)

        # If the result contains an error message, return it with a 500 status code
        if "{'error': {'message':" in result:
            logger.error("API call failed", extra={"result": result})
            REQUEST_COUNT.labels(method='POST', endpoint='/api_call', status='500').inc()
            return jsonify({"error": result}), 500

        logger.info("API call successful")
        REQUEST_COUNT.labels(method='POST', endpoint='/api_call', status='200').inc()
        return jsonify({"result": result}), 200
    
    except Exception as e:
        logger.error("Unexpected error in API call", extra={"error": str(e)})
        REQUEST_COUNT.labels(method='POST', endpoint='/api_call', status='500').inc()
        return jsonify({"error": str(e)}), 500
    finally:
        REQUEST_LATENCY.labels(method='POST', endpoint='/api_call').observe(time.time() - start_time)

@app.route('/_/_/echo')
def echo():
    start_time = time.time()
    try:
        REQUEST_COUNT.labels(method='GET', endpoint='/_/_/echo', status='200').inc()
        return jsonify(success=True)
    finally:
        REQUEST_LATENCY.labels(method='GET', endpoint='/_/_/echo').observe(time.time() - start_time)

if __name__ == '__main__':
    app.run(host='0.0.0.0')
