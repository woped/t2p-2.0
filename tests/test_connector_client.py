import pytest
from unittest.mock import patch, MagicMock
from app import create_app
from app.backend.connector_client import (
    ConnectorClient,
    ConnectorError,
    ConnectorClientError,
)


@pytest.fixture
def app():
    # Default to the synchronous path so the transport-contract tests below
    # exercise _generate_sync directly. The async submit/poll path has its own
    # fixture + tests further down.
    app = create_app("testing")
    app.config["CONNECTOR_INTERNAL_ASYNC_ENABLED"] = False
    return app


@pytest.fixture
def connector(app):
    with app.app_context():
        return ConnectorClient()


# --- generate (synchronous path) ------------------------------------------


@patch("app.backend.connector_client.requests.post")
def test_generate_success_returns_raw_response(mock_post, connector, app):
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {"raw_response": "RAW BPMN JSON"}

    with app.app_context():
        result = connector.generate(
            authorization="Bearer secret-token",
            user_text="describe a process",
            provider="openai",
            model="gpt-4o",
        )

    assert result == "RAW BPMN JSON"


@patch("app.backend.connector_client.requests.post")
def test_generate_sends_contract_request(mock_post, connector, app):
    """The outbound request must match the connector contract exactly:
    Authorization forwarded verbatim, body fields present, no api_key."""
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {"raw_response": "ok"}

    with app.app_context():
        connector.generate(
            authorization="Bearer secret-token",
            user_text="hello",
            provider="openai",
            model="gpt-4o",
        )

    mock_post.assert_called_once()
    url = mock_post.call_args.args[0]
    kwargs = mock_post.call_args.kwargs

    assert url.endswith("/generate")
    # Authorization is forwarded unchanged.
    assert kwargs["headers"]["Authorization"] == "Bearer secret-token"
    # Body carries the contract fields...
    assert kwargs["json"] == {
        "user_text": "hello",
        "provider": "openai",
        "model": "gpt-4o",
    }
    # ...and the key is never put in the body.
    assert "api_key" not in kwargs["json"]
    # A timeout is always set.
    assert kwargs.get("timeout") is not None


@patch("app.backend.connector_client.requests.post")
def test_generate_forwards_correlation_id(mock_post, connector, app):
    # The bound request id is forwarded as X-Request-ID so the connector logs
    # this call under the same id as the orchestrator.
    from app.request_id import REQUEST_ID_HEADER, set_request_id

    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {"raw_response": "ok"}

    with app.app_context():
        set_request_id("test-correlation-id")
        connector.generate("Bearer t", "hello", "openai", "gpt-4o")

    assert (
        mock_post.call_args.kwargs["headers"][REQUEST_ID_HEADER]
        == "test-correlation-id"
    )


@patch("app.backend.connector_client.requests.post")
def test_generate_5xx_raises_upstream_error(mock_post, connector, app):
    mock_post.return_value.status_code = 500
    mock_post.return_value.text = "Internal Server Error"

    with app.app_context():
        with pytest.raises(ConnectorError) as exc_info:
            connector.generate("Bearer t", "text", "openai", "gpt-4o")

    assert "status 500" in str(exc_info.value)


@patch("app.backend.connector_client.requests.post")
def test_generate_4xx_raises_client_error(mock_post, connector, app):
    # A 4xx from the connector (e.g. invalid provider) is a relayable client
    # error, not an upstream failure.
    mock_post.return_value.status_code = 400
    mock_post.return_value.json.return_value = {
        "error": {"code": "invalid_provider", "message": "Unknown provider."}
    }

    with app.app_context():
        with pytest.raises(ConnectorClientError) as exc_info:
            connector.generate("Bearer t", "text", "bogus", "gpt-4o")

    assert exc_info.value.status_code == 400
    assert exc_info.value.error_body["error"]["code"] == "invalid_provider"


@patch("app.backend.connector_client.requests.post")
def test_generate_request_exception_raises(mock_post, connector, app):
    from requests.exceptions import RequestException

    mock_post.side_effect = RequestException("boom")

    with app.app_context():
        with pytest.raises(ConnectorError) as exc_info:
            connector.generate("Bearer t", "text", "openai", "gpt-4o")

    assert "Failed to reach" in str(exc_info.value)


@patch("app.backend.connector_client.requests.post")
def test_generate_invalid_json_raises(mock_post, connector, app):
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.side_effect = ValueError("no json")

    with app.app_context():
        with pytest.raises(ConnectorError) as exc_info:
            connector.generate("Bearer t", "text", "openai", "gpt-4o")

    assert "invalid JSON" in str(exc_info.value)


@patch("app.backend.connector_client.requests.post")
def test_generate_missing_raw_response_raises(mock_post, connector, app):
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {"unexpected": "shape"}

    with app.app_context():
        with pytest.raises(ConnectorError) as exc_info:
            connector.generate("Bearer t", "text", "openai", "gpt-4o")

    assert "raw_response" in str(exc_info.value)


# --- list_models ----------------------------------------------------------


@patch("app.backend.connector_client.requests.get")
def test_list_models_success_returns_list(mock_get, connector, app):
    models = [{"provider": "openai", "model": "gpt-4o"}]
    mock_get.return_value.status_code = 200
    mock_get.return_value.json.return_value = {"models": models}

    with app.app_context():
        result = connector.list_models()

    assert result == models
    assert mock_get.call_args.args[0].endswith("/models")


@patch("app.backend.connector_client.requests.get")
def test_list_models_non_200_raises(mock_get, connector, app):
    mock_get.return_value.status_code = 503

    with app.app_context():
        with pytest.raises(ConnectorError):
            connector.list_models()


@patch("app.backend.connector_client.requests.get")
def test_list_models_request_exception_raises(mock_get, connector, app):
    from requests.exceptions import ConnectionError

    mock_get.side_effect = ConnectionError("refused")

    with app.app_context():
        with pytest.raises(ConnectorError):
            connector.list_models()


@patch("app.backend.connector_client.requests.get")
def test_list_models_missing_field_raises(mock_get, connector, app):
    mock_get.return_value.status_code = 200
    mock_get.return_value.json.return_value = {"unexpected": "shape"}

    with app.app_context():
        with pytest.raises(ConnectorError) as exc_info:
            connector.list_models()

    assert "models" in str(exc_info.value)


@patch("app.backend.connector_client.requests.get")
def test_list_models_invalid_json_raises(mock_get, connector, app):
    # A 200 with an unparseable body is an upstream failure, not a usable list.
    mock_get.return_value.status_code = 200
    mock_get.return_value.json.side_effect = ValueError("no json")

    with app.app_context():
        with pytest.raises(ConnectorError) as exc_info:
            connector.list_models()

    assert "invalid JSON" in str(exc_info.value)


@patch("app.backend.connector_client.requests.post")
def test_generate_4xx_with_non_json_body_still_relays_status(mock_post, connector, app):
    # A 4xx whose body is not JSON (e.g. an HTML error page or empty body) must
    # still be relayed as a client error with its status preserved, so the route
    # can pass the rejection through rather than masking it as a 500. The error
    # body is simply absent.
    mock_post.return_value.status_code = 401
    mock_post.return_value.json.side_effect = ValueError("not json")

    with app.app_context():
        with pytest.raises(ConnectorClientError) as exc_info:
            connector.generate("Bearer t", "text", "openai", "gpt-4o")

    assert exc_info.value.status_code == 401
    assert exc_info.value.error_body is None


@patch("app.backend.connector_client.requests.post")
def test_generate_status_500_is_upstream_not_client_error(mock_post, connector, app):
    # The 4xx/5xx split is a boundary: a 5xx is an upstream failure the caller
    # cannot fix by changing input, so it must be ConnectorError, not a relayable
    # ConnectorClientError.
    mock_post.return_value.status_code = 500

    with app.app_context():
        with pytest.raises(ConnectorError):
            connector.generate("Bearer t", "text", "openai", "gpt-4o")


# --- generate (async submit/poll path) ------------------------------------


@pytest.fixture
def async_app():
    app = create_app("testing")
    app.config["CONNECTOR_INTERNAL_ASYNC_ENABLED"] = True
    app.config["CONNECTOR_INTERNAL_ASYNC_FALLBACK_TO_SYNC"] = True
    # No real waiting in tests.
    app.config["CONNECTOR_ASYNC_POLL_INTERVAL_SECONDS"] = 0.0
    app.config["CONNECTOR_ASYNC_MAX_WAIT_SECONDS"] = 5
    return app


@pytest.fixture
def async_connector(async_app):
    with async_app.app_context():
        return ConnectorClient()


@patch("app.backend.connector_client.requests.get")
@patch("app.backend.connector_client.requests.post")
def test_async_submit_and_poll_returns_raw_response(
    mock_post, mock_get, async_connector, async_app
):
    # Submit returns 202 + job id; a status poll reports success with the result.
    mock_post.return_value.status_code = 202
    mock_post.return_value.json.return_value = {
        "job_id": "job-1",
        "status_url": "/internal/jobs/job-1",
    }
    mock_get.return_value.status_code = 200
    mock_get.return_value.json.return_value = {
        "status": "succeeded",
        "result": {"raw_response": "RAW"},
    }

    with async_app.app_context():
        result = async_connector.generate("Bearer t", "text", "openai", "gpt-4o")

    assert result == "RAW"
    assert mock_post.call_args.args[0].endswith("/internal/jobs/generate")
    assert mock_get.call_args.args[0].endswith("/internal/jobs/job-1")


@patch("app.backend.connector_client.requests.get")
@patch("app.backend.connector_client.requests.post")
def test_async_failed_preserves_client_error_status(
    mock_post, mock_get, async_connector, async_app
):
    # A background failure carrying a 4xx http_status (e.g. 422) must surface as a
    # relayable ConnectorClientError, not be collapsed into a generic 5xx.
    mock_post.return_value.status_code = 202
    mock_post.return_value.json.return_value = {"job_id": "job-2"}
    mock_get.return_value.status_code = 200
    mock_get.return_value.json.return_value = {
        "status": "failed",
        "error": {
            "http_status": 422,
            "code": "model_unprocessable",
            "message": "no valid net",
            "details": ["x"],
        },
    }

    with async_app.app_context():
        with pytest.raises(ConnectorClientError) as exc_info:
            async_connector.generate("Bearer t", "text", "openai", "gpt-4o")

    assert exc_info.value.status_code == 422
    assert exc_info.value.error_body["error"]["code"] == "model_unprocessable"


@patch("app.backend.connector_client.requests.post")
def test_async_unavailable_falls_back_to_sync(mock_post, async_connector, async_app):
    # If the connector lacks the internal async endpoint (404), degrade to the
    # synchronous /generate instead of failing.
    submit = MagicMock(status_code=404)
    submit.json.return_value = {"error": {"code": "not_found"}}
    sync = MagicMock(status_code=200)
    sync.json.return_value = {"raw_response": "RAW-SYNC"}
    mock_post.side_effect = [submit, sync]

    with async_app.app_context():
        result = async_connector.generate("Bearer t", "text", "openai", "gpt-4o")

    assert result == "RAW-SYNC"
    assert mock_post.call_count == 2
    assert mock_post.call_args_list[0].args[0].endswith("/internal/jobs/generate")
    assert mock_post.call_args_list[1].args[0].endswith("/generate")
