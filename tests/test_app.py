import pytest
from app import create_app


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_test_connection(client):
    response = client.get("/test_connection")
    assert response.status_code == 200
    assert response.json == "Successful"
    assert "Deprecation" in response.headers


def test_echo(client):
    response = client.get("/_/_/echo")
    assert response.status_code == 200
    assert response.json == {"success": True}


def test_metrics(client):
    response = client.get("/metrics")
    assert response.status_code == 200
    assert b"http_requests_total" in response.data


def test_api_call(client):
    response = client.post("/api_call", json={})
    assert response.status_code == 410


def test_generate_BPMN_call(client):
    response = client.post("/generate_BPMN", json={})
    assert response.status_code == 400
    assert "Deprecation" in response.headers


def test_generate_PNML_call(client):
    response = client.post("/generate_PNML", json={})
    assert response.status_code == 400


def test_generate_bpmn_lowercase_route(client):
    """Lowercase /generate_bpmn route remains available during migration."""
    response = client.post("/generate_bpmn", json={})
    assert response.status_code == 400


def test_generate_pnml_lowercase_route(client):
    """Lowercase /generate_pnml route remains available during migration."""
    response = client.post("/generate_pnml", json={})
    assert response.status_code == 400


def test_app_has_swagger_ui():
    """Test that Swagger UI endpoint is exposed via Flasgger."""
    from app import create_app

    app = create_app()
    with app.test_client() as client:
        response = client.get("/swagger/")
        assert response.status_code == 200


def test_openapi_endpoint_exposed():
    from app import create_app

    app = create_app()
    with app.test_client() as client:
        response = client.get("/openapi.json")
        assert response.status_code == 200
        data = response.get_json()
        assert "openapi" in data
        assert "paths" in data


def test_app_configuration():
    """Test app is properly configured"""
    from app import create_app

    app = create_app("testing")
    assert app.config["TESTING"] == True
    assert "T2P_TRANSFORMER_BASE_URL" in app.config
    assert "T2P_LLM_API_CONNECTOR_URL" in app.config


def test_metrics_extension_registered():
    """Test that Prometheus metrics are registered"""
    from app import create_app

    app = create_app()
    assert "metrics" in app.extensions
    assert "REQUEST_COUNT" in app.extensions["metrics"]
    assert "REQUEST_LATENCY" in app.extensions["metrics"]


def test_logging_configured():
    """Test that logging is configured"""
    from app import create_app
    import logging

    app = create_app()
    # Root logger should be configured
    logger = logging.getLogger()
    assert logger.level != logging.NOTSET
    assert len(logger.handlers) > 0
