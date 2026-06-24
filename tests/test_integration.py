"""
Integration tests for the T2P service
"""

import pytest


PROCESS_TEXT_CASES = [
    ("atm.txt", "ATM Withdrawal"),
    ("bicycle-repair.txt", "Bicycle Repair"),
    ("serial-process.txt", "Ice Cream Service"),
]


@pytest.fixture
def app():
    from app import create_app

    return create_app("testing")


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def connector_app(mock_connector_server):
    from app import create_app

    app = create_app("testing")
    app.config["T2P_LLM_API_CONNECTOR_URL"] = mock_connector_server["base_url"]
    return app


@pytest.fixture
def connector_client(connector_app):
    return connector_app.test_client()


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

    def test_deprecated_health_alias_remains_functional(self, client):
        response = client.get("/test_connection")
        assert response.status_code == 200
        assert response.headers.get("Deprecation") == "@1780272000"

    def test_content_type_json(self, client):
        response = client.get("/test_connection")
        assert "application/json" in response.content_type

    def test_cors_preflight_allows_authorization_header(self, client):
        # The v2 endpoints require an Authorization header, so the CORS
        # preflight must permit it for browser clients.
        response = client.options(
            "/v2/generate/bpmn",
            headers={
                "Origin": "http://example.com",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Authorization",
            },
        )
        allowed = response.headers.get("Access-Control-Allow-Headers", "")
        assert "authorization" in allowed.lower()


class TestConnectorIntegration:
    """End-to-end coverage against the local mocked connector API."""

    @pytest.mark.parametrize("filename, expected_task_name", PROCESS_TEXT_CASES)
    def test_v2_generate_bpmn_uses_process_texts(
        self,
        connector_client,
        mock_connector_server,
        process_texts,
        filename,
        expected_task_name,
    ):
        response = connector_client.post(
            "/v2/generate/bpmn",
            json={
                "text": process_texts[filename],
                "provider": "openai",
                "model": "gpt-4o",
            },
            headers={"Authorization": "Bearer integration-token"},
        )

        assert response.status_code == 200
        result = response.get_json()["result"]
        assert "<definitions" in result
        assert expected_task_name in result

        assert mock_connector_server["received_requests"]["generate"]
        assert mock_connector_server["received_requests"]["generate"][-1][
            "user_text"
        ] == process_texts[filename]
        assert mock_connector_server["received_requests"]["generate"][-1][
            "provider"
        ] == "openai"
        assert mock_connector_server["received_requests"]["generate"][-1][
            "model"
        ] == "gpt-4o"

    def test_v2_models_uses_configurable_connector_url(
        self, connector_client, mock_connector_server
    ):
        response = connector_client.get("/v2/models")

        assert response.status_code == 200
        assert response.get_json() == {
            "models": [
                {"provider": "openai", "model": "gpt-4o"},
                {"provider": "anthropic", "model": "claude-3.5-sonnet"},
            ]
        }
        assert mock_connector_server["received_requests"]["models"] == 1
