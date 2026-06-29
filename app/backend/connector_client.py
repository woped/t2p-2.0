import logging
import time
import requests
from flask import current_app

from app.request_id import REQUEST_ID_HEADER, get_request_id

# Module-level logger for this module
logger = logging.getLogger(__name__)

# Default timeout (seconds) for a single connector HTTP call. In the async path
# each call (submit / one status poll) is short; in the sync fallback this one
# call must outlast the full multi-attempt generation, so it is generous.
DEFAULT_TIMEOUT = 300


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

    Generation is driven through the connector's internal async submit/poll
    endpoints when enabled, so the long, multi-attempt generation is not held
    open on a single HTTP request (which would hit the connector's gunicorn
    worker timeout). It degrades to the synchronous ``/generate`` if the async
    endpoints are unavailable.

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

    def _headers(self, authorization=None):
        """Build request headers. The correlation id is always forwarded so the
        connector logs the call under the same id as the orchestrator. The
        Authorization value is forwarded verbatim and never logged.
        """
        headers = {REQUEST_ID_HEADER: get_request_id()}
        if authorization is not None:
            headers["Authorization"] = authorization
            headers["Content-Type"] = "application/json"
        return headers

    def generate(self, authorization, user_text, provider, model):
        """Call the connector and return ``raw_response``.

        Uses the internal async submit/poll endpoints when enabled; falls back
        to the synchronous ``/generate`` if they are unavailable (404/405).

        :param authorization: the client's ``Authorization`` header value,
            forwarded unchanged (e.g. ``"Bearer <api_key>"``).
        :raises ConnectorError: on connection failure, timeout, non-200, or a
            malformed response body.
        :raises ConnectorClientError: on a connector 4xx (relayed to the caller).
        """
        if current_app.config.get("CONNECTOR_INTERNAL_ASYNC_ENABLED", True):
            fallback_enabled = current_app.config.get(
                "CONNECTOR_INTERNAL_ASYNC_FALLBACK_TO_SYNC", True
            )
            try:
                return self._generate_via_internal_async(
                    authorization, user_text, provider, model
                )
            except ConnectorClientError as e:
                # If the internal async endpoint is not available on the
                # connector, degrade to the stable synchronous endpoint. Other
                # 4xx (e.g. 422 model_unprocessable) are real and re-raised.
                if fallback_enabled and e.status_code in (404, 405):
                    logger.warning(
                        "Connector internal async unavailable (%s), falling back "
                        "to /generate",
                        e.status_code,
                    )
                    return self._generate_sync(
                        authorization, user_text, provider, model
                    )
                raise

        return self._generate_sync(authorization, user_text, provider, model)

    def _generate_sync(self, authorization, user_text, provider, model):
        """Call the connector's synchronous ``POST /generate``."""
        url = f"{self.base_url}/generate"
        payload = {"user_text": user_text, "provider": provider, "model": model}

        logger.info(
            "Calling connector /generate (sync)",
            extra={"url": url, "provider": provider, "model": model},
        )
        try:
            # verify=False mirrors the existing connector calls in this codebase.
            response = requests.post(
                url,
                headers=self._headers(authorization),
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
            raise ConnectorClientError(response.status_code, _json_or_none(response))

        if response.status_code != 200:
            logger.error(
                "Connector /generate returned non-200",
                extra={"status": response.status_code},
            )
            raise ConnectorError(
                f"LLM API connector returned status {response.status_code}"
            )

        return _extract_raw_response(response)

    def _generate_via_internal_async(self, authorization, user_text, provider, model):
        """Submit to the internal async endpoint and poll until terminal state.

        Each HTTP call here is short (submit, then status polls), so the long
        generation never occupies an open request and never trips the connector's
        per-request worker timeout. The total wait is bounded by the poll loop.
        """
        submit_url = f"{self.base_url}/internal/jobs/generate"
        payload = {"user_text": user_text, "provider": provider, "model": model}

        logger.info(
            "Submitting connector async job",
            extra={"url": submit_url, "provider": provider, "model": model},
        )
        try:
            submit_response = requests.post(
                submit_url,
                headers=self._headers(authorization),
                json=payload,
                timeout=self.timeout,
                verify=False,
            )
        except requests.exceptions.RequestException as e:
            logger.exception("Connector async submit failed")
            raise ConnectorError(f"Failed to reach the LLM API connector: {e}") from e

        if 400 <= submit_response.status_code < 500:
            raise ConnectorClientError(
                submit_response.status_code, _json_or_none(submit_response)
            )
        if submit_response.status_code != 202:
            raise ConnectorError(
                "LLM API connector async submit returned status "
                f"{submit_response.status_code}"
            )

        try:
            job_id = submit_response.json().get("job_id")
        except ValueError as e:
            raise ConnectorError("LLM API connector returned invalid JSON") from e
        if not job_id:
            raise ConnectorError("LLM API connector async submit missing job_id")

        status_url = f"{self.base_url}/internal/jobs/{job_id}"
        poll_interval = float(
            current_app.config.get("CONNECTOR_ASYNC_POLL_INTERVAL_SECONDS", 2.0)
        )
        max_wait = float(
            current_app.config.get("CONNECTOR_ASYNC_MAX_WAIT_SECONDS", 300)
        )
        deadline = time.time() + max_wait

        while time.time() < deadline:
            remaining = deadline - time.time()
            try:
                status_response = requests.get(
                    status_url,
                    headers=self._headers(),
                    timeout=min(self.timeout, max(1.0, remaining)),
                    verify=False,
                )
            except requests.exceptions.RequestException as e:
                logger.exception("Connector async status poll failed")
                raise ConnectorError(
                    f"Failed to reach the LLM API connector: {e}"
                ) from e

            if 400 <= status_response.status_code < 500:
                raise ConnectorClientError(
                    status_response.status_code, _json_or_none(status_response)
                )
            if status_response.status_code != 200:
                raise ConnectorError(
                    "LLM API connector async status returned status "
                    f"{status_response.status_code}"
                )

            try:
                status_data = status_response.json()
            except ValueError as e:
                raise ConnectorError("LLM API connector returned invalid JSON") from e

            status = status_data.get("status")
            if status == "succeeded":
                raw_response = (status_data.get("result") or {}).get("raw_response")
                if raw_response is None:
                    raise ConnectorError(
                        "LLM API connector async result missing 'raw_response'"
                    )
                return raw_response
            if status == "failed":
                error = status_data.get("error") or {}
                http_status = error.get("http_status")
                message = error.get("message") or "LLM provider call failed"
                # Preserve the connector's original client-error semantics (e.g.
                # 422 model_unprocessable) instead of collapsing every async
                # failure to a generic upstream error.
                if isinstance(http_status, int) and 400 <= http_status < 500:
                    raise ConnectorClientError(http_status, {"error": error})
                raise ConnectorError(message)

            time.sleep(poll_interval)

        raise ConnectorError("Timed out waiting for LLM API connector async result")

    def list_models(self):
        """Call the connector's ``GET /models`` and return the models list.

        :raises ConnectorError: on connection failure, timeout, non-200, or a
            malformed response body.
        """
        url = f"{self.base_url}/models"

        logger.debug("Calling connector /models", extra={"url": url})
        try:
            response = requests.get(
                url, headers=self._headers(), timeout=self.timeout, verify=False
            )
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


def _json_or_none(response):
    """Parse a response body as JSON, or return None if it is not JSON."""
    try:
        return response.json()
    except ValueError:
        return None


def _extract_raw_response(response):
    """Pull ``raw_response`` out of a 200 generate response body."""
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
        raise ConnectorError("LLM API connector response missing 'raw_response' field")
    return raw_response
