import logging
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .exceptions import APIError

logger = logging.getLogger(__name__)

# Browser-like headers sent with every request; the server may depend on them, so keep them as they are
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.5",
    "DNT": "1",
    "Sec-GPC": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "TE": "trailers",
}


class ApiClient:
    """Owns the HTTP session, default headers, timeouts and connection retries, and turns bad responses into APIError."""

    def __init__(self, timeout: tuple[float, float] = (5, 10)) -> None:
        """
        Args:
            timeout: Default (connect, read) timeout in seconds, used when a request does not pass its own.
        """
        # The service books classes in parallel threads that share this session, which is fine for this usage
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        self.timeout = timeout
        # Retry only failures where the request never reached the server; never re-send a booking.
        retry = Retry(total=None, connect=2, read=0, status=0, other=0, allowed_methods=None, backoff_factor=0.3)
        self.session.mount("https://", HTTPAdapter(max_retries=retry))

    def set_bearer_token(self, token: str | None) -> None:
        """Send `Authorization: Bearer <token>` with every request, or stop sending it if `token` is None."""
        if token is None:
            self.session.headers.pop("Authorization", None)
        else:
            self.session.headers["Authorization"] = f"Bearer {token}"

    def request_json(
        self, method: str, url: str, *, headers: dict[str, str] | None = None, **kwargs: Any
    ) -> dict[str, Any]:
        """
        Send a request with the default timeout and return its JSON object body.

        Args:
            method: The HTTP method, e.g. "GET" or "POST".
            url: The endpoint URL.
            headers: Extra headers for this request only, merged over the session headers.
            **kwargs: Passed on to `requests.Session.request`, e.g. `params`, `data`, `json` or `timeout`.

        Raises:
            APIError: If the status is not 2xx, or the body is not JSON or not a JSON object.
            requests.RequestException: If the request itself fails, e.g. on a timeout or connection error.
        """
        kwargs.setdefault("timeout", self.timeout)
        # Never log request bodies or headers: they contain the password and tokens
        response = self.session.request(method, url, headers=headers, **kwargs)
        logger.debug("%s %s -> HTTP %s in %.2f s", method, url, response.status_code, response.elapsed.total_seconds())

        if not 200 <= response.status_code < 300:
            raise APIError("Unexpected HTTP status", endpoint=url, status_code=response.status_code, body=response.text)
        try:
            data = response.json()
        except ValueError as err:
            raise APIError(
                "Response is not JSON", endpoint=url, status_code=response.status_code, body=response.text
            ) from err
        if not isinstance(data, dict):
            raise APIError(
                "Response is not a JSON object", endpoint=url, status_code=response.status_code, body=response.text
            )
        return data

    def get_json(self, url: str, **kwargs: Any) -> dict[str, Any]:
        """Send a GET request; see `request_json`."""
        return self.request_json("GET", url, **kwargs)

    def post_json(self, url: str, **kwargs: Any) -> dict[str, Any]:
        """Send a POST request; see `request_json`."""
        return self.request_json("POST", url, **kwargs)
