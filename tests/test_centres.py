import json
import logging

import pytest
import requests
import responses
from responses import matchers

from pysportbot import Centre, SportBot
from pysportbot.centres import MAX_SPLITS, Centres
from pysportbot.client import ApiClient
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


def test_centres_fetched_once(mocked_api, centre_slug):
    bot = SportBot()

    bot.centres()
    bot.centres(search="test")
    bot.login("user@example.com", "password", centre_slug)

    assert len(_centre_calls(mocked_api)) == 1


def test_centres_returns_copy(mocked_api):
    bot = SportBot()

    bot.centres().clear()

    assert len(bot.centres()) == 3


def test_login_fetches_centres(mocked_api, centre_slug):
    SportBot().login("user@example.com", "password", centre_slug)

    assert len(_centre_calls(mocked_api)) == 1


def test_login_unknown_centre_raises_before_login_request(mocked_api, pysportbot_caplog):
    pysportbot_caplog.set_level(logging.INFO)

    with pytest.raises(CentreNotFoundError) as exc_info:
        SportBot().login("user@example.com", "password", "unknown")

    assert exc_info.value.centre == "unknown"
    assert [c.request.url for c in mocked_api.calls] == [str(Endpoints.CENTRE)]
    assert "test-centre, other-centre, third-centre" in pysportbot_caplog.text


def test_check_centre_unknown_raises(mocked_api):
    """`check_centre` rejects a slug that is not in the fetched centre list."""
    centres = Centres(ApiClient())

    with pytest.raises(CentreNotFoundError) as exc_info:
        centres.check_centre("unknown")

    assert exc_info.value.centre == "unknown"


def test_check_centre_valid_slug_passes(mocked_api, centre_slug):
    """`check_centre` accepts a slug returned by the centres endpoint."""
    centres = Centres(ApiClient())

    centres.check_centre(centre_slug)


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
@pytest.mark.parametrize(
    "call",
    [
        pytest.param(lambda bot: bot.centres(), id="centres"),
        pytest.param(lambda bot: bot.login("user@example.com", "password", "test-centre"), id="login"),
    ],
)
def test_fetch_centres_failure_raises_api_error(mocked_api, response_kwargs, status_code, call):
    """A failed centre fetch raises a clear APIError instead of `KeyError: 'slug'`."""
    mocked_api.replace(responses.POST, str(Endpoints.CENTRE), **response_kwargs)

    with pytest.raises(APIError) as exc_info:
        call(SportBot())

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


def test_fetch_centres_gives_up_after_max_splits(mocked_api):
    """An area that keeps failing is split MAX_SPLITS times, then the error is raised without trying other areas."""
    mocked_api.replace(responses.POST, str(Endpoints.CENTRE), status=500)

    with pytest.raises(APIError) as exc_info:
        SportBot().centres()

    assert exc_info.value.status_code == 500
    assert len(_centre_calls(mocked_api)) == MAX_SPLITS + 1


def test_fetch_centres_does_not_split_on_other_errors(mocked_api):
    mocked_api.replace(responses.POST, str(Endpoints.CENTRE), status=503)

    with pytest.raises(APIError):
        SportBot().centres()

    assert len(_centre_calls(mocked_api)) == 1
