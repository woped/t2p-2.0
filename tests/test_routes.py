"""
Tests for API routes in app.api.routes
"""

import pytest
from unittest.mock import Mock, patch


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
        mock_cc.return_value.generate.return_value = "<bpmn>legacy</bpmn>"
        response = client.post(path, json={"text": "x", "api_key": "k"})
        assert response.status_code == 200
        assert response.get_json() == {"result": "<bpmn>legacy</bpmn>"}
        assert response.headers.get("Deprecation") == "@1780272000"

    @pytest.mark.parametrize("path", ["/generate_pnml", "/generate_PNML"])
    @patch("app.api.routes.ModelTransformer")
    @patch("app.api.routes.ConnectorClient")
    def test_legacy_pnml_routes_remain_functional(
        self, mock_cc, mock_transformer, client, path
    ):
        mock_cc.return_value.generate.return_value = "<bpmn>legacy</bpmn>"
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
