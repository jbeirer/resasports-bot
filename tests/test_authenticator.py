import json
from urllib.parse import parse_qs, urlsplit

import pytest
import requests
import responses

from pysportbot.authenticator import Authenticator
from pysportbot.client import ApiClient
from pysportbot.endpoints import Endpoints
from pysportbot.exceptions import AuthenticationError, CentreNotFoundError


@pytest.fixture
def client() -> ApiClient:
    return ApiClient()


@pytest.fixture
def auth(mocked_api, client) -> Authenticator:
    return Authenticator(client)


def _without(payload: dict, key: str) -> dict:
    return {k: v for k, v in payload.items() if k != key}


def test_login_success(auth, client, mocked_api, payloads):
    auth.login("user@example.com", "password", "test-centre")

    [login_call] = [c for c in mocked_api.calls if c.request.url == str(Endpoints.USER_LOGIN)]
    assert json.loads(login_call.request.body) == {"username": "user@example.com", "password": "password"}

    login_app = payloads["user_login"]["applications"][0]
    assert auth.authenticated is True
    assert auth.id_application == str(login_app["id_application"])
    assert auth.id_user == str(login_app["id_user"])
    [user_call] = [c for c in mocked_api.calls if c.request.url == str(Endpoints.USER)]
    assert user_call.request.headers["Authorization"] == f"Bearer {payloads['sport_user_token']['jwt_token']}"
    assert auth.user_id == str(payloads["user"]["data"]["user"]["id_user"])


def test_sport_user_token_request_uses_resasocial_bearer(auth, mocked_api, payloads):
    auth.login("user@example.com", "password", "test-centre")

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
        auth.login("user@example.com", "password", "test-centre")

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
        auth.login("user@example.com", "password", "test-centre")

    assert exc_info.value.reason == reason


def test_login_wraps_unexpected_error(auth, mocked_api):
    error = requests.ConnectionError("connection refused")
    mocked_api.replace(responses.POST, str(Endpoints.USER_LOGIN), body=error)

    with pytest.raises(AuthenticationError) as exc_info:
        auth.login("user@example.com", "password", "test-centre")

    assert exc_info.value.__cause__ is error
    assert auth.authenticated is False


def test_session_invalid_before_login(auth, mocked_api):
    assert auth.is_session_valid() is False
    assert len(mocked_api.calls) == 0


def test_session_valid_after_login(auth):
    auth.login("user@example.com", "password", "test-centre")

    assert auth.is_session_valid() is True


@pytest.mark.parametrize(
    "response_kwargs",
    [
        pytest.param({"status": 401}, id="non-200"),
        pytest.param({"body": requests.ConnectionError("connection refused")}, id="connection-error"),
    ],
)
def test_session_invalid_on_user_failure(auth, mocked_api, response_kwargs):
    auth.login("user@example.com", "password", "test-centre")
    mocked_api.replace(responses.POST, str(Endpoints.USER), **response_kwargs)

    assert auth.is_session_valid() is False


def test_session_invalid_on_non_object_user_data(auth, mocked_api):
    auth.login("user@example.com", "password", "test-centre")
    mocked_api.replace(responses.POST, str(Endpoints.USER), json={"data": []})

    assert auth.is_session_valid() is False


def _application_url(id_application) -> str:
    return Endpoints.APPLICATION.format(id_application=id_application)


def test_login_selects_the_requested_centre(auth, mocked_api, payloads):
    """With several applications, login looks them up in order and uses the one whose slug is the centre."""
    first = payloads["user_login"]["applications"][0]
    second = {"id_application": 4321, "id_user": 8765}
    mocked_api.replace(
        responses.POST,
        str(Endpoints.USER_LOGIN),
        json={**payloads["user_login"], "applications": [first, second]},
    )
    mocked_api.add(responses.GET, _application_url(4321), json={**payloads["application"], "slug": "other-centre"})

    auth.login("user@example.com", "password", "other-centre")

    assert (auth.id_user, auth.id_application) == ("8765", "4321")
    [token_call] = [c for c in mocked_api.calls if c.request.url.startswith(str(Endpoints.SPORT_USER_TOKEN))]
    assert parse_qs(urlsplit(token_call.request.url).query) == {"id_user": ["8765"], "id_application": ["4321"]}


def test_login_stops_looking_up_at_the_matching_centre(auth, mocked_api, payloads):
    first = payloads["user_login"]["applications"][0]
    mocked_api.replace(
        responses.POST,
        str(Endpoints.USER_LOGIN),
        json={**payloads["user_login"], "applications": [first, {"id_application": 4321, "id_user": 8765}]},
    )

    auth.login("user@example.com", "password", "test-centre")

    assert [c.request.url for c in mocked_api.calls if "/application/" in c.request.url] == [_application_url(1234)]


def test_login_unknown_centre_raises_centre_not_found(auth, client, mocked_api):
    with pytest.raises(CentreNotFoundError) as exc_info:
        auth.login("user@example.com", "password", "unknown")

    assert exc_info.value.available == ["test-centre"]
    assert auth.authenticated is False
    assert (auth.id_user, auth.id_application) == (None, None)
    assert not any(c.request.url.startswith(str(Endpoints.SPORT_USER_TOKEN)) for c in mocked_api.calls)


@pytest.mark.parametrize(
    ("response_kwargs", "reason"),
    [
        pytest.param({"status": 404}, "centre lookup returned HTTP 404", id="non-200"),
        pytest.param({"json": {"name": "Test Centre"}}, "no slug in centre lookup response", id="missing-slug"),
    ],
)
def test_login_centre_lookup_failure_raises(auth, mocked_api, response_kwargs, reason):
    mocked_api.replace(responses.GET, _application_url(1234), **response_kwargs)

    with pytest.raises(AuthenticationError) as exc_info:
        auth.login("user@example.com", "password", "test-centre")

    assert exc_info.value.reason == reason


def test_relogin_does_not_send_stale_token(auth, mocked_api):
    auth.login("user@example.com", "password", "test-centre")
    auth.login("user@example.com", "password", "test-centre")

    login_calls = [c for c in mocked_api.calls if c.request.url == str(Endpoints.USER_LOGIN)]
    assert all("Authorization" not in c.request.headers for c in login_calls)


def test_failed_login_clears_bearer_token(auth, client, mocked_api):
    auth.login("user@example.com", "password", "test-centre")
    mocked_api.replace(responses.POST, str(Endpoints.USER_LOGIN), status=401)

    with pytest.raises(AuthenticationError):
        auth.login("user@example.com", "wrong-password", "test-centre")

    assert client._bearer is None
    assert (auth.id_user, auth.id_application) == (None, None)


def test_nubapp_token_is_not_sent_to_resasocial(auth, client, mocked_api):
    auth.login("user@example.com", "password", "test-centre")

    client.post_json(Endpoints.CENTRE, json={})

    [centre_call] = [c for c in mocked_api.calls if c.request.url == str(Endpoints.CENTRE)]
    assert "Authorization" not in centre_call.request.headers
