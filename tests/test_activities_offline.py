from datetime import UTC, date, datetime, timedelta
from unittest.mock import patch
from urllib.parse import parse_qs
from zoneinfo import ZoneInfo

import pytest
import responses

from pysportbot import Activity, SportBot
from pysportbot.activities import SLOTS_READ_TIMEOUT, Activities
from pysportbot.authenticator import Authenticator
from pysportbot.client import ApiClient
from pysportbot.endpoints import Endpoints
from pysportbot.exceptions import ActivityNotFoundError, APIError

DAY = "2030-01-04"
EMPTY_CALENDAR = {"data": {"activities_calendar": []}}
# 00:30 on 2030-01-04 in Madrid, but still 2030-01-03 in UTC
FROZEN_UTC = datetime(2030, 1, 3, 23, 30, tzinfo=UTC)


def _frozen_now(tz=None):
    """`datetime.now` on a machine whose local clock is UTC, frozen at FROZEN_UTC."""
    return FROZEN_UTC.astimezone(tz) if tz else FROZEN_UTC.replace(tzinfo=None)


@pytest.fixture
def activities(mocked_api) -> Activities:
    client = ApiClient()
    auth = Authenticator(client)
    auth.login("user@example.com", "password", "test-centre")
    return Activities(client, auth)


def _slots_calls(mocked_api):
    return [c for c in mocked_api.calls if c.request.url == str(Endpoints.SLOTS)]


def test_fetch_dedupes_by_id_activity(activities, payloads):
    result = activities.fetch()

    calendar = payloads["activities_calendar"]["data"]["activities_calendar"]
    unique_ids = list(dict.fromkeys(slot["id_activity"] for slot in calendar))
    assert len(calendar) > len(unique_ids), "fixture should contain duplicate id_activity values"
    assert [a.id for a in result] == unique_ids
    assert result[0] == Activity(id=101, name="Yoga", category_id=10)


def test_fetch_keeps_first_occurrence_and_coerces_ids(activities, mocked_api, payloads):
    calendar = payloads["activities_calendar"]["data"]["activities_calendar"]
    # The same activity with its id as a string, under a different name: the first entry wins
    duplicate = {**calendar[0], "id_activity": str(calendar[0]["id_activity"]), "name_activity": "Yoga (renamed)"}
    mocked_api.replace(
        responses.POST, str(Endpoints.SLOTS), json={"data": {"activities_calendar": [*calendar, duplicate]}}
    )

    result = activities.fetch()

    assert [a.name for a in result] == ["Yoga", "Gimnasio", "Pilates"]


def test_fetch_sends_user_and_week_window(activities, mocked_api, payloads):
    activities.fetch()

    body = parse_qs(_slots_calls(mocked_api)[-1].request.body)
    login_app = payloads["user_login"]["applications"][0]
    assert body["id_application"] == [str(login_app["id_application"])]
    assert body["id_user"] == [str(login_app["id_user"])]
    [start], [end] = body["start_timestamp"], body["end_timestamp"]
    assert date.fromisoformat(end) - date.fromisoformat(start) == timedelta(days=7)


@pytest.mark.parametrize("calendar", [pytest.param([], id="empty"), pytest.param(None, id="null")])
def test_fetch_empty_calendar(activities, mocked_api, calendar):
    mocked_api.replace(responses.POST, str(Endpoints.SLOTS), json={"data": {"activities_calendar": calendar}})

    assert activities.fetch() == []


@pytest.mark.parametrize(
    "response_kwargs",
    [
        pytest.param({"status": 500}, id="non-200"),
        pytest.param({"body": "not json"}, id="invalid-json"),
        pytest.param({"json": {"data": {}}}, id="missing-key"),
        pytest.param({"json": {"data": {"activities_calendar": {"id_activity": 1}}}}, id="not-a-list"),
        pytest.param({"json": {"data": {"activities_calendar": [{"name_activity": "Yoga"}]}}}, id="missing-field"),
    ],
)
def test_fetch_failure_raises(activities, mocked_api, response_kwargs):
    mocked_api.replace(responses.POST, str(Endpoints.SLOTS), **response_kwargs)

    with pytest.raises(APIError):
        activities.fetch()


def test_daily_slots_filters_to_activity(activities, payloads):
    acts = activities.fetch()

    slots = activities.daily_slots(acts, "Yoga", DAY)

    calendar = payloads["activities_calendar"]["data"]["activities_calendar"]
    expected = [s["id_activity_calendar"] for s in calendar if s["name_activity"] == "Yoga"]
    assert len(expected) >= 2, "fixture should contain the same activity at two times"
    assert {s.activity_name for s in slots} == {"Yoga"}
    assert [s.id for s in slots] == expected


def test_daily_slots_matches_str_activity_ids(activities, mocked_api, payloads):
    """The API may send ids as strings; the filter compares them as integers."""
    acts = activities.fetch()
    calendar = payloads["activities_calendar"]["data"]["activities_calendar"]
    as_str = [{**s, "id_activity": str(s["id_activity"])} for s in calendar]
    mocked_api.replace(responses.POST, str(Endpoints.SLOTS), json={"data": {"activities_calendar": as_str}})

    slots = activities.daily_slots(acts, "Yoga", DAY)

    assert [s.id for s in slots] == [5001, 5003]


@pytest.mark.parametrize("time_zone", ["Europe/Madrid", "America/New_York"])
def test_daily_slots_times_in_configured_time_zone(mocked_api, time_zone):
    client = ApiClient()
    auth = Authenticator(client)
    auth.login("user@example.com", "password", "test-centre")
    activities = Activities(client, auth, time_zone=time_zone)

    slots = activities.daily_slots(activities.fetch(), "Yoga", DAY)

    assert slots[0].start == datetime(2030, 1, 4, 9, tzinfo=ZoneInfo(time_zone))


def test_daily_slots_malformed_entry_of_other_activity_raises(activities, mocked_api, payloads):
    """The calendar covers the whole category; a malformed entry of another activity fails loudly too."""
    acts = activities.fetch()
    calendar = payloads["activities_calendar"]["data"]["activities_calendar"]
    pilates = next(s for s in calendar if s["name_activity"] == "Pilates")
    assert pilates["id_category_activity"] == next(a.category_id for a in acts if a.name == "Yoga")
    del pilates["n_capacity"]
    mocked_api.replace(responses.POST, str(Endpoints.SLOTS), json=payloads["activities_calendar"])

    with pytest.raises(APIError, match="'n_capacity'"):
        activities.daily_slots(acts, "Yoga", DAY)


def test_daily_slots_malformed_entry_raises(activities, mocked_api, payloads):
    acts = activities.fetch()
    calendar = payloads["activities_calendar"]["data"]["activities_calendar"]
    del calendar[0]["start_timestamp"]
    mocked_api.replace(responses.POST, str(Endpoints.SLOTS), json=payloads["activities_calendar"])

    with pytest.raises(APIError, match="'start_timestamp'"):
        activities.daily_slots(acts, "Yoga", DAY)


def test_daily_slots_request_body(activities, mocked_api, payloads):
    acts = activities.fetch()

    activities.daily_slots(acts, "Yoga", DAY)

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


@pytest.mark.parametrize(
    "day",
    [
        pytest.param(DAY.replace("-", ""), id="basic-iso"),
        pytest.param(date(2030, 1, 4), id="date"),
        pytest.param(datetime(2030, 1, 4, 18, 30), id="datetime"),
    ],
)
def test_daily_slots_sends_canonical_date(activities, mocked_api, day):
    acts = activities.fetch()

    activities.daily_slots(acts, "Yoga", day)

    body = parse_qs(_slots_calls(mocked_api)[-1].request.body)
    assert body["start_timestamp"] == body["end_timestamp"] == [DAY]


@pytest.mark.parametrize("day", ["2030-13-01", "2030-02-30", "04/01/2030", "tomorrow", ""])
def test_daily_slots_invalid_day_raises_before_request(activities, mocked_api, day):
    acts = activities.fetch()
    n_calls = len(mocked_api.calls)

    with pytest.raises(ValueError, match=f"Invalid day '{day}'"):
        activities.daily_slots(acts, "Yoga", day)

    assert len(mocked_api.calls) == n_calls


def test_daily_slots_unknown_activity_raises(activities):
    acts = activities.fetch()

    with pytest.raises(ActivityNotFoundError) as exc_info:
        activities.daily_slots(acts, "Zumba", DAY)

    assert exc_info.value.activity == "Zumba"
    assert exc_info.value.available == [a.name for a in acts]


def test_daily_slots_empty_calendar(activities, mocked_api):
    acts = activities.fetch()
    mocked_api.replace(responses.POST, str(Endpoints.SLOTS), json=EMPTY_CALENDAR)

    assert activities.daily_slots(acts, "Yoga", DAY) == []


@pytest.mark.parametrize(
    "response_kwargs",
    [
        pytest.param({"status": 500}, id="non-200"),
        pytest.param({"body": "not json"}, id="invalid-json"),
        pytest.param({"json": {"data": {}}}, id="missing-key"),
    ],
)
def test_daily_slots_failure_raises(activities, mocked_api, response_kwargs):
    acts = activities.fetch()
    mocked_api.replace(responses.POST, str(Endpoints.SLOTS), **response_kwargs)

    with pytest.raises(APIError):
        activities.daily_slots(acts, "Yoga", DAY)


def test_daily_slots_no_matching_activity(activities, mocked_api, payloads):
    acts = activities.fetch()
    calendar = payloads["activities_calendar"]["data"]["activities_calendar"]
    others = [s for s in calendar if s["name_activity"] != "Yoga"]
    mocked_api.replace(responses.POST, str(Endpoints.SLOTS), json={"data": {"activities_calendar": others}})

    assert activities.daily_slots(acts, "Yoga", DAY) == []


@pytest.mark.parametrize(
    ("time_zone", "expected_start", "expected_end"),
    [
        ("Europe/Madrid", "2030-01-04", "2030-01-11"),
        ("America/New_York", "2030-01-03", "2030-01-10"),
    ],
)
def test_fetch_window_uses_configured_time_zone(mocked_api, time_zone, expected_start, expected_end):
    client = ApiClient()
    auth = Authenticator(client)
    auth.login("user@example.com", "password", "test-centre")
    activities = Activities(client, auth, time_zone=time_zone)

    with patch("pysportbot.activities.datetime", wraps=datetime) as mock_datetime:
        mock_datetime.now.side_effect = _frozen_now
        activities.fetch()

    body = parse_qs(_slots_calls(mocked_api)[-1].request.body)
    assert body["start_timestamp"] == [expected_start]
    assert body["end_timestamp"] == [expected_end]


def test_sportbot_passes_time_zone_to_activities(mocked_api, centre_slug):
    bot = SportBot(time_zone="Europe/Madrid")

    with patch("pysportbot.activities.datetime", wraps=datetime) as mock_datetime:
        mock_datetime.now.side_effect = _frozen_now
        bot.login("user@example.com", "password", centre_slug)

    body = parse_qs(_slots_calls(mocked_api)[-1].request.body)
    assert body["start_timestamp"] == ["2030-01-04"]


@pytest.mark.parametrize("method", ["fetch", "daily_slots"])
def test_requests_use_slots_timeout(activities, method):
    acts = activities.fetch()
    args = (acts, "Yoga", DAY) if method == "daily_slots" else ()

    with patch.object(activities.client.session, "request", wraps=activities.client.session.request) as post:
        getattr(activities, method)(*args)

    assert post.call_args.kwargs["timeout"] == (5, SLOTS_READ_TIMEOUT)
