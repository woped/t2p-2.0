"""
Integration tests for the T2P service
"""

import pytest


@pytest.fixture
def app():
    from app import create_app

    return create_app("testing")


@pytest.fixture
def client(app):
    return app.test_client()


class TestMetricsIntegration:
    """Prometheus metrics integration."""

    def test_metrics_updated_on_request(self, client):
        client.get("/test_connection")

        metrics_response = client.get("/metrics")
        assert metrics_response.status_code == 200
        metrics_data = metrics_response.data.decode("utf-8")
        assert "http_requests_total" in metrics_data or "REQUEST_COUNT" in metrics_data

    def test_metrics_track_different_endpoints(self, client):
        client.get("/test_connection")
        client.get("/_/_/echo")

        metrics_response = client.get("/metrics")
        metrics_data = metrics_response.data.decode("utf-8")
        assert "test_connection" in metrics_data or "/test_connection" in metrics_data
        assert "echo" in metrics_data or "/_/_/echo" in metrics_data


class TestCORSAndSecurity:
    """CORS and content-type behavior on a representative endpoint."""

    def test_legacy_endpoint_is_gone(self, client):
        response = client.get("/test_connection")
        assert response.status_code == 410

    def test_content_type_json(self, client):
        response = client.get("/test_connection")
        assert "application/json" in response.content_type

    def test_cors_preflight_allows_authorization_header(self, client):
        # The v1 endpoints require an Authorization header, so the CORS
        # preflight must permit it for browser clients.
        response = client.options(
            "/v1/generate/bpmn",
            headers={
                "Origin": "http://example.com",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Authorization",
            },
        )
        allowed = response.headers.get("Access-Control-Allow-Headers", "")
        assert "authorization" in allowed.lower()
