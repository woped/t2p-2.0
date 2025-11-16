import logging
import os
from flask import Flask, request, jsonify, send_from_directory
from .backend.gpt_process import ApiCaller
from config import config
from flask_swagger_ui import get_swaggerui_blueprint
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST, REGISTRY
from pythonjsonlogger import jsonlogger


class _MetricProxy:
    """Proxy object that forwards attribute access to the app-registered metric.

    This allows modules to import REQUEST_COUNT (and others) at import-time while
    deferring the actual metric creation until create_app() runs.
    """
    def __init__(self, key):
        self._key = key

    def _get(self):
        from flask import current_app
        try:
            return current_app.extensions['metrics'][self._key]
        except Exception:
            raise RuntimeError(
                f"Metric '{self._key}' is not initialized. Call create_app() first or access via current_app.extensions['metrics']."
            )

    def __getattr__(self, name):
        return getattr(self._get(), name)

    def __call__(self, *args, **kwargs):
        return self._get()(*args, **kwargs)


# Expose proxy objects so other modules can import them safely before the app is created.
REQUEST_COUNT = _MetricProxy('REQUEST_COUNT')
REQUEST_LATENCY = _MetricProxy('REQUEST_LATENCY')
API_CALL_DURATION = _MetricProxy('API_CALL_DURATION')

def create_app(config_name=None):
    if config_name is None:
        config_name = os.environ.get('FLASK_CONFIG') or 'default'
    
    app = Flask(__name__)
    app.config.from_object(config[config_name])
    config[config_name].init_app(app)
    
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

    if app.config.get('TESTING'):
        # During tests on Windows, stdout/stderr can be invalid handles.
        # Use NullHandler to avoid noisy OSErrors from logging.
        logger.handlers = []
        werkzeug_logger.handlers = []
        null_handler = logging.NullHandler()
        logger.addHandler(null_handler)
        werkzeug_logger.addHandler(null_handler)
    else:
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
    app.register_blueprint(api_bp, url_prefix='')

    # Swagger UI
    SWAGGER_URL = '/swagger'
    API_URL = '/api/swagger.yaml'
    swaggerui_blueprint = get_swaggerui_blueprint(SWAGGER_URL, API_URL)
    app.register_blueprint(swaggerui_blueprint, url_prefix=SWAGGER_URL)

    # Create and register Prometheus metrics in the app context to avoid
    # duplicate registration when modules are imported multiple times.
    def _get_or_create(name, constructor, *args, **kwargs):
        existing = REGISTRY._names_to_collectors.get(name)
        if existing is not None:
            return existing
        return constructor(name, *args, **kwargs)

    metrics = {
        'REQUEST_COUNT': _get_or_create('http_requests_total', Counter, 'Total HTTP requests', ['method', 'endpoint', 'status']),
        'REQUEST_LATENCY': _get_or_create('http_request_duration_seconds', Histogram, 'HTTP request latency', ['method', 'endpoint']),
        'API_CALL_DURATION': _get_or_create('api_call_duration_seconds', Histogram, 'API call processing duration')
    }
    app.extensions = getattr(app, 'extensions', {})
    app.extensions['metrics'] = metrics

    return app
