import json
from urllib.parse import parse_qs, urlsplit

import pytest
import requests
import responses

from pysportbot.authenticator import Authenticator
from pysportbot.client import ApiClient
from pysportbot.endpoints import Endpoints
from pysportbot.exceptions import AuthenticationError


@pytest.fixture
def client() -> ApiClient:
    return ApiClient()


@pytest.fixture
def auth(mocked_api, client) -> Authenticator:
    return Authenticator(client)


def _without(payload: dict, key: str) -> dict:
    return {k: v for k, v in payload.items() if k != key}


def test_login_success(auth, client, mocked_api, payloads):
    auth.login("user@example.com", "password")

    [login_call] = [c for c in mocked_api.calls if c.request.url == str(Endpoints.USER_LOGIN)]
    assert json.loads(login_call.request.body) == {"username": "user@example.com", "password": "password"}

    login_app = payloads["user_login"]["applications"][0]
    assert auth.authenticated is True
    assert auth.id_application == str(login_app["id_application"])
    assert auth.id_user == str(login_app["id_user"])
    assert client.session.headers["Authorization"] == f"Bearer {payloads['sport_user_token']['jwt_token']}"
    assert auth.user_id == str(payloads["user"]["data"]["user"]["id_user"])


def test_sport_user_token_request_uses_resasocial_bearer(auth, mocked_api, payloads):
    auth.login("user@example.com", "password")

    [call] = [c for c in mocked_api.calls if c.request.url.startswith(str(Endpoints.SPORT_USER_TOKEN))]
    login = payloads["user_login"]
    assert call.request.headers["Authorization"] == f"Bearer {login['jwt_token']}"
    assert parse_qs(urlsplit(call.request.url).query) == {
        "id_user": [str(login["applications"][0]["id_user"])],
        "id_application": [str(login["applications"][0]["id_application"])],
    }


@pytest.mark.parametrize(
    ("method", "endpoint", "make_response"),
    [
        pytest.param(responses.POST, Endpoints.USER_LOGIN, lambda p: {"status": 401}, id="login-non-200"),
        pytest.param(responses.POST, Endpoints.USER_LOGIN, lambda p: {"body": "<html></html>"}, id="login-non-json"),
        pytest.param(
            responses.POST,
            Endpoints.USER_LOGIN,
            lambda p: {"json": {**p["user_login"], "applications": []}},
            id="login-empty-applications",
        ),
        pytest.param(
            responses.POST,
            Endpoints.USER_LOGIN,
            lambda p: {"json": _without(p["user_login"], "jwt_token")},
            id="login-missing-jwt",
        ),
        pytest.param(responses.GET, Endpoints.SPORT_USER_TOKEN, lambda p: {"status": 500}, id="sport-token-non-200"),
        pytest.param(
            responses.GET,
            Endpoints.SPORT_USER_TOKEN,
            lambda p: {"json": _without(p["sport_user_token"], "jwt_token")},
            id="sport-token-missing-jwt",
        ),
        pytest.param(responses.POST, Endpoints.USER, lambda p: {"status": 403}, id="user-non-200"),
        pytest.param(responses.POST, Endpoints.USER, lambda p: {"json": {"data": {}}}, id="user-missing-user"),
    ],
)
def test_login_failure_raises(auth, mocked_api, payloads, method, endpoint, make_response):
    mocked_api.replace(method, str(endpoint), **make_response(payloads))

    with pytest.raises(AuthenticationError):
        auth.login("user@example.com", "password")

    assert auth.authenticated is False
    assert auth.user_id is None


@pytest.mark.parametrize(
    ("make_response", "reason"),
    [
        pytest.param(lambda p: {"status": 401}, "login returned HTTP 401", id="non-200"),
        pytest.param(
            lambda p: {"json": {**p["user_login"], "applications": []}},
            "no applications in login response",
            id="empty-applications",
        ),
    ],
)
def test_login_failure_reason_is_specific(auth, mocked_api, payloads, make_response, reason):
    mocked_api.replace(responses.POST, str(Endpoints.USER_LOGIN), **make_response(payloads))

    with pytest.raises(AuthenticationError) as exc_info:
        auth.login("user@example.com", "password")

    assert exc_info.value.reason == reason


def test_login_wraps_unexpected_error(auth, mocked_api):
    error = requests.ConnectionError("connection refused")
    mocked_api.replace(responses.POST, str(Endpoints.USER_LOGIN), body=error)

    with pytest.raises(AuthenticationError) as exc_info:
        auth.login("user@example.com", "password")

    assert exc_info.value.__cause__ is error
    assert auth.authenticated is False


def test_session_invalid_before_login(auth, mocked_api):
    assert auth.is_session_valid() is False
    assert len(mocked_api.calls) == 0


def test_session_valid_after_login(auth):
    auth.login("user@example.com", "password")

    assert auth.is_session_valid() is True


@pytest.mark.parametrize(
    "response_kwargs",
    [
        pytest.param({"status": 401}, id="non-200"),
        pytest.param({"body": requests.ConnectionError("connection refused")}, id="connection-error"),
    ],
)
def test_session_invalid_on_user_failure(auth, mocked_api, response_kwargs):
    auth.login("user@example.com", "password")
    mocked_api.replace(responses.POST, str(Endpoints.USER), **response_kwargs)

    assert auth.is_session_valid() is False


def test_session_invalid_on_non_object_user_data(auth, mocked_api):
    auth.login("user@example.com", "password")
    mocked_api.replace(responses.POST, str(Endpoints.USER), json={"data": []})

    assert auth.is_session_valid() is False


def test_multiple_applications_use_first_and_warn(auth, mocked_api, payloads, pysportbot_caplog):
    first = payloads["user_login"]["applications"][0]
    second = {"id_application": 4321, "id_user": 8765}
    mocked_api.replace(
        responses.POST,
        str(Endpoints.USER_LOGIN),
        json={**payloads["user_login"], "applications": [first, second]},
    )

    auth.login("user@example.com", "password")

    assert auth.id_application == str(first["id_application"])
    warnings = [r.getMessage() for r in pysportbot_caplog.records if r.levelname == "WARNING"]
    assert any(str(first["id_application"]) in w and str(second["id_application"]) in w for w in warnings)


def test_relogin_does_not_send_stale_token(auth, mocked_api):
    auth.login("user@example.com", "password")
    auth.login("user@example.com", "password")

    login_calls = [c for c in mocked_api.calls if c.request.url == str(Endpoints.USER_LOGIN)]
    assert all("Authorization" not in c.request.headers for c in login_calls)


def test_failed_login_clears_bearer_token(auth, client, mocked_api):
    auth.login("user@example.com", "password")
    mocked_api.replace(responses.POST, str(Endpoints.USER_LOGIN), status=401)

    with pytest.raises(AuthenticationError):
        auth.login("user@example.com", "wrong-password")

    assert "Authorization" not in client.session.headers
    assert (auth.id_user, auth.id_application) == (None, None)
