import re
from urllib.parse import parse_qs

import pytest
import responses

from pysportbot import SportBot
from pysportbot.endpoints import Endpoints
from pysportbot.utils.errors import ErrorMessages

DAY = "2030-01-04"
FULL_SLOT = f"{DAY} 10:00:00"  # Gimnasio, n_inscribed == n_capacity
OPEN_SLOT = f"{DAY} 12:00:00"  # Gimnasio, places left
OPEN_SLOT_ID = "5004"


def _calls_to(mocked_api, endpoint):
    return [c for c in mocked_api.calls if c.request.url == str(endpoint)]


def test_activities_limit(offline_bot):
    assert len(offline_bot.activities(limit=1)) == 1


def test_daily_slots(offline_bot):
    slots = offline_bot.daily_slots("Gimnasio", DAY)

    assert set(slots["start_timestamp"]) == {FULL_SLOT, OPEN_SLOT}


def test_book_unknown_time_raises(offline_bot):
    with pytest.raises(IndexError):
        offline_bot.book("Gimnasio", f"{DAY} 23:00:00")


def test_book_full_slot_raises_without_request(offline_bot, mocked_api):
    with pytest.raises(ValueError, match=re.escape(ErrorMessages.slot_capacity_full())):
        offline_bot.book("Gimnasio", FULL_SLOT)

    assert _calls_to(mocked_api, Endpoints.BOOKING) == []


def test_book_success_sends_one_request(offline_bot, mocked_api):
    offline_bot.book("Gimnasio", OPEN_SLOT)

    calls = _calls_to(mocked_api, Endpoints.BOOKING)
    assert len(calls) == 1
    assert parse_qs(calls[0].request.body)["id_activity_calendar"] == [OPEN_SLOT_ID]


@pytest.mark.parametrize(
    ("error_code", "message"),
    [
        (5, ErrorMessages.slot_already_booked()),
        (6, ErrorMessages.slot_unavailable()),
        (28, ErrorMessages.slot_not_bookable_yet()),
    ],
)
def test_book_propagates_api_error(offline_bot, mocked_api, error_code, message):
    mocked_api.replace(responses.POST, str(Endpoints.BOOKING), json={"success": False, "error": error_code})

    with pytest.raises(ValueError, match=re.escape(message)):
        offline_bot.book("Gimnasio", OPEN_SLOT)


def test_cancel_propagates_api_error(offline_bot, mocked_api):
    mocked_api.replace(responses.POST, str(Endpoints.CANCELLATION), json={"success": False})

    with pytest.raises(ValueError, match=re.escape(ErrorMessages.cancellation_failed())):
        offline_bot.cancel("Gimnasio", OPEN_SLOT)


def test_cancel_success_sends_one_request(offline_bot, mocked_api):
    offline_bot.cancel("Gimnasio", OPEN_SLOT)

    calls = _calls_to(mocked_api, Endpoints.CANCELLATION)
    assert len(calls) == 1
    assert parse_qs(calls[0].request.body)["id_activity_calendar"] == [OPEN_SLOT_ID]


def test_cancel_unknown_time_raises(offline_bot):
    with pytest.raises(IndexError):
        offline_bot.cancel("Gimnasio", f"{DAY} 23:00:00")


def test_login_failure_resets_state(mocked_api, centre_slug):
    mocked_api.replace(responses.POST, str(Endpoints.USER_LOGIN), status=401)
    bot = SportBot()

    with pytest.raises(ValueError, match=re.escape(ErrorMessages.failed_login())):
        bot.login("user@example.com", "wrong-password", centre_slug)

    assert bot.is_logged_in() is False
    with pytest.raises(PermissionError):
        _ = bot.bookings_manager


@pytest.mark.parametrize("manager", ["activities_manager", "bookings_manager"])
def test_manager_requires_login(mocked_api, manager):
    bot = SportBot()

    with pytest.raises(PermissionError, match=re.escape(ErrorMessages.not_logged_in())):
        getattr(bot, manager)


@pytest.mark.parametrize(
    "call",
    [
        pytest.param(lambda bot: bot.activities(), id="activities"),
        pytest.param(lambda bot: bot.daily_slots("Gimnasio", DAY), id="daily_slots"),
        pytest.param(lambda bot: bot.book("Gimnasio", OPEN_SLOT), id="book"),
        pytest.param(lambda bot: bot.cancel("Gimnasio", OPEN_SLOT), id="cancel"),
    ],
)
def test_requires_activities_loaded(mocked_api, call):
    bot = SportBot()

    with pytest.raises(ValueError, match=re.escape(ErrorMessages.no_activities_loaded())):
        call(bot)
