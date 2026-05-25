from unittest.mock import patch
from app.backend.connector_client import ConnectorError, ConnectorClientError


AUTH = {"Authorization": "Bearer secret-token"}
BODY = {"text": "describe a process", "provider": "openai", "model": "gpt-4o"}


# --- /v1/generate ---------------------------------------------------------


@patch("app.api.routes.ConnectorClient")
def test_v1_generate_bpmn_success(mock_cc, client):
    mock_cc.return_value.generate.return_value = "RAW"

    resp = client.post("/v1/generate/bpmn", json=BODY, headers=AUTH)

    assert resp.status_code == 200
    assert resp.get_json() == {"result": "RAW"}
    # The request is translated into the connector call: header forwarded,
    # text -> user_text, provider/model passed through.
    mock_cc.return_value.generate.assert_called_once_with(
        authorization="Bearer secret-token",
        user_text="describe a process",
        provider="openai",
        model="gpt-4o",
    )


@patch("app.api.routes.ConnectorClient")
def test_v1_generate_pnml_success(mock_cc, client):
    mock_cc.return_value.generate.return_value = "RAW"

    resp = client.post("/v1/generate/pnml", json=BODY, headers=AUTH)

    assert resp.status_code == 200
    assert resp.get_json() == {"result": "RAW"}


@patch("app.api.routes.ConnectorClient")
def test_v1_generate_missing_auth_returns_401(mock_cc, client):
    resp = client.post("/v1/generate/bpmn", json=BODY)

    assert resp.status_code == 401
    assert resp.get_json()["error"]["code"] == "unauthorized"
    mock_cc.return_value.generate.assert_not_called()


@patch("app.api.routes.ConnectorClient")
def test_v1_generate_malformed_auth_returns_401(mock_cc, client):
    resp = client.post(
        "/v1/generate/bpmn", json=BODY, headers={"Authorization": "secret-token"}
    )

    assert resp.status_code == 401
    assert resp.get_json()["error"]["code"] == "unauthorized"


@patch("app.api.routes.ConnectorClient")
def test_v1_generate_missing_field_returns_400(mock_cc, client):
    body = {"text": "x", "provider": "openai"}  # no model

    resp = client.post("/v1/generate/bpmn", json=body, headers=AUTH)

    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "invalid_request"
    mock_cc.return_value.generate.assert_not_called()


@patch("app.api.routes.ConnectorClient")
def test_v1_generate_non_json_returns_400(mock_cc, client):
    resp = client.post(
        "/v1/generate/bpmn",
        data="not json",
        headers={**AUTH, "Content-Type": "text/plain"},
    )

    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "invalid_request"


@patch("app.api.routes.ConnectorClient")
def test_v1_generate_connector_error_returns_500(mock_cc, client):
    mock_cc.return_value.generate.side_effect = ConnectorError("down")

    resp = client.post("/v1/generate/bpmn", json=BODY, headers=AUTH)

    assert resp.status_code == 500
    assert resp.get_json()["error"]["code"] == "upstream_error"


@patch("app.api.routes.ConnectorClient")
def test_v1_generate_relays_connector_4xx(mock_cc, client):
    # A 4xx from the connector (its semantic validation) is relayed to the
    # client with its status and body intact, not masked as 500.
    mock_cc.return_value.generate.side_effect = ConnectorClientError(
        400, {"error": {"code": "invalid_provider", "message": "Unknown provider 'x'."}}
    )

    resp = client.post("/v1/generate/bpmn", json=BODY, headers=AUTH)

    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "invalid_provider"


# --- /v1/models -----------------------------------------------------------


@patch("app.api.routes.ConnectorClient")
def test_v1_models_success(mock_cc, client):
    models = [{"provider": "openai", "model": "gpt-4o", "default": True}]
    mock_cc.return_value.list_models.return_value = models

    resp = client.get("/v1/models")

    assert resp.status_code == 200
    assert resp.get_json() == {"models": models}


@patch("app.api.routes.ConnectorClient")
def test_v1_models_connector_error_returns_500(mock_cc, client):
    mock_cc.return_value.list_models.side_effect = ConnectorError("down")

    resp = client.get("/v1/models")

    assert resp.status_code == 500
    assert resp.get_json()["error"]["code"] == "upstream_error"


# --- /v1/health -----------------------------------------------------------


def test_v1_health_ok(client):
    resp = client.get("/v1/health")

    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}


# --- deprecation headers --------------------------------------------------


def test_deprecated_test_connection_has_headers(client):
    resp = client.get("/test_connection")

    assert resp.status_code == 410
    assert resp.headers.get("Deprecation") == "true"
    assert "Sunset" in resp.headers
    assert "Link" in resp.headers


def test_deprecated_echo_has_headers(client):
    resp = client.get("/_/_/echo")

    assert resp.status_code == 410
    assert resp.headers.get("Deprecation") == "true"
