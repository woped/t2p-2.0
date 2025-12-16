import pytest
from unittest.mock import patch
from app import create_app
from app.backend.gpt_process import ApiCaller


@pytest.fixture
def app():
    app = create_app("testing")
    return app


@pytest.fixture
def api_caller(app):
    with app.app_context():
        caller = ApiCaller(api_key="test_key")
    return caller


@patch("app.backend.gpt_process.requests.post")
def test_call_api_success(mock_post, api_caller, app):
    # Arrange: baue Fake-Response
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {"message": "Fake GPT Response"}

    # Act
    with app.app_context():
        result = api_caller.call_api("test_system_prompt", "test_user_text")

    # Assert
    assert result == "Fake GPT Response"
    mock_post.assert_called_once()


@patch("app.backend.gpt_process.requests.post")
def test_call_api_http_error(mock_post, api_caller, app):
    # Arrange: Fake HTTP 500
    mock_post.return_value.status_code = 500
    mock_post.return_value.text = "Internal Server Error"

    # Act
    with app.app_context():
        with pytest.raises(RuntimeError) as exc_info:
            api_caller.call_api("test_system_prompt", "test_user_text")

    # Assert
    assert "LLM API connector returned status 500" in str(exc_info.value)


@patch("app.backend.gpt_process.requests.post")
def test_conversion_pipeline_success(mock_post, api_caller, app):
    # Arrange: GPT liefert JSON, json_to_bpmn wird normal aufgerufen
    fake_json = '{"events": [], "tasks": [], "gateways": [], "flows": []}'
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {"message": fake_json}

    # Act
    with app.app_context():
        result = api_caller.conversion_pipeline("Test process description")

    # Assert
    assert isinstance(result, str)
    assert "<?xml" in result or "<definitions" in result  # simple check on BPMN output


@patch("app.backend.gpt_process.requests.post")
def test_call_api_exception(mock_post, api_caller, app):
    from requests.exceptions import RequestException

    mock_post.side_effect = RequestException("Fake API Exception")

    with app.app_context():
        with pytest.raises(RuntimeError) as exc_info:
            api_caller.call_api("test_system_prompt", "test_user_text")

    assert "Failed to connect to LLM API connector" in str(exc_info.value)


@patch("app.backend.gpt_process.requests.post")
def test_call_api_missing_message_field(mock_post, api_caller, app):
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {"data": "no message field"}

    with app.app_context():
        with pytest.raises(ValueError) as exc_info:
            api_caller.call_api("test_system_prompt", "test_user_text")

    assert "does not contain 'message' field" in str(exc_info.value)


@patch("app.backend.gpt_process.requests.post")
def test_call_api_json_decode_error(mock_post, api_caller, app):
    from json import JSONDecodeError

    mock_post.return_value.status_code = 200
    mock_post.return_value.json.side_effect = JSONDecodeError("error", "doc", 0)

    with app.app_context():
        with pytest.raises(ValueError) as exc_info:
            api_caller.call_api("test_system_prompt", "test_user_text")

    assert "invalid JSON" in str(exc_info.value)


@patch.object(ApiCaller, "generate_bpmn_json")
def test_conversion_pipeline_json_decode_error(
    mock_generate_bpmn_json, api_caller, app
):
    # When generate_bpmn_json returns invalid JSON, conversion_pipeline should raise ValueError
    mock_generate_bpmn_json.return_value = "INVALID_JSON"

    with app.app_context():
        with pytest.raises(ValueError) as exc_info:
            api_caller.conversion_pipeline("Bad process description")

    assert "invalid JSON" in str(exc_info.value) or "JSON" in str(exc_info.value)


@patch.object(ApiCaller, "generate_bpmn_json")
def test_conversion_pipeline_with_markdown_wrapper(
    mock_generate_bpmn_json, api_caller, app
):
    fake_json = '{"events": [], "tasks": [], "gateways": [], "flows": []}'
    mock_generate_bpmn_json.return_value = f"```json\n{fake_json}\n```"

    with app.app_context():
        result = api_caller.conversion_pipeline("Test process description")

    assert isinstance(result, str)
    assert "<?xml" in result or "<definitions" in result


@patch("app.backend.gpt_process.requests.post")
def test_generate_bpmn_json_calls_api(mock_post, api_caller, app):
    fake_json = '{"events": [], "tasks": [], "gateways": [], "flows": []}'
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {"message": fake_json}

    with app.app_context():
        result = api_caller.generate_bpmn_json("Test description")

    assert result == fake_json
    assert mock_post.called
    call_args = mock_post.call_args
    assert "system_prompt" in call_args[1]["json"]
    assert "DOUBLE QUOTES" in call_args[1]["json"]["system_prompt"]
