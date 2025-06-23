import pytest
from unittest.mock import patch
from app.backend.modeltransformer import ModelTransformer

@pytest.fixture
def model_transformer():
    return ModelTransformer()

# ---- Test 1: Erfolgreicher Response ----
@patch("app.backend.modeltransformer.requests.post")
def test_transform_success(mock_post, model_transformer):
    # Arrange
    mock_post.return_value.status_code = 200
    mock_post.return_value.text = '{"pnml": "<pnml>Test-PNML</pnml>"}'
    mock_post.return_value.raise_for_status = lambda: None  # no exception

    # Act
    result = model_transformer.transform("<bpmn>Test</bpmn>")

    # Assert
    assert "<pnml>Test-PNML</pnml>" in result
    mock_post.assert_called_once()

# ---- Test 2: HTTPError ----
@patch("app.backend.modeltransformer.requests.post")
def test_transform_http_error(mock_post, model_transformer):
    from requests.exceptions import HTTPError

    mock_response = mock_post.return_value
    mock_response.status_code = 500
    mock_response.raise_for_status.side_effect = HTTPError(response=mock_response)

    with pytest.raises(HTTPError):
        model_transformer.transform("<bpmn>Test</bpmn>")

# ---- Test 3: RequestException ----
@patch("app.backend.modeltransformer.requests.post")
def test_transform_request_exception(mock_post, model_transformer):
    from requests.exceptions import RequestException

    mock_post.side_effect = RequestException("Network error")

    with pytest.raises(RequestException):
        model_transformer.transform("<bpmn>Test</bpmn>")
