from unittest.mock import patch
from app.backend.connector_client import ConnectorError, ConnectorClientError
from tests.sample_models import RAW_MODEL_JSON


AUTH = {"Authorization": "Bearer secret-token"}
BODY = {"text": "describe a process", "provider": "openai", "model": "gpt-4o"}


# --- /v2/generate ---------------------------------------------------------


@patch("app.api.routes.ConnectorClient")
def test_v2_generate_bpmn_success(mock_cc, client):
    mock_cc.return_value.generate.return_value = RAW_MODEL_JSON

    resp = client.post("/v2/generate/bpmn", json=BODY, headers=AUTH)

    assert resp.status_code == 200
    assert "<definitions" in resp.get_json()["result"]
    # The request is translated into the connector call: header forwarded,
    # text -> user_text, provider/model passed through.
    mock_cc.return_value.generate.assert_called_once_with(
        authorization="Bearer secret-token",
        user_text="describe a process",
        provider="openai",
        model="gpt-4o",
    )


@patch("app.api.routes.ModelTransformer")
@patch("app.api.routes.ConnectorClient")
def test_v2_generate_pnml_success(mock_cc, mock_mt, client):
    mock_cc.return_value.generate.return_value = RAW_MODEL_JSON
    mock_mt.return_value.transform.return_value = "PNML"

    resp = client.post("/v2/generate/pnml", json=BODY, headers=AUTH)

    assert resp.status_code == 200
    assert resp.get_json() == {"result": "PNML"}
    mock_mt.return_value.transform.assert_called_once()


@patch("app.api.routes.ModelTransformer")
@patch("app.api.routes.ConnectorClient")
def test_v2_generate_pnml_transform_error_returns_500(mock_cc, mock_mt, client):
    import requests

    mock_cc.return_value.generate.return_value = RAW_MODEL_JSON
    mock_mt.return_value.transform.side_effect = requests.exceptions.RequestException(
        "transformer down"
    )

    resp = client.post("/v2/generate/pnml", json=BODY, headers=AUTH)

    assert resp.status_code == 500
    assert resp.get_json()["error"]["code"] == "transform_error"


# Request validation is owned by the connector (the authoritative validator);
# the orchestrator forwards the request and relays the connector's response. The
# following tests assert that forward-and-relay behavior rather than a duplicate
# guard in this layer.


@patch("app.api.routes.ConnectorClient")
def test_v2_generate_forwards_missing_auth_and_relays_401(mock_cc, client):
    # No Authorization header: the orchestrator forwards an empty header and
    # relays the connector's 401 instead of short-circuiting locally.
    mock_cc.return_value.generate.side_effect = ConnectorClientError(
        401,
        {
            "error": {
                "code": "unauthorized",
                "message": "Missing or malformed Authorization header.",
            }
        },
    )

    resp = client.post("/v2/generate/bpmn", json=BODY)

    assert resp.status_code == 401
    assert resp.get_json()["error"]["code"] == "unauthorized"
    mock_cc.return_value.generate.assert_called_once_with(
        authorization="",
        user_text="describe a process",
        provider="openai",
        model="gpt-4o",
    )


@patch("app.api.routes.ConnectorClient")
def test_v2_generate_forwards_missing_field_and_relays_400(mock_cc, client):
    # A missing field is forwarded (as None) and the connector's 400 is relayed.
    mock_cc.return_value.generate.side_effect = ConnectorClientError(
        400,
        {
            "error": {
                "code": "invalid_request",
                "message": "Missing or empty field(s): model.",
            }
        },
    )
    body = {"text": "x", "provider": "openai"}  # no model

    resp = client.post("/v2/generate/bpmn", json=body, headers=AUTH)

    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "invalid_request"
    mock_cc.return_value.generate.assert_called_once_with(
        authorization="Bearer secret-token",
        user_text="x",
        provider="openai",
        model=None,
    )


@patch("app.api.routes.ConnectorClient")
def test_v2_generate_non_json_is_forwarded_as_empty(mock_cc, client):
    # A non-JSON body is normalized to empty fields and forwarded; the connector
    # rejects it and the orchestrator relays that error.
    mock_cc.return_value.generate.side_effect = ConnectorClientError(
        400,
        {
            "error": {
                "code": "invalid_request",
                "message": "Missing or empty field(s): user_text, provider, model.",
            }
        },
    )

    resp = client.post(
        "/v2/generate/bpmn",
        data="not json",
        headers={**AUTH, "Content-Type": "text/plain"},
    )

    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "invalid_request"
    mock_cc.return_value.generate.assert_called_once_with(
        authorization="Bearer secret-token",
        user_text=None,
        provider=None,
        model=None,
    )


@patch("app.api.routes.ConnectorClient")
def test_v2_generate_connector_error_returns_500(mock_cc, client):
    mock_cc.return_value.generate.side_effect = ConnectorError("down")

    resp = client.post("/v2/generate/bpmn", json=BODY, headers=AUTH)

    assert resp.status_code == 500
    assert resp.get_json()["error"]["code"] == "upstream_error"


@patch("app.api.routes.ConnectorClient")
def test_v2_generate_relays_connector_4xx(mock_cc, client):
    # A 4xx from the connector (its semantic validation) is relayed to the
    # client with its status and body intact, not masked as 500.
    mock_cc.return_value.generate.side_effect = ConnectorClientError(
        400, {"error": {"code": "invalid_provider", "message": "Unknown provider 'x'."}}
    )

    resp = client.post("/v2/generate/bpmn", json=BODY, headers=AUTH)

    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "invalid_provider"


@patch("app.api.routes.ConnectorClient")
def test_v2_generate_relays_422_model_unprocessable_with_details(mock_cc, client):
    # Validation exhaustion in the connector is a 422 (unprocessable input, not
    # an upstream failure). As a 4xx it is relayed verbatim, so the friendly
    # message AND the structured `details` reach the client unchanged.
    body = {
        "error": {
            "code": "model_unprocessable",
            "message": "Could not generate a valid process model from the description.",
            "details": [
                "Node 'task_3' has multiple outgoing flows; a split must use a gateway."
            ],
        }
    }
    mock_cc.return_value.generate.side_effect = ConnectorClientError(422, body)

    resp = client.post("/v2/generate/bpmn", json=BODY, headers=AUTH)

    assert resp.status_code == 422
    relayed = resp.get_json()["error"]
    assert relayed["code"] == "model_unprocessable"
    assert relayed["details"] == body["error"]["details"]


@patch("app.api.routes.ConnectorClient")
def test_v2_generate_relays_4xx_status_when_error_body_is_malformed(mock_cc, client):
    # The connector returned a 4xx but its body is not the expected
    # {"error": {...}} shape. The status is still relayed, with a synthesized
    # invalid_request body rather than passing the unusable body through.
    mock_cc.return_value.generate.side_effect = ConnectorClientError(
        400, {"unexpected": "shape"}
    )

    resp = client.post("/v2/generate/bpmn", json=BODY, headers=AUTH)

    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "invalid_request"


@patch("app.api.routes.ConnectorClient")
def test_v2_generate_unexpected_error_returns_internal_error_500(mock_cc, client):
    # An error that is none of the known connector/model failures must not leak
    # as an unhandled 500; it is mapped to a structured internal_error.
    mock_cc.return_value.generate.side_effect = RuntimeError("boom")

    resp = client.post("/v2/generate/bpmn", json=BODY, headers=AUTH)

    assert resp.status_code == 500
    assert resp.get_json()["error"]["code"] == "internal_error"


@patch("app.api.routes.ConnectorClient")
def test_v2_generate_invalid_payload_returns_502_upstream_error(mock_cc, client):
    # The connector replied, but payload decoding/building failed locally:
    # surfaced as an upstream integration error.
    mock_cc.return_value.generate.return_value = "not a json model"

    resp = client.post("/v2/generate/bpmn", json=BODY, headers=AUTH)

    assert resp.status_code == 502
    assert resp.get_json()["error"]["code"] == "upstream_error"


# --- correlation id -------------------------------------------------------


@patch("app.api.routes.ConnectorClient")
def test_v2_response_echoes_request_id_header(mock_cc, client):
    # Every response carries an X-Request-ID, minted when the client sends none.
    mock_cc.return_value.generate.return_value = RAW_MODEL_JSON

    resp = client.post("/v2/generate/bpmn", json=BODY, headers=AUTH)

    assert resp.status_code == 200
    assert resp.headers.get("X-Request-ID")


@patch("app.api.routes.ConnectorClient")
def test_v2_honours_inbound_request_id(mock_cc, client):
    # A client-supplied X-Request-ID is honoured and echoed back unchanged.
    mock_cc.return_value.generate.return_value = RAW_MODEL_JSON

    resp = client.post(
        "/v2/generate/bpmn",
        json=BODY,
        headers={**AUTH, "X-Request-ID": "client-supplied-id"},
    )

    assert resp.headers.get("X-Request-ID") == "client-supplied-id"


@patch("app.api.routes.ConnectorClient")
def test_v2_error_body_carries_matching_request_id(mock_cc, client):
    # The error body's request_id matches the X-Request-ID header, so a caller
    # can pin the failure in the logs from either.
    mock_cc.return_value.generate.side_effect = ConnectorError("down")

    resp = client.post(
        "/v2/generate/bpmn", json=BODY, headers={**AUTH, "X-Request-ID": "trace-42"}
    )

    assert resp.status_code == 500
    assert resp.get_json()["error"]["request_id"] == "trace-42"
    assert resp.headers.get("X-Request-ID") == "trace-42"


# --- /v2/models -----------------------------------------------------------


@patch("app.api.routes.ConnectorClient")
def test_v2_models_success(mock_cc, client):
    models = [{"provider": "openai", "model": "gpt-4o"}]
    mock_cc.return_value.list_models.return_value = models

    resp = client.get("/v2/models")

    assert resp.status_code == 200
    assert resp.get_json() == {"models": models}


@patch("app.api.routes.ConnectorClient")
def test_v2_models_connector_error_returns_500(mock_cc, client):
    mock_cc.return_value.list_models.side_effect = ConnectorError("down")

    resp = client.get("/v2/models")

    assert resp.status_code == 500
    assert resp.get_json()["error"]["code"] == "upstream_error"


# --- /v2/health -----------------------------------------------------------


def test_v2_health_ok(client):
    resp = client.get("/v2/health")

    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}


# --- deprecation headers --------------------------------------------------


def test_deprecated_test_connection_has_headers(client):
    resp = client.get("/test_connection")

    assert resp.status_code == 200
    assert resp.get_json() == "Successful"
    assert resp.headers.get("Deprecation") == "@1780272000"
    assert resp.headers.get("Sunset") == "Tue, 01 Dec 2026 00:00:00 GMT"
    assert resp.headers.get("Link") == '</api/swagger.yaml>; rel="deprecation"'


def test_operational_echo_is_not_deprecated(client):
    resp = client.get("/_/_/echo")

    assert resp.status_code == 200
    assert resp.get_json() == {"success": True}
    assert "Deprecation" not in resp.headers


@patch("app.api.routes.ConnectorClient")
def test_legacy_bpmn_uses_default_model_and_builds_bpmn(mock_cc, client):
    mock_cc.return_value.generate.return_value = RAW_MODEL_JSON

    resp = client.post(
        "/generate_BPMN", json={"text": "describe a process", "api_key": "secret-token"}
    )

    assert resp.status_code == 200
    assert "<definitions" in resp.get_json()["result"]
    assert resp.headers.get("Deprecation") == "@1780272000"
    mock_cc.return_value.generate.assert_called_once_with(
        authorization="Bearer secret-token",
        user_text="describe a process",
        provider="openai",
        model="gpt-4o",
    )


@patch("app.api.routes.ModelTransformer")
@patch("app.api.routes.ConnectorClient")
def test_legacy_pnml_uses_new_flow_and_preserves_response(mock_cc, mock_mt, client):
    mock_cc.return_value.generate.return_value = RAW_MODEL_JSON
    mock_mt.return_value.transform.return_value = "<pnml>legacy</pnml>"

    resp = client.post(
        "/generate_PNML", json={"text": "describe a process", "api_key": "secret-token"}
    )

    assert resp.status_code == 200
    assert resp.get_json() == {"result": "<pnml>legacy</pnml>"}
    mock_mt.return_value.transform.assert_called_once()
