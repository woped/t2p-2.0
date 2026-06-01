"""
Tests for API routes in app.api.routes
"""

import pytest
import requests
from unittest.mock import Mock, patch

from app.backend.connector_client import ConnectorError, ConnectorClientError
from tests.sample_models import RAW_MODEL_JSON


@pytest.fixture
def app():
    from app import create_app

    app = create_app("testing")
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


class TestExampleRoute:
    def test_example_route_success(self, client):
        response = client.get("/example")
        assert response.status_code == 200
        assert b"This is an example route" in response.data


class TestMetrics:
    def test_metrics_endpoint(self, client):
        response = client.get("/metrics")
        assert response.status_code == 200
        assert response.content_type.startswith("text/plain")
        assert (
            b"http_requests_total" in response.data or b"REQUEST_COUNT" in response.data
        )


class TestDeprecatedEndpoints:
    def test_already_sunset_api_call_returns_410(self, client):
        response = client.post("/api_call", json={"text": "x", "api_key": "k"})
        assert response.status_code == 410
        assert response.get_json()["error"]["code"] == "deprecated"
        assert "/v2 API" in response.get_json()["error"]["message"]
        assert response.headers.get("Sunset") == "Wed, 31 Dec 2025 23:59:59 GMT"

    def test_newly_deprecated_health_route_still_works_with_headers(self, client):
        response = client.get("/test_connection")
        assert response.status_code == 200
        assert response.get_json() == "Successful"
        assert response.headers.get("Deprecation") == "@1780272000"
        assert response.headers.get("Sunset") == "Tue, 01 Dec 2026 00:00:00 GMT"
        assert response.headers.get("Link") == '</api/swagger.yaml>; rel="deprecation"'

    def test_deprecated_endpoint_increments_counter(self, app, client):
        # Replace the metric through its registration seam rather than patching
        # the import-time proxy, which can't resolve outside an app context.
        mock_counter = Mock()
        app.extensions["metrics"]["REQUEST_COUNT"] = mock_counter
        response = client.get("/test_connection")
        assert response.status_code == 200
        mock_counter.labels.assert_called()

    @pytest.mark.parametrize("path", ["/generate_bpmn", "/generate_BPMN"])
    @patch("app.api.routes.ConnectorClient")
    def test_legacy_bpmn_routes_remain_functional(self, mock_cc, client, path):
        mock_cc.return_value.generate.return_value = RAW_MODEL_JSON
        response = client.post(path, json={"text": "x", "api_key": "k"})
        assert response.status_code == 200
        assert "<definitions" in response.get_json()["result"]
        assert response.headers.get("Deprecation") == "@1780272000"

    @pytest.mark.parametrize("path", ["/generate_pnml", "/generate_PNML"])
    @patch("app.api.routes.ModelTransformer")
    @patch("app.api.routes.ConnectorClient")
    def test_legacy_pnml_routes_remain_functional(
        self, mock_cc, mock_transformer, client, path
    ):
        mock_cc.return_value.generate.return_value = RAW_MODEL_JSON
        mock_transformer.return_value.transform.return_value = "<pnml>legacy</pnml>"
        response = client.post(path, json={"text": "x", "api_key": "k"})
        assert response.status_code == 200
        assert response.get_json() == {"result": "<pnml>legacy</pnml>"}


class TestOperationalEndpoints:
    def test_echo_remains_unversioned_and_functional(self, client):
        response = client.get("/_/_/echo")
        assert response.status_code == 200
        assert response.get_json() == {"success": True}
        assert "Deprecation" not in response.headers


class TestLegacyGenerateErrors:
    """The legacy /generate_* endpoints own their own validation and error
    mapping (unlike the v2 path, which delegates to the connector). These cover
    the failure branches: the happy paths are exercised elsewhere."""

    def test_missing_api_key_returns_400(self, client):
        # The legacy contract requires both 'text' and 'api_key' in the body.
        response = client.post("/generate_bpmn", json={"text": "x"})
        assert response.status_code == 400
        assert "api_key" in response.get_json()["error"]

    @patch("app.api.routes.ConnectorClient")
    def test_connector_unreachable_returns_500(self, mock_cc, client):
        mock_cc.return_value.generate.side_effect = ConnectorError("down")
        response = client.post("/generate_bpmn", json={"text": "x", "api_key": "k"})
        assert response.status_code == 500
        assert response.get_json()["error"] == "LLM API connector error."

    @patch("app.api.routes.ConnectorClient")
    def test_connector_client_error_returns_500(self, mock_cc, client):
        # A 4xx/bad reply from the connector surfaces as an invalid-response 500
        # on the legacy path (it has no relay semantics, unlike v2).
        mock_cc.return_value.generate.side_effect = ConnectorClientError(400, None)
        response = client.post("/generate_bpmn", json={"text": "x", "api_key": "k"})
        assert response.status_code == 500
        assert response.get_json()["error"] == "Invalid response from LLM API."

    @patch("app.api.routes.ModelTransformer")
    @patch("app.api.routes.ConnectorClient")
    def test_pnml_transform_failure_returns_500(self, mock_cc, mock_mt, client):
        mock_cc.return_value.generate.return_value = RAW_MODEL_JSON
        mock_mt.return_value.transform.side_effect = (
            requests.exceptions.RequestException("transformer down")
        )
        response = client.post("/generate_pnml", json={"text": "x", "api_key": "k"})
        assert response.status_code == 500
        assert response.get_json()["error"] == "BPMN to PNML transformation failed."
