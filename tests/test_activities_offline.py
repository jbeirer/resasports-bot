from datetime import date, datetime, timedelta
from unittest.mock import patch
from urllib.parse import parse_qs

import pytest
import pytz
import responses

from pysportbot import SportBot
from pysportbot.activities import SLOTS_READ_TIMEOUT, Activities
from pysportbot.authenticator import Authenticator
from pysportbot.endpoints import Endpoints
from pysportbot.exceptions import ActivityNotFoundError, APIError
from pysportbot.session import Session

ACTIVITY_COLUMNS = ["id_activity", "name_activity", "id_category_activity"]
DAY = "2030-01-04"
EMPTY_CALENDAR = {"data": {"activities_calendar": []}}
# 00:30 on 2030-01-04 in Madrid, but still 2030-01-03 in UTC
FROZEN_UTC = datetime(2030, 1, 3, 23, 30, tzinfo=pytz.utc)


def _frozen_now(tz=None):
    """`datetime.now` on a machine whose local clock is UTC, frozen at FROZEN_UTC."""
    return FROZEN_UTC.astimezone(tz) if tz else FROZEN_UTC.replace(tzinfo=None)


@pytest.fixture
def activities(mocked_api) -> Activities:
    auth = Authenticator(Session(), "test-centre")
    auth.login("user@example.com", "password")
    return Activities(auth)


def _slots_calls(mocked_api):
    return [c for c in mocked_api.calls if c.request.url == str(Endpoints.SLOTS)]


def test_fetch_dedupes_by_id_activity(activities, payloads):
    df = activities.fetch()

    calendar = payloads["activities_calendar"]["data"]["activities_calendar"]
    unique_ids = list(dict.fromkeys(slot["id_activity"] for slot in calendar))
    assert len(calendar) > len(unique_ids), "fixture should contain duplicate id_activity values"
    assert list(df.columns) == ACTIVITY_COLUMNS
    assert df["id_activity"].tolist() == unique_ids


def test_fetch_sends_user_and_week_window(activities, mocked_api, payloads):
    activities.fetch()

    body = parse_qs(_slots_calls(mocked_api)[-1].request.body)
    login_app = payloads["user_login"]["applications"][0]
    assert body["id_application"] == [str(login_app["id_application"])]
    assert body["id_user"] == [str(login_app["id_user"])]
    [start], [end] = body["start_timestamp"], body["end_timestamp"]
    assert date.fromisoformat(end) - date.fromisoformat(start) == timedelta(days=7)


def test_fetch_empty_calendar(activities, mocked_api):
    mocked_api.replace(responses.POST, str(Endpoints.SLOTS), json=EMPTY_CALENDAR)

    df = activities.fetch()

    assert df.empty
    assert list(df.columns) == ACTIVITY_COLUMNS


@pytest.mark.parametrize(
    "response_kwargs",
    [
        pytest.param({"status": 500}, id="non-200"),
        pytest.param({"body": "not json"}, id="invalid-json"),
        pytest.param({"json": {"data": {}}}, id="missing-key"),
    ],
)
def test_fetch_failure_raises(activities, mocked_api, response_kwargs):
    mocked_api.replace(responses.POST, str(Endpoints.SLOTS), **response_kwargs)

    with pytest.raises(APIError):
        activities.fetch()


def test_daily_slots_filters_to_activity(activities, payloads):
    df_activities = activities.fetch()

    df = activities.daily_slots(df_activities, "Yoga", DAY)

    calendar = payloads["activities_calendar"]["data"]["activities_calendar"]
    expected = [s["id_activity_calendar"] for s in calendar if s["name_activity"] == "Yoga"]
    assert len(expected) >= 2, "fixture should contain the same activity at two times"
    assert set(df["name_activity"]) == {"Yoga"}
    assert df["id_activity_calendar"].tolist() == expected


def test_daily_slots_request_body(activities, mocked_api, payloads):
    df_activities = activities.fetch()

    activities.daily_slots(df_activities, "Yoga", DAY)

    calendar = payloads["activities_calendar"]["data"]["activities_calendar"]
    yoga_category = next(s["id_category_activity"] for s in calendar if s["name_activity"] == "Yoga")
    login_app = payloads["user_login"]["applications"][0]
    assert parse_qs(_slots_calls(mocked_api)[-1].request.body) == {
        "id_application": [str(login_app["id_application"])],
        "id_user": [str(login_app["id_user"])],
        "start_timestamp": [DAY],
        "end_timestamp": [DAY],
        "id_category_activity": [str(yoga_category)],
    }


def test_daily_slots_unknown_activity_raises(activities):
    df_activities = activities.fetch()

    with pytest.raises(ActivityNotFoundError) as exc_info:
        activities.daily_slots(df_activities, "Zumba", DAY)

    assert exc_info.value.activity == "Zumba"
    assert exc_info.value.available == df_activities["name_activity"].tolist()


def test_daily_slots_empty_calendar(activities, mocked_api):
    df_activities = activities.fetch()
    mocked_api.replace(responses.POST, str(Endpoints.SLOTS), json=EMPTY_CALENDAR)

    df = activities.daily_slots(df_activities, "Yoga", DAY)

    assert df.empty


@pytest.mark.parametrize(
    "response_kwargs",
    [
        pytest.param({"status": 500}, id="non-200"),
        pytest.param({"body": "not json"}, id="invalid-json"),
        pytest.param({"json": {"data": {}}}, id="missing-key"),
    ],
)
def test_daily_slots_failure_raises(activities, mocked_api, response_kwargs):
    df_activities = activities.fetch()
    mocked_api.replace(responses.POST, str(Endpoints.SLOTS), **response_kwargs)

    with pytest.raises(APIError):
        activities.daily_slots(df_activities, "Yoga", DAY)


def test_daily_slots_no_matching_activity(activities, mocked_api, payloads):
    df_activities = activities.fetch()
    calendar = payloads["activities_calendar"]["data"]["activities_calendar"]
    others = [s for s in calendar if s["name_activity"] != "Yoga"]
    mocked_api.replace(responses.POST, str(Endpoints.SLOTS), json={"data": {"activities_calendar": others}})

    df = activities.daily_slots(df_activities, "Yoga", DAY)

    assert df.empty


@pytest.mark.parametrize(
    ("time_zone", "expected_start"),
    [
        ("Europe/Madrid", "2030-01-04"),
        ("America/New_York", "2030-01-03"),
    ],
)
def test_fetch_window_uses_configured_time_zone(mocked_api, time_zone, expected_start):
    auth = Authenticator(Session(), "test-centre")
    auth.login("user@example.com", "password")
    activities = Activities(auth, time_zone=time_zone)

    with patch("pysportbot.activities.datetime", wraps=datetime) as mock_datetime:
        mock_datetime.now.side_effect = _frozen_now
        activities.fetch()

    body = parse_qs(_slots_calls(mocked_api)[-1].request.body)
    assert body["start_timestamp"] == [expected_start]


def test_sportbot_passes_time_zone_to_activities(mocked_api, centre_slug):
    bot = SportBot(time_zone="Europe/Madrid")

    with patch("pysportbot.activities.datetime", wraps=datetime) as mock_datetime:
        mock_datetime.now.side_effect = _frozen_now
        bot.login("user@example.com", "password", centre_slug)

    body = parse_qs(_slots_calls(mocked_api)[-1].request.body)
    assert body["start_timestamp"] == ["2030-01-04"]


@pytest.mark.parametrize("method", ["fetch", "daily_slots"])
def test_requests_use_slots_timeout(activities, method):
    df_activities = activities.fetch()
    args = (df_activities, "Yoga", DAY) if method == "daily_slots" else ()

    with patch.object(activities.session, "post", wraps=activities.session.post) as post:
        getattr(activities, method)(*args)

    assert post.call_args.kwargs["timeout"] == (5, SLOTS_READ_TIMEOUT)
