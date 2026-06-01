from unittest.mock import patch
from app.backend.connector_client import ConnectorError, ConnectorClientError


AUTH = {"Authorization": "Bearer secret-token"}
BODY = {"text": "describe a process", "provider": "openai", "model": "gpt-4o"}
RAW_MODEL_JSON = """{
  "events": [
    {"id": "start", "type": "startEvent", "name": "Start"},
    {"id": "end", "type": "endEvent", "name": "End"}
  ],
  "tasks": [],
  "gateways": [],
  "flows": [
    {"id": "flow", "type": "sequenceFlow", "source": "start", "target": "end"}
  ]
}"""


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
    mock_cc.return_value.generate.return_value = "<bpmn>BPMN</bpmn>"
    mock_mt.return_value.transform.return_value = "PNML"

    resp = client.post("/v2/generate/pnml", json=BODY, headers=AUTH)

    assert resp.status_code == 200
    assert resp.get_json() == {"result": "PNML"}
    mock_mt.return_value.transform.assert_called_once_with(
        "<bpmn>BPMN</bpmn>", {"direction": "bpmntopnml"}
    )


@patch("app.api.routes.ModelTransformer")
@patch("app.api.routes.ConnectorClient")
def test_v2_generate_pnml_transform_error_returns_500(mock_cc, mock_mt, client):
    import requests

    mock_cc.return_value.generate.return_value = "<bpmn>BPMN</bpmn>"
    mock_mt.return_value.transform.side_effect = requests.exceptions.RequestException(
        "transformer down"
    )

    resp = client.post("/v2/generate/pnml", json=BODY, headers=AUTH)

    assert resp.status_code == 500
    assert resp.get_json()["error"]["code"] == "transform_error"


@patch("app.api.routes.ConnectorClient")
def test_v2_generate_missing_auth_returns_401(mock_cc, client):
    resp = client.post("/v2/generate/bpmn", json=BODY)

    assert resp.status_code == 401
    assert resp.get_json()["error"]["code"] == "unauthorized"
    mock_cc.return_value.generate.assert_not_called()


@patch("app.api.routes.ConnectorClient")
def test_v2_generate_malformed_auth_returns_401(mock_cc, client):
    resp = client.post(
        "/v2/generate/bpmn", json=BODY, headers={"Authorization": "secret-token"}
    )

    assert resp.status_code == 401
    assert resp.get_json()["error"]["code"] == "unauthorized"


@patch("app.api.routes.ConnectorClient")
def test_v2_generate_missing_field_returns_400(mock_cc, client):
    body = {"text": "x", "provider": "openai"}  # no model

    resp = client.post("/v2/generate/bpmn", json=body, headers=AUTH)

    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "invalid_request"
    mock_cc.return_value.generate.assert_not_called()


@patch("app.api.routes.ConnectorClient")
def test_v2_generate_non_json_returns_400(mock_cc, client):
    resp = client.post(
        "/v2/generate/bpmn",
        data="not json",
        headers={**AUTH, "Content-Type": "text/plain"},
    )

    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "invalid_request"


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
def test_legacy_bpmn_uses_default_model_and_preserves_response(mock_cc, client):
    mock_cc.return_value.generate.return_value = "<bpmn>legacy</bpmn>"

    resp = client.post(
        "/generate_BPMN", json={"text": "describe a process", "api_key": "secret-token"}
    )

    assert resp.status_code == 200
    assert resp.get_json() == {"result": "<bpmn>legacy</bpmn>"}
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
    mock_cc.return_value.generate.return_value = "<bpmn>legacy</bpmn>"
    mock_mt.return_value.transform.return_value = "<pnml>legacy</pnml>"

    resp = client.post(
        "/generate_PNML", json={"text": "describe a process", "api_key": "secret-token"}
    )

    assert resp.status_code == 200
    assert resp.get_json() == {"result": "<pnml>legacy</pnml>"}
    mock_mt.return_value.transform.assert_called_once_with(
        "<bpmn>legacy</bpmn>", {"direction": "bpmntopnml"}
    )
