import json
from unittest.mock import patch

import pytest
import requests
import responses
from responses import matchers

from pysportbot import Centre, SportBot
from pysportbot.centres import CENTRES_READ_TIMEOUT, MAX_SPLITS
from pysportbot.endpoints import Endpoints
from pysportbot.exceptions import APIError, CentreNotFoundError


def _centre_calls(mocked_api):
    return [c for c in mocked_api.calls if c.request.url == str(Endpoints.CENTRE)]


def test_sportbot_init_makes_no_http_calls(mocked_api):
    SportBot()

    assert len(mocked_api.calls) == 0


def test_centres_returns_models(mocked_api, payloads):
    centres = SportBot().centres()

    assert all(isinstance(c, Centre) for c in centres)
    assert [c.slug for c in centres] == [app["slug"] for app in payloads["centres"]["applications"]]
    assert centres[0] == Centre(
        slug="test-centre", name="Test Centre", town="Testville", country="Spain", address="Calle Falsa 123"
    )


@pytest.mark.parametrize(
    ("search", "expected"),
    [
        pytest.param("other", ["other-centre"], id="slug"),
        pytest.param("THIRD CENTRE", ["third-centre"], id="name-ignores-case"),
        pytest.param("testville", ["test-centre"], id="town"),
        pytest.param("centre", ["test-centre", "other-centre", "third-centre"], id="several"),
        pytest.param("madrid", [], id="no-match"),
        pytest.param("", ["test-centre", "other-centre", "third-centre"], id="empty"),
        pytest.param(None, ["test-centre", "other-centre", "third-centre"], id="none"),
    ],
)
def test_centres_search(mocked_api, search, expected):
    assert [c.slug for c in SportBot().centres(search=search)] == expected


def test_centres_search_skips_missing_town(mocked_api, payloads):
    payloads["centres"]["applications"][0]["address"] = {}
    mocked_api.replace(responses.POST, str(Endpoints.CENTRE), json=payloads["centres"])

    assert [c.slug for c in SportBot().centres(search="ville")] == ["other-centre", "third-centre"]


def test_centres_fetched_once(mocked_api):
    bot = SportBot()

    bot.centres()
    bot.centres(search="test")

    assert len(_centre_calls(mocked_api)) == 1


def test_centres_returns_copy(mocked_api):
    bot = SportBot()

    bot.centres().clear()

    assert len(bot.centres()) == 3


def test_login_does_not_fetch_centres(mocked_api, centre_slug):
    SportBot().login("user@example.com", "password", centre_slug)

    assert _centre_calls(mocked_api) == []


def test_login_unknown_centre_lists_account_centres(mocked_api, pysportbot_caplog):
    bot = SportBot()

    with pytest.raises(CentreNotFoundError) as exc_info:
        bot.login("user@example.com", "password", "unknown")

    assert (exc_info.value.centre, exc_info.value.available) == ("unknown", ["test-centre"])
    assert "test-centre" in pysportbot_caplog.text
    assert bot.is_logged_in() is False


# Content errors found after a 2xx response carry no status code
@pytest.mark.parametrize(
    ("response_kwargs", "status_code"),
    [
        pytest.param({"status": 500}, 500, id="non-200"),
        pytest.param({"body": "not json"}, 200, id="invalid-json"),
        pytest.param({"json": {}}, None, id="missing-applications"),
        pytest.param({"json": {"applications": []}}, None, id="empty"),
        pytest.param({"json": {"applications": {"slug": "x"}}}, None, id="not-a-list"),
        pytest.param({"json": {"applications": [{"slug": "no-name"}]}}, None, id="missing-name"),
        pytest.param({"json": {"applications": ["test-centre"]}}, None, id="not-an-object"),
        pytest.param({"body": requests.ConnectionError("connection refused")}, None, id="connection-error"),
    ],
)
def test_fetch_centres_failure_raises_api_error(mocked_api, response_kwargs, status_code):
    """A failed centre fetch raises a clear APIError instead of `KeyError: 'slug'`."""
    mocked_api.replace(responses.POST, str(Endpoints.CENTRE), **response_kwargs)

    with pytest.raises(APIError) as exc_info:
        SportBot().centres()

    assert exc_info.value.endpoint == str(Endpoints.CENTRE)
    assert exc_info.value.status_code == status_code


def test_failed_fetch_is_not_cached(mocked_api, payloads):
    # Not 500, which would be retried on smaller areas
    mocked_api.replace(responses.POST, str(Endpoints.CENTRE), status=503)
    mocked_api.add(responses.POST, str(Endpoints.CENTRE), json=payloads["centres"])
    bot = SportBot()

    with pytest.raises(APIError):
        bot.centres()

    assert len(bot.centres()) == 3


WORLD = {"south": -90, "west": -180, "north": 90, "east": 180}


def _bounds_of(call):
    return json.loads(call.request.body)["bounds"]


def test_fetch_centres_splits_area_on_500(mocked_api, payloads):
    """When the whole world returns HTTP 500, each half is fetched and the centres merged without duplicates."""
    apps = payloads["centres"]["applications"]
    mocked_api.remove(responses.POST, str(Endpoints.CENTRE))
    for bounds, response in [
        (WORLD, {"status": 500}),
        ({**WORLD, "east": 0}, {"json": {"applications": apps[:2]}}),
        # A centre on the dividing line is returned by both halves
        ({**WORLD, "west": 0}, {"json": {"applications": apps[1:]}}),
    ]:
        mocked_api.add(
            responses.POST, str(Endpoints.CENTRE), match=[matchers.json_params_matcher({"bounds": bounds})], **response
        )

    centres = SportBot().centres()

    assert [c.slug for c in centres] == ["test-centre", "other-centre", "third-centre"]
    assert [_bounds_of(c) for c in _centre_calls(mocked_api)] == [WORLD, {**WORLD, "east": 0}, {**WORLD, "west": 0}]


def test_fetch_centres_splits_area_on_read_timeout(mocked_api, payloads):
    mocked_api.remove(responses.POST, str(Endpoints.CENTRE))
    for bounds, response in [
        (WORLD, {"body": requests.ReadTimeout("read timed out")}),
        ({**WORLD, "east": 0}, {"json": {"applications": []}}),
        ({**WORLD, "west": 0}, {"json": payloads["centres"]}),
    ]:
        mocked_api.add(
            responses.POST, str(Endpoints.CENTRE), match=[matchers.json_params_matcher({"bounds": bounds})], **response
        )

    assert len(SportBot().centres()) == 3


def test_fetch_centres_split_halves_may_be_empty(mocked_api, payloads):
    """A half without centres is fine as long as the merged list is not empty."""
    mocked_api.remove(responses.POST, str(Endpoints.CENTRE))
    for bounds, response in [
        (WORLD, {"status": 500}),
        ({**WORLD, "east": 0}, {"json": {"applications": []}}),
        ({**WORLD, "west": 0}, {"json": payloads["centres"]}),
    ]:
        mocked_api.add(
            responses.POST, str(Endpoints.CENTRE), match=[matchers.json_params_matcher({"bounds": bounds})], **response
        )

    assert len(SportBot().centres()) == 3


@pytest.mark.parametrize(
    ("response_kwargs", "status_code"),
    [
        pytest.param({"status": 500}, 500, id="http-500"),
        pytest.param({"body": requests.ReadTimeout("read timed out")}, None, id="read-timeout"),
    ],
)
def test_fetch_centres_gives_up_after_max_splits(mocked_api, response_kwargs, status_code):
    """An area that keeps failing is split MAX_SPLITS times, then the error is raised without trying other areas."""
    mocked_api.replace(responses.POST, str(Endpoints.CENTRE), **response_kwargs)

    with pytest.raises(APIError) as exc_info:
        SportBot().centres()

    assert exc_info.value.status_code == status_code
    assert len(_centre_calls(mocked_api)) == MAX_SPLITS + 1


@pytest.mark.parametrize(
    "response_kwargs",
    [
        pytest.param({"status": 503}, id="non-500"),
        pytest.param({"body": requests.ConnectTimeout("connect timed out")}, id="connect-timeout"),
    ],
)
def test_fetch_centres_does_not_split_on_other_errors(mocked_api, response_kwargs):
    mocked_api.replace(responses.POST, str(Endpoints.CENTRE), **response_kwargs)

    with pytest.raises(APIError):
        SportBot().centres()

    assert len(_centre_calls(mocked_api)) == 1


def test_centres_request_uses_centres_timeout(mocked_api):
    bot = SportBot()

    with patch.object(bot._client.session, "request", wraps=bot._client.session.request) as request:
        bot.centres()

    assert request.call_args.kwargs["timeout"] == (5, CENTRES_READ_TIMEOUT)
