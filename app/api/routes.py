from flask import jsonify, send_from_directory, current_app, request, make_response
import time, logging, os
from functools import wraps
from app.api import api_bp
from app.__init__ import REQUEST_COUNT, REQUEST_LATENCY
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from app.backend.handlecall import HandleCall
from app.backend.connector_client import ConnectorClient, ConnectorError

# Module-level logger for routes
logger = logging.getLogger(__name__)

# Deprecation signaling headers (RFC 8594) shared by the deprecated endpoints.
_DEPRECATION_SUNSET = "Wed, 31 Dec 2025 23:59:59 GMT"
_DEPRECATION_LINK = (
    '<https://woped.dhbw-karlsruhe.de/docs/migration>; rel="deprecation"'
)


def deprecated(view):
    """Attach deprecation signaling headers to a view's response."""

    @wraps(view)
    def wrapper(*args, **kwargs):
        response = make_response(view(*args, **kwargs))
        response.headers.setdefault("Deprecation", "true")
        response.headers.setdefault("Sunset", _DEPRECATION_SUNSET)
        response.headers.setdefault("Link", _DEPRECATION_LINK)
        return response

    return wrapper


def _error_response(status_code, code, message):
    """Build the standard v1 error body: {"error": {"code", "message"}}."""
    return jsonify({"error": {"code": code, "message": message}}), status_code


def _extract_bearer():
    """Return the Authorization header if it is a well-formed bearer token, else None."""
    auth = request.headers.get("Authorization", "")
    parts = auth.split()
    if len(parts) == 2 and parts[0].lower() == "bearer" and parts[1]:
        return auth
    return None


@api_bp.route("/example")
def example_route():
    logger.debug("Example route accessed")
    return "This is an example route"


@api_bp.route("/api/swagger.yaml")
def serve_swagger_yaml():
    logger.debug("Swagger YAML requested")
    return send_from_directory(os.path.dirname(__file__), "swagger.yaml")


@api_bp.route("/metrics")
def metrics():
    # Don't log metrics endpoint to avoid noise in logs
    return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}


@api_bp.route("/test_connection", methods=["GET"])
@deprecated
def test():
    start_time = time.time()
    try:
        logger.info(
            "Test connection endpoint called", extra={"client_ip": request.remote_addr}
        )
        REQUEST_COUNT.labels(
            method="GET", endpoint="/test_connection", status="200"
        ).inc()
        return jsonify("Successful"), 200
    except Exception as e:
        logger.error("Test connection failed", extra={"error": str(e)}, exc_info=True)
        REQUEST_COUNT.labels(
            method="GET", endpoint="/test_connection", status="500"
        ).inc()
        return jsonify({"error": str(e)}), 500
    finally:
        duration = time.time() - start_time
        REQUEST_LATENCY.labels(method="GET", endpoint="/test_connection").observe(
            duration
        )
        logger.debug(
            "Test connection completed", extra={"duration_seconds": round(duration, 4)}
        )


@api_bp.route("/api_call", methods=["POST"])
def api_call():
    start_time = time.time()
    try:
        logger.warning(
            "/api_call (DEPRECATED) endpoint called",
            extra={
                "client_ip": request.remote_addr,
                "content_type": request.headers.get("Content-Type"),
                "user_agent": request.headers.get("User-Agent"),
            },
        )
        # Mark as deprecated via response headers per IETF recommendations
        result = HandleCall.handle(current_app, {"direction": "pnmltobpmn"})

        response = make_response(result)
        # Deprecation signaling headers
        response.headers.setdefault("Deprecation", "true")  # boolean-style flag
        # Optional: set a sunset date (RFC 8594) when the endpoint will be removed
        response.headers.setdefault("Sunset", "Wed, 31 Dec 2025 23:59:59 GMT")
        # Optional: link to deprecation/migration docs
        response.headers.setdefault(
            "Link",
            '<https://woped.dhbw-karlsruhe.de/docs/migration>; rel="deprecation"',
        )

        status_code = getattr(response, "status_code", 200)
        REQUEST_COUNT.labels(
            method="POST", endpoint="/api_call", status=str(status_code)
        ).inc()
        logger.info(
            "API call completed", extra={"status": status_code, "deprecated": True}
        )
        return response
    except Exception as e:
        logger.error("API call failed", extra={"error": str(e)}, exc_info=True)
        REQUEST_COUNT.labels(method="POST", endpoint="/api_call", status="500").inc()
        return jsonify({"error": str(e)}), 500
    finally:
        duration = time.time() - start_time
        REQUEST_LATENCY.labels(method="POST", endpoint="/api_call").observe(duration)
        logger.debug(
            "API call duration", extra={"duration_seconds": round(duration, 4)}
        )


@api_bp.route("/generate_bpmn", methods=["POST"])  # preferred lowercase alias
@api_bp.route(
    "/generate_BPMN", methods=["POST"]
)  # legacy/case-variant for compatibility
@deprecated
def generateBPMN():
    start_time = time.time()
    endpoint_label = request.path
    try:
        logger.info(
            "Generate BPMN endpoint called",
            extra={
                "endpoint": endpoint_label,
                "client_ip": request.remote_addr,
                "content_type": request.headers.get("Content-Type"),
            },
        )
        RESPONSE_STATUS = "200"
        result = HandleCall.handle(current_app, {"direction": "pnmltobpmn"})
        # If HandleCall returns a tuple (response, status), reflect status in metrics
        if isinstance(result, tuple) and len(result) > 1:
            RESPONSE_STATUS = str(result[1])
        REQUEST_COUNT.labels(
            method="POST", endpoint=endpoint_label, status=RESPONSE_STATUS
        ).inc()
        logger.info("Generate BPMN completed", extra={"status": RESPONSE_STATUS})
        return result
    except Exception as e:
        logger.error(
            "Generate BPMN failed",
            extra={"error": str(e), "endpoint": endpoint_label},
            exc_info=True,
        )
        REQUEST_COUNT.labels(method="POST", endpoint=endpoint_label, status="500").inc()
        return jsonify({"error": str(e)}), 500
    finally:
        duration = time.time() - start_time
        REQUEST_LATENCY.labels(method="POST", endpoint=endpoint_label).observe(duration)
        logger.debug(
            "Generate BPMN duration",
            extra={"duration_seconds": round(duration, 4), "endpoint": endpoint_label},
        )


@api_bp.route("/generate_pnml", methods=["POST"])  # preferred lowercase alias
@api_bp.route(
    "/generate_PNML", methods=["POST"]
)  # legacy/case-variant for compatibility
@deprecated
def generatePNML():
    start_time = time.time()
    endpoint_label = request.path
    try:
        logger.info(
            "Generate PNML endpoint called",
            extra={
                "endpoint": endpoint_label,
                "client_ip": request.remote_addr,
                "content_type": request.headers.get("Content-Type"),
            },
        )
        result = HandleCall.handle(current_app, {"direction": "bpmntopnml"})
        RESPONSE_STATUS = "200"
        if isinstance(result, tuple) and len(result) > 1:
            RESPONSE_STATUS = str(result[1])
        REQUEST_COUNT.labels(
            method="POST", endpoint=endpoint_label, status=RESPONSE_STATUS
        ).inc()
        logger.info("Generate PNML completed", extra={"status": RESPONSE_STATUS})
        return result
    except Exception as e:
        logger.error(
            "Generate PNML failed",
            extra={"error": str(e), "endpoint": endpoint_label},
            exc_info=True,
        )
        REQUEST_COUNT.labels(method="POST", endpoint=endpoint_label, status="500").inc()
        return jsonify({"error": str(e)}), 500
    finally:
        duration = time.time() - start_time
        REQUEST_LATENCY.labels(method="POST", endpoint=endpoint_label).observe(duration)
        logger.debug(
            "Generate PNML duration",
            extra={"duration_seconds": round(duration, 4), "endpoint": endpoint_label},
        )


# --- v1 API ---------------------------------------------------------------


def _v1_generate():
    """Receive a v1 generate request, validate it, and forward it to the connector.

    BPMN and PNML diverge only in post-LLM processing, which is future work; in
    this phase both endpoints forward identically and return the raw response.
    """
    start_time = time.time()
    endpoint_label = request.path
    status = "200"
    try:
        authorization = _extract_bearer()
        if authorization is None:
            status = "401"
            return _error_response(
                401, "unauthorized", "Missing or malformed bearer token."
            )

        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            status = "400"
            return _error_response(400, "invalid_request", "Request body must be JSON.")

        missing = [f for f in ("text", "provider", "model") if not data.get(f)]
        if missing:
            status = "400"
            return _error_response(
                400,
                "invalid_request",
                f"Missing or empty field(s): {', '.join(missing)}.",
            )

        raw_response = ConnectorClient().generate(
            authorization=authorization,
            user_text=data["text"],
            provider=data["provider"],
            model=data["model"],
        )
        logger.info("v1 generate completed", extra={"endpoint": endpoint_label})
        return jsonify({"result": raw_response}), 200

    except ConnectorError as e:
        status = "500"
        logger.error(
            "Connector call failed",
            extra={"endpoint": endpoint_label, "error": str(e)},
        )
        return _error_response(
            500, "upstream_error", "The LLM API connector could not be reached."
        )
    except Exception:
        status = "500"
        logger.exception("Unexpected error in v1 generate")
        return _error_response(500, "internal_error", "An unexpected error occurred.")
    finally:
        duration = time.time() - start_time
        REQUEST_COUNT.labels(
            method="POST", endpoint=endpoint_label, status=status
        ).inc()
        REQUEST_LATENCY.labels(method="POST", endpoint=endpoint_label).observe(duration)


@api_bp.route("/v1/generate/bpmn", methods=["POST"])
def v1_generate_bpmn():
    return _v1_generate()


@api_bp.route("/v1/generate/pnml", methods=["POST"])
def v1_generate_pnml():
    return _v1_generate()


@api_bp.route("/v1/models", methods=["GET"])
def v1_models():
    start_time = time.time()
    status = "200"
    try:
        models = ConnectorClient().list_models()
        return jsonify({"models": models}), 200
    except ConnectorError as e:
        status = "500"
        logger.error("Failed to fetch models from connector", extra={"error": str(e)})
        return _error_response(
            500, "upstream_error", "The LLM API connector could not be reached."
        )
    except Exception:
        status = "500"
        logger.exception("Unexpected error in v1 models")
        return _error_response(500, "internal_error", "An unexpected error occurred.")
    finally:
        duration = time.time() - start_time
        REQUEST_COUNT.labels(method="GET", endpoint="/v1/models", status=status).inc()
        REQUEST_LATENCY.labels(method="GET", endpoint="/v1/models").observe(duration)


@api_bp.route("/v1/health", methods=["GET"])
def v1_health():
    REQUEST_COUNT.labels(method="GET", endpoint="/v1/health", status="200").inc()
    return jsonify({"status": "ok"}), 200


@api_bp.route("/_/_/echo")
@deprecated
def echo():
    start_time = time.time()
    try:
        logger.debug("Echo endpoint called", extra={"client_ip": request.remote_addr})
        REQUEST_COUNT.labels(method="GET", endpoint="/_/_/echo", status="200").inc()
        return jsonify(success=True)
    finally:
        duration = time.time() - start_time
        REQUEST_LATENCY.labels(method="GET", endpoint="/_/_/echo").observe(duration)
        logger.debug("Echo completed", extra={"duration_seconds": round(duration, 4)})
