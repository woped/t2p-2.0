import pytest
from unittest.mock import patch
from app import create_app
from app.backend.connector_client import (
    ConnectorClient,
    ConnectorError,
    ConnectorClientError,
)


@pytest.fixture
def app():
    return create_app("testing")


@pytest.fixture
def connector(app):
    with app.app_context():
        return ConnectorClient()


# --- generate -------------------------------------------------------------


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
def test_generate_forwards_prompting_strategy_when_provided(mock_post, connector, app):
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {"raw_response": "ok"}

    with app.app_context():
        connector.generate(
            authorization="Bearer secret-token",
            user_text="hello",
            provider="openai",
            model="gpt-4o",
            prompting_strategy="few_shot",
        )

    kwargs = mock_post.call_args.kwargs
    assert kwargs["json"] == {
        "user_text": "hello",
        "provider": "openai",
        "model": "gpt-4o",
        "prompting_strategy": "few_shot",
    }


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
def test_generate_429_raises_client_error_with_rate_limited_body(
    mock_post, connector, app
):
    mock_post.return_value.status_code = 429
    mock_post.return_value.json.return_value = {
        "error": {
            "code": "rate_limited",
            "message": "Provider quota or rate limit exceeded.",
        }
    }

    with app.app_context():
        with pytest.raises(ConnectorClientError) as exc_info:
            connector.generate("Bearer t", "text", "openai", "gpt-4o")

    assert exc_info.value.status_code == 429
    assert exc_info.value.error_body["error"]["code"] == "rate_limited"


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
