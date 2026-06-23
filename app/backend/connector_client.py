import logging
import requests
from flask import current_app

# Module-level logger for this module
logger = logging.getLogger(__name__)

# Default timeout (seconds) for connector HTTP calls.
DEFAULT_TIMEOUT = 60


class ConnectorError(Exception):
    """Raised when the connector is unreachable or returns a server error.

    The route layer maps this to an ``upstream_error`` response.
    """


class ConnectorClientError(Exception):
    """Raised when the connector rejects the request with a 4xx client error.

    Carries the status and the connector's error body so the route layer can
    relay them to the caller instead of masking them as an upstream failure.
    """

    def __init__(self, status_code, error_body=None):
        self.status_code = status_code
        self.error_body = error_body
        super().__init__(f"connector returned {status_code}")


class ConnectorClient:
    """HTTP client for the LLM API connector.

    Transport only: it forwards generate requests and fetches the model list.
    It does not build prompts, parse responses, or validate provider/model -
    those concerns live elsewhere.

    The instance is stateless: the caller's ``Authorization`` header is passed
    per request and forwarded verbatim, so the provider key never becomes a
    body field or instance attribute.
    """

    def __init__(self):
        self.base_url = current_app.config["T2P_LLM_API_CONNECTOR_URL"]
        self.timeout = current_app.config.get("CONNECTOR_TIMEOUT", DEFAULT_TIMEOUT)
        logger.debug(
            "ConnectorClient initialized",
            extra={"base_url": self.base_url, "timeout": self.timeout},
        )

    def generate(
        self, authorization, user_text, provider, model, prompting_strategy=None
    ):
        """Call the connector's ``POST /generate`` and return ``raw_response``.

        :param authorization: the client's ``Authorization`` header value,
            forwarded unchanged (e.g. ``"Bearer <api_key>"``).
        :param prompting_strategy: optional strategy forwarded to connector,
            for example ``"zero_shot"`` or ``"few_shot"``.
        :raises ConnectorError: on connection failure, timeout, non-200, or a
            malformed response body.
        """
        url = f"{self.base_url}/generate"
        # Authorization is forwarded verbatim; never log header values.
        headers = {"Authorization": authorization, "Content-Type": "application/json"}
        payload = {"user_text": user_text, "provider": provider, "model": model}
        if prompting_strategy is not None:
            payload["prompting_strategy"] = prompting_strategy

        logger.info(
            "Calling connector /generate",
            extra={"url": url, "provider": provider, "model": model},
        )
        try:
            # verify=False mirrors the existing connector calls in this codebase.
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=self.timeout,
                verify=False,
            )
        except requests.exceptions.RequestException as e:
            logger.exception("Connector /generate request failed")
            raise ConnectorError(f"Failed to reach the LLM API connector: {e}") from e

        # Relay the connector's own client errors (4xx) so the caller can pass
        # them through; treat 5xx / unreachable as an upstream failure.
        if 400 <= response.status_code < 500:
            try:
                error_body = response.json()
            except ValueError:
                error_body = None
            raise ConnectorClientError(response.status_code, error_body)

        if response.status_code != 200:
            logger.error(
                "Connector /generate returned non-200",
                extra={"status": response.status_code},
            )
            raise ConnectorError(
                f"LLM API connector returned status {response.status_code}"
            )

        try:
            data = response.json()
        except ValueError as e:
            logger.exception("Connector /generate returned invalid JSON")
            raise ConnectorError("LLM API connector returned invalid JSON") from e

        raw_response = data.get("raw_response")
        if raw_response is None:
            logger.error(
                "Connector /generate response missing 'raw_response'",
                extra={"response_keys": list(data.keys())},
            )
            raise ConnectorError(
                "LLM API connector response missing 'raw_response' field"
            )
        return raw_response

    def list_models(self):
        """Call the connector's ``GET /models`` and return the models list.

        :raises ConnectorError: on connection failure, timeout, non-200, or a
            malformed response body.
        """
        url = f"{self.base_url}/models"

        logger.debug("Calling connector /models", extra={"url": url})
        try:
            response = requests.get(url, timeout=self.timeout, verify=False)
        except requests.exceptions.RequestException as e:
            logger.exception("Connector /models request failed")
            raise ConnectorError(f"Failed to reach the LLM API connector: {e}") from e

        if response.status_code != 200:
            logger.error(
                "Connector /models returned non-200",
                extra={"status": response.status_code},
            )
            raise ConnectorError(
                f"LLM API connector returned status {response.status_code}"
            )

        try:
            data = response.json()
        except ValueError as e:
            logger.exception("Connector /models returned invalid JSON")
            raise ConnectorError("LLM API connector returned invalid JSON") from e

        models = data.get("models")
        if models is None:
            logger.error(
                "Connector /models response missing 'models'",
                extra={"response_keys": list(data.keys())},
            )
            raise ConnectorError("LLM API connector response missing 'models' field")
        return models
