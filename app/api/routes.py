import json
import logging
import os
import time
from functools import wraps

import requests
from flask import jsonify, make_response, request, send_from_directory
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.api import api_bp
from app.__init__ import REQUEST_COUNT, REQUEST_LATENCY
from app.backend.connector_client import (
    ConnectorClient,
    ConnectorClientError,
    ConnectorError,
)
from app.backend.modeltransformer import ModelTransformer
from app.backend.xml_parser import json_to_bpmn

# Module-level logger for routes
logger = logging.getLogger(__name__)

_DEPRECATION_LINK = '</api/swagger.yaml>; rel="deprecation"'
_LEGACY_DEPRECATION_DATE = "@1780272000"  # 2026-06-01T00:00:00Z
_LEGACY_SUNSET_DATE = "Tue, 01 Dec 2026 00:00:00 GMT"
_REMOVED_API_CALL_SUNSET_DATE = "Wed, 31 Dec 2025 23:59:59 GMT"
_LEGACY_PROVIDER = "openai"
_LEGACY_MODEL = "gpt-4o"


def deprecated(view):
    """Attach migration headers while a legacy endpoint remains functional."""

    @wraps(view)
    def wrapper(*args, **kwargs):
        response = make_response(view(*args, **kwargs))
        response.headers.setdefault("Deprecation", _LEGACY_DEPRECATION_DATE)
        response.headers.setdefault("Sunset", _LEGACY_SUNSET_DATE)
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


def _removed_api_call_response():
    """Respond for the legacy endpoint whose previously announced sunset elapsed."""
    REQUEST_COUNT.labels(
        method=request.method, endpoint=request.path, status="410"
    ).inc()
    response = make_response(
        _error_response(
            410,
            "deprecated",
            "This endpoint was removed after its sunset date; use the /v1 API.",
        )
    )
    response.headers["Sunset"] = _REMOVED_API_CALL_SUNSET_DATE
    response.headers["Link"] = _DEPRECATION_LINK
    return response


def _raw_response_to_bpmn(raw_response):
    """Convert the connector's LLM JSON response to BPMN XML."""
    if not isinstance(raw_response, str):
        raise ValueError("LLM API connector response must be text.")

    content = raw_response.strip()
    if content.startswith("<"):
        return content
    if content.startswith("```"):
        content = content.split("\n", 1)[1] if "\n" in content else content[3:]
        if content.endswith("```"):
            content = content.rsplit("```", 1)[0]
        content = content.strip()

    try:
        return json_to_bpmn(json.loads(content))
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError("LLM API connector returned invalid BPMN JSON.") from exc


def _generate_bpmn(authorization, text, provider, model):
    raw_response = ConnectorClient().generate(
        authorization=authorization,
        user_text=text,
        provider=provider,
        model=model,
    )
    return _raw_response_to_bpmn(raw_response)


def _transform_to_pnml(bpmn_xml):
    return ModelTransformer().transform(bpmn_xml, {"direction": "bpmntopnml"})


def _legacy_generate(target):
    """Preserve the unversioned generation contract during its migration period."""
    start_time = time.time()
    endpoint_label = request.path
    status = "200"
    try:
        data = request.get_json(silent=True)
        if not data:
            status = "400"
            return jsonify({"error": "Request body must be JSON."}), 400

        missing = [field for field in ("text", "api_key") if field not in data]
        if missing:
            status = "400"
            return jsonify({"error": f"Missing data for: {', '.join(missing)}"}), 400

        bpmn_xml = _generate_bpmn(
            authorization=f"Bearer {data['api_key']}",
            text=data["text"],
            provider=_LEGACY_PROVIDER,
            model=_LEGACY_MODEL,
        )
        result = _transform_to_pnml(bpmn_xml) if target == "pnml" else bpmn_xml
        return jsonify({"result": result}), 200
    except requests.exceptions.RequestException as exc:
        status = "500"
        logger.error("Legacy transformation failed", extra={"error": str(exc)})
        return jsonify({"error": "BPMN to PNML transformation failed."}), 500
    except ConnectorError as exc:
        status = "500"
        logger.error("Legacy connector call failed", extra={"error": str(exc)})
        return jsonify({"error": "LLM API connector error."}), 500
    except (ConnectorClientError, ValueError) as exc:
        status = "500"
        logger.error("Legacy generation failed", extra={"error": str(exc)})
        return jsonify({"error": "Invalid response from LLM API."}), 500
    finally:
        duration = time.time() - start_time
        REQUEST_COUNT.labels(
            method="POST", endpoint=endpoint_label, status=status
        ).inc()
        REQUEST_LATENCY.labels(method="POST", endpoint=endpoint_label).observe(duration)


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
        REQUEST_COUNT.labels(
            method="GET", endpoint="/test_connection", status="200"
        ).inc()
        return jsonify("Successful"), 200
    finally:
        REQUEST_LATENCY.labels(method="GET", endpoint="/test_connection").observe(
            time.time() - start_time
        )


@api_bp.route("/api_call", methods=["POST"])
def api_call():
    return _removed_api_call_response()


@api_bp.route("/generate_bpmn", methods=["POST"])  # preferred lowercase alias
@api_bp.route(
    "/generate_BPMN", methods=["POST"]
)  # legacy/case-variant for compatibility
@deprecated
def generateBPMN():
    return _legacy_generate("bpmn")


@api_bp.route("/generate_pnml", methods=["POST"])  # preferred lowercase alias
@api_bp.route(
    "/generate_PNML", methods=["POST"]
)  # legacy/case-variant for compatibility
@deprecated
def generatePNML():
    return _legacy_generate("pnml")


# --- v1 API ---------------------------------------------------------------


def _v1_generate(target):
    """Receive a v1 generate request, validate it, and produce the requested model.

    The connector returns an LLM BPMN structure which this service converts to
    BPMN XML. ``target == "pnml"`` then transforms that XML to PNML.
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

        bpmn_xml = _generate_bpmn(
            authorization=authorization,
            text=data["text"],
            provider=data["provider"],
            model=data["model"],
        )

        if target == "pnml":
            try:
                result = _transform_to_pnml(bpmn_xml)
            except requests.exceptions.RequestException as e:
                status = "500"
                logger.error(
                    "BPMN to PNML transformation failed",
                    extra={"endpoint": endpoint_label, "error": str(e)},
                )
                return _error_response(
                    500,
                    "transform_error",
                    "The BPMN to PNML transformation service failed.",
                )
        else:
            result = bpmn_xml

        logger.info("v1 generate completed", extra={"endpoint": endpoint_label})
        return jsonify({"result": result}), 200

    except ConnectorClientError as e:
        # The connector rejected the request (e.g. invalid provider/model);
        # relay its status and error body to the client unchanged.
        status = str(e.status_code)
        logger.info(
            "Relaying connector client error",
            extra={"endpoint": endpoint_label, "status": e.status_code},
        )
        if isinstance(e.error_body, dict) and "error" in e.error_body:
            return jsonify(e.error_body), e.status_code
        return _error_response(
            e.status_code,
            "invalid_request",
            "The request was rejected by the LLM API connector.",
        )
    except ConnectorError as e:
        status = "500"
        logger.error(
            "Connector call failed",
            extra={"endpoint": endpoint_label, "error": str(e)},
        )
        return _error_response(
            500, "upstream_error", "The LLM API connector is unavailable."
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
    return _v1_generate("bpmn")


@api_bp.route("/v1/generate/pnml", methods=["POST"])
def v1_generate_pnml():
    return _v1_generate("pnml")


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
def echo():
    start_time = time.time()
    try:
        REQUEST_COUNT.labels(method="GET", endpoint="/_/_/echo", status="200").inc()
        return jsonify(success=True), 200
    finally:
        REQUEST_LATENCY.labels(method="GET", endpoint="/_/_/echo").observe(
            time.time() - start_time
        )
