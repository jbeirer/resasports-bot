import logging
from unittest.mock import patch

import pytest
import requests
import responses
from urllib3.connectionpool import HTTPConnectionPool
from urllib3.exceptions import NewConnectionError, ProtocolError, ReadTimeoutError
from urllib3.util.retry import Retry

from pysportbot.client import DEFAULT_HEADERS, ApiClient
from pysportbot.exceptions import APIError

BASE_URL = "https://api.example.test"
URL = f"{BASE_URL}/endpoint"


@pytest.fixture
def client() -> ApiClient:
    return ApiClient()


@pytest.fixture
def rsps():
    with responses.RequestsMock() as rsps:
        yield rsps


def test_returns_json_object(client, rsps):
    rsps.add(responses.POST, URL, json={"success": True})

    assert client.post_json(URL) == {"success": True}


@pytest.mark.parametrize("status", [401, 404, 500])
def test_non_2xx_raises_api_error(client, rsps, status):
    rsps.add(responses.GET, URL, status=status, body="x" * 500)

    with pytest.raises(APIError) as exc_info:
        client.get_json(URL)

    assert exc_info.value.endpoint == URL
    assert exc_info.value.status_code == status
    assert exc_info.value.body == "x" * 200


@pytest.mark.parametrize(
    "response_kwargs",
    [
        pytest.param({"body": "<html>Maintenance</html>", "content_type": "text/html"}, id="html"),
        pytest.param({"json": [{"success": True}]}, id="json-list"),
        pytest.param({"json": "ok"}, id="json-string"),
    ],
)
def test_non_object_body_raises_api_error(client, rsps, response_kwargs):
    rsps.add(responses.POST, URL, **response_kwargs)

    with pytest.raises(APIError) as exc_info:
        client.post_json(URL)

    assert exc_info.value.status_code == 200


def test_default_timeout_is_passed(client, rsps):
    rsps.add(responses.POST, URL, json={})

    with patch.object(client.session, "request", wraps=client.session.request) as request:
        client.post_json(URL)

    assert request.call_args.kwargs["timeout"] == (5, 10)


def test_explicit_timeout_wins(client, rsps):
    rsps.add(responses.POST, URL, json={})

    with patch.object(client.session, "request", wraps=client.session.request) as request:
        client.post_json(URL, timeout=(5, 120))

    assert request.call_args.kwargs["timeout"] == (5, 120)


def test_sends_default_headers(client, rsps):
    rsps.add(responses.GET, URL, json={})

    client.get_json(URL)

    sent = rsps.calls[0].request.headers
    assert {key: sent[key] for key in DEFAULT_HEADERS} == DEFAULT_HEADERS


def test_request_headers_merge_with_session_headers(client, rsps):
    rsps.add(responses.GET, URL, json={})
    client.set_bearer_token("session-token", base_url=BASE_URL)

    client.get_json(URL, headers={"Authorization": "Bearer request-token", "X-Extra": "1"})

    sent = rsps.calls[0].request.headers
    assert sent["Authorization"] == "Bearer request-token"
    assert sent["X-Extra"] == "1"
    assert sent["User-Agent"] == DEFAULT_HEADERS["User-Agent"]
    # The per-request override does not leak into the session
    assert "Authorization" not in client.session.headers


@pytest.mark.parametrize(
    ("url", "sent"),
    [
        pytest.param(URL, True, id="same-service"),
        pytest.param("https://other.example.test/endpoint", False, id="other-service"),
        pytest.param("https://api.example.test.evil.test/endpoint", False, id="look-alike-host"),
    ],
)
def test_bearer_token_is_scoped_to_base_url(client, rsps, url, sent):
    rsps.add(responses.GET, url, json={})
    client.set_bearer_token("token", base_url=BASE_URL)

    client.get_json(url)

    assert ("Authorization" in rsps.calls[0].request.headers) is sent


def test_clear_bearer_token(client, rsps):
    rsps.add(responses.GET, URL, json={})
    client.set_bearer_token("token", base_url=BASE_URL)
    client.clear_bearer_token()

    client.get_json(URL)

    assert "Authorization" not in rsps.calls[0].request.headers
    # Clearing an already cleared token is fine
    client.clear_bearer_token()


def test_logs_request_without_body_or_headers(client, rsps, pysportbot_caplog):
    rsps.add(responses.POST, URL, json={})
    client.set_bearer_token("secret-token", base_url=BASE_URL)
    pysportbot_caplog.set_level(logging.DEBUG, logger="pysportbot")

    client.post_json(URL, json={"password": "secret-password"})

    assert f"POST {URL} -> HTTP 200" in pysportbot_caplog.text
    assert "secret" not in pysportbot_caplog.text


@pytest.mark.parametrize(
    ("error", "attempts"),
    [
        # Never reached the server: retried twice
        pytest.param(NewConnectionError(None, "connection refused"), 3, id="connect-error"),
        # May have reached the server: never re-sent, so a booking cannot be made twice
        pytest.param(ReadTimeoutError(None, URL, "read timed out"), 1, id="read-timeout"),
        pytest.param(ProtocolError("connection aborted"), 1, id="connection-aborted"),
    ],
)
def test_post_retries_only_connection_errors(client, error, attempts):
    with (
        patch.object(HTTPConnectionPool, "_make_request", side_effect=error) as make_request,
        patch.object(Retry, "sleep"),
        pytest.raises(requests.RequestException),
    ):
        client.post_json(URL, data={"id_activity_calendar": "1"})

    assert make_request.call_count == attempts


def test_retry_policy(client):
    retry = client.session.get_adapter(URL).max_retries

    assert (retry.connect, retry.read, retry.status, retry.other) == (2, False, 0, 0)


def test_read_timeout_raises_read_timeout(client):
    with (
        patch.object(HTTPConnectionPool, "_make_request", side_effect=ReadTimeoutError(None, URL, "read timed out")),
        pytest.raises(requests.ReadTimeout),
    ):
        client.post_json(URL, data={"id_activity_calendar": "1"})
