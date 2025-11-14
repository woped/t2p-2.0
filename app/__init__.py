import logging
from flask import Flask, request, jsonify, send_from_directory
from .backend.gpt_process import ApiCaller
from config import Config
from flask_swagger_ui import get_swaggerui_blueprint
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from pythonjsonlogger import jsonlogger

# Application-level Prometheus metrics
REQUEST_COUNT = Counter('http_requests_total', 'Total HTTP requests', ['method', 'endpoint', 'status'])
REQUEST_LATENCY = Histogram('http_request_duration_seconds', 'HTTP request latency', ['method', 'endpoint'])
API_CALL_DURATION = Histogram('api_call_duration_seconds', 'API call processing duration')

def create_app(config_class=Config):
    app = Flask(__name__)

    # Logging Setup
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    werkzeug_logger = logging.getLogger('werkzeug')
    werkzeug_logger.setLevel(logging.INFO)

    class MetricsFilter(logging.Filter):
        def filter(self, record):
            if record.name == "werkzeug":
                return "/metrics" not in record.getMessage()
            try:
                return not request.path.startswith('/metrics')
            except RuntimeError:
                return True

    metrics_filter = MetricsFilter()
    console_handler = logging.StreamHandler()
    console_handler.addFilter(metrics_filter)
    console_formatter = jsonlogger.JsonFormatter(
        '%(asctime)s %(levelname)s %(name)s %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    werkzeug_logger.addHandler(console_handler)

    @app.before_request
    def suppress_metrics_logging():
        if request.path == '/metrics':
            app.logger.disabled = True

    @app.after_request
    def restore_logging(response):
        app.logger.disabled = False
        return response

    from app.api import api_bp
    app.register_blueprint(api_bp, url_prefix='/api')

    # Swagger UI
    SWAGGER_URL = '/swagger'
    API_URL = '/api/swagger.yaml'
    swaggerui_blueprint = get_swaggerui_blueprint(SWAGGER_URL, API_URL)
    app.register_blueprint(swaggerui_blueprint, url_prefix=SWAGGER_URL)

    return app
