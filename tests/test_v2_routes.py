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
        prompting_strategy=None,
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
        prompting_strategy=None,
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
        prompting_strategy=None,
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
        prompting_strategy=None,
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
def test_v2_generate_relays_connector_429(mock_cc, client):
    mock_cc.return_value.generate.side_effect = ConnectorClientError(
        429,
        {
            "error": {
                "code": "rate_limited",
                "message": "Provider quota or rate limit exceeded.",
            }
        },
    )

    resp = client.post("/v2/generate/bpmn", json=BODY, headers=AUTH)

    assert resp.status_code == 429
    assert resp.get_json()["error"]["code"] == "rate_limited"


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
def test_v2_generate_invalid_model_returns_500(mock_cc, client):
    # The connector replied, but the model is unreadable: surfaced as
    # invalid_model rather than a generic internal error.
    mock_cc.return_value.generate.return_value = "not a json model"

    resp = client.post("/v2/generate/bpmn", json=BODY, headers=AUTH)

    assert resp.status_code == 500
    assert resp.get_json()["error"]["code"] == "invalid_model"


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
        prompting_strategy=None,
    )


@patch("app.api.routes.ConnectorClient")
def test_v2_generate_bpmn_forwards_few_shot_strategy(mock_cc, client):
    mock_cc.return_value.generate.return_value = RAW_MODEL_JSON

    resp = client.post(
        "/v2/generate/bpmn",
        json={**BODY, "prompting_strategy": "few_shot"},
        headers=AUTH,
    )

    assert resp.status_code == 200
    assert "<definitions" in resp.get_json()["result"]
    mock_cc.return_value.generate.assert_called_once_with(
        authorization="Bearer secret-token",
        user_text="describe a process",
        provider="openai",
        model="gpt-4o",
        prompting_strategy="few_shot",
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


# --- PNML connectivity validation -----------------------------------------


@patch("app.api.routes.validate_pnml_connectivity")
@patch("app.api.routes.ModelTransformer")
@patch("app.api.routes.ConnectorClient")
def test_v2_generate_pnml_runs_connectivity_validation(mock_cc, mock_mt, mock_validate, client):
    """validate_pnml_connectivity is called on the PNML returned by the transformer."""
    mock_cc.return_value.generate.return_value = RAW_MODEL_JSON
    mock_mt.return_value.transform.return_value = "<pnml>some net</pnml>"

    resp = client.post("/v2/generate/pnml", json=BODY, headers=AUTH)

    assert resp.status_code == 200
    mock_validate.assert_called_once()


@patch("app.api.routes.validate_pnml_connectivity")
@patch("app.api.routes.ModelTransformer")
@patch("app.api.routes.ConnectorClient")
def test_v2_generate_pnml_connectivity_failure_returns_invalid_model(
    mock_cc, mock_mt, mock_validate, client
):
    """A PnmlStructureError raised by the validator maps to an invalid_model 500 response."""
    from app.backend.xml_parser import PnmlStructureError

    mock_cc.return_value.generate.return_value = RAW_MODEL_JSON
    mock_mt.return_value.transform.return_value = "<pnml>bad net</pnml>"
    mock_validate.side_effect = PnmlStructureError(
        "PNML connectivity check failed: transition 't1' has no inbound arc."
    )

    resp = client.post("/v2/generate/pnml", json=BODY, headers=AUTH)

    assert resp.status_code == 500
    assert resp.get_json()["error"]["code"] == "invalid_model"
