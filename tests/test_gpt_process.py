import pytest
from unittest.mock import patch
from app.backend.gpt_process import ApiCaller

@pytest.fixture
def api_caller():
    return ApiCaller(api_key="test_key", llm_provider="openai", prompting_strategy="minimal")


@patch("app.backend.gpt_process.requests.post")
def test_call_api_success(mock_post, api_caller):
    # Arrange: baue Fake-Response
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {"message": "Fake GPT Response"}

    # Act
    result = api_caller.call_api("test_user_text")

    # Assert
    assert result == "Fake GPT Response"
    mock_post.assert_called_once()


@patch("app.backend.gpt_process.requests.post")
def test_call_api_http_error(mock_post, api_caller):
    # Arrange: Fake HTTP 500
    mock_post.return_value.status_code = 500
    mock_post.return_value.text = "Internal Server Error"

    # Act
    result = api_caller.call_api("test_user_text")

    # Assert
    assert "An error occurred" in result
    assert "Internal Server Error" in result


@patch("app.backend.gpt_process.requests.post")
def test_conversion_pipeline_success(mock_post, api_caller):
    # Arrange: GPT liefert JSON, json_to_bpmn wird normal aufgerufen
    fake_json = '{"events": [], "tasks": [], "gateways": [], "flows": []}'
    mock_post.return_value.status_code = 200
    mock_post.return_value.json.return_value = {"message": fake_json}

    # Act
    result = api_caller.conversion_pipeline("Test process description")

    # Assert
    assert isinstance(result, str)
    assert "<?xml" in result or "<definitions" in result  # simple check on BPMN output

@patch("app.backend.gpt_process.requests.post")
def test_call_api_exception(mock_post, api_caller):
    mock_post.side_effect = Exception("Fake API Exception")

    result = api_caller.call_api("test_user_text")

    assert "An exception occurred" in result
    assert "Fake API Exception" in result

@patch.object(ApiCaller, 'generate_bpmn_json')
def test_conversion_pipeline_exception(mock_generate_bpmn_json, api_caller):
    mock_generate_bpmn_json.return_value = "INVALID_JSON"

    result = api_caller.conversion_pipeline("Bad process description")
    
    assert "An error occurred" in result
