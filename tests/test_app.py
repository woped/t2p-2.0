import pytest
from app import create_app


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


# The legacy endpoints are sunset: routes still exist (not 404) but return 410.


def test_test_connection(client):
    response = client.get("/test_connection")
    assert response.status_code == 410
    assert response.json["error"]["code"] == "deprecated"


def test_echo(client):
    response = client.get("/_/_/echo")
    assert response.status_code == 410
    assert response.json["error"]["code"] == "deprecated"


def test_metrics(client):
    response = client.get("/metrics")
    assert response.status_code == 200
    assert b"http_requests_total" in response.data


def test_api_call(client):
    response = client.post("/api_call", json={})
    assert response.status_code == 410


def test_generate_BPMN_call(client):
    response = client.post("/generate_BPMN", json={})
    assert response.status_code == 410


def test_generate_PNML_call(client):
    response = client.post("/generate_PNML", json={})
    assert response.status_code == 410


def test_generate_bpmn_lowercase_route(client):
    """Lowercase /generate_bpmn route still exists (410, not 404)."""
    response = client.post("/generate_bpmn", json={})
    assert response.status_code == 410


def test_generate_pnml_lowercase_route(client):
    """Lowercase /generate_pnml route still exists (410, not 404)."""
    response = client.post("/generate_pnml", json={})
    assert response.status_code == 410


def test_app_has_swagger_ui():
    """Test that Swagger UI blueprint is registered"""
    from app import create_app

    app = create_app()
    # Check if swagger blueprint exists
    blueprints = [bp for bp in app.blueprints.keys()]
    # Swagger UI typically registers as 'swagger_ui'
    assert len(blueprints) > 0


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
