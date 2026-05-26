"""
Tests for API routes in app.api.routes
"""

import pytest
from unittest.mock import Mock


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


# The legacy endpoints are sunset: their routes and deprecation headers remain,
# but they return 410 Gone with no result.

DEPRECATED_GET = ["/test_connection", "/_/_/echo"]
DEPRECATED_POST = [
    "/api_call",
    "/generate_bpmn",
    "/generate_BPMN",
    "/generate_pnml",
    "/generate_PNML",
]


class TestDeprecatedEndpoints:
    @pytest.mark.parametrize("path", DEPRECATED_GET)
    def test_get_endpoints_return_410(self, client, path):
        response = client.get(path)
        assert response.status_code == 410
        assert response.get_json()["error"]["code"] == "deprecated"

    @pytest.mark.parametrize("path", DEPRECATED_POST)
    def test_post_endpoints_return_410(self, client, path):
        response = client.post(path, json={"text": "x", "api_key": "k"})
        assert response.status_code == 410
        assert response.get_json()["error"]["code"] == "deprecated"

    def test_deprecation_headers_present(self, client):
        response = client.get("/test_connection")
        assert response.headers.get("Deprecation") == "true"
        assert "Link" in response.headers
        # No Sunset header: the endpoint is already 410 Gone.
        assert "Sunset" not in response.headers

    def test_deprecated_endpoint_increments_counter(self, app, client):
        # Replace the metric through its registration seam rather than patching
        # the import-time proxy, which can't resolve outside an app context.
        mock_counter = Mock()
        app.extensions["metrics"]["REQUEST_COUNT"] = mock_counter
        response = client.get("/test_connection")
        assert response.status_code == 410
        mock_counter.labels.assert_called()
