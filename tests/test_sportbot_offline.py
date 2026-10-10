import json
from urllib.parse import parse_qs

import pytest
import responses

from pysportbot import (
    APIError,
    AuthenticationError,
    CancellationError,
    NotLoggedInError,
    SlotAlreadyBookedError,
    SlotFullError,
    SlotNotBookableYetError,
    SlotNotFoundError,
    SlotUnavailableError,
    SportBot,
)
from pysportbot.endpoints import Endpoints

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
    with pytest.raises(SlotNotFoundError) as exc_info:
        offline_bot.book("Gimnasio", f"{DAY} 23:00:00")

    assert exc_info.value.activity == "Gimnasio"
    assert exc_info.value.start == f"{DAY} 23:00:00"


def test_book_full_slot_raises_without_request(offline_bot, mocked_api):
    with pytest.raises(SlotFullError):
        offline_bot.book("Gimnasio", FULL_SLOT)

    assert _calls_to(mocked_api, Endpoints.BOOKING) == []


def test_book_success_sends_one_request(offline_bot, mocked_api):
    offline_bot.book("Gimnasio", OPEN_SLOT)

    calls = _calls_to(mocked_api, Endpoints.BOOKING)
    assert len(calls) == 1
    assert parse_qs(calls[0].request.body)["id_activity_calendar"] == [OPEN_SLOT_ID]


@pytest.mark.parametrize(
    ("error_code", "error_class"),
    [
        (5, SlotAlreadyBookedError),
        (6, SlotUnavailableError),
        (28, SlotNotBookableYetError),
    ],
)
def test_book_propagates_api_error(offline_bot, mocked_api, error_code, error_class):
    mocked_api.replace(responses.POST, str(Endpoints.BOOKING), json={"success": False, "error": error_code})

    with pytest.raises(error_class) as exc_info:
        offline_bot.book("Gimnasio", OPEN_SLOT)

    assert str(exc_info.value.slot_id) == OPEN_SLOT_ID
    assert exc_info.value.code == error_code


def test_cancel_propagates_api_error(offline_bot, mocked_api):
    mocked_api.replace(responses.POST, str(Endpoints.CANCELLATION), json={"success": False})

    with pytest.raises(CancellationError):
        offline_bot.cancel("Gimnasio", OPEN_SLOT)


def test_cancel_success_sends_one_request(offline_bot, mocked_api):
    offline_bot.cancel("Gimnasio", OPEN_SLOT)

    calls = _calls_to(mocked_api, Endpoints.CANCELLATION)
    assert len(calls) == 1
    assert parse_qs(calls[0].request.body)["id_activity_calendar"] == [OPEN_SLOT_ID]


def test_cancel_unknown_time_raises(offline_bot):
    with pytest.raises(SlotNotFoundError):
        offline_bot.cancel("Gimnasio", f"{DAY} 23:00:00")


@pytest.mark.parametrize("method", ["book", "cancel"])
def test_empty_calendar_raises_slot_not_found(offline_bot, mocked_api, method):
    mocked_api.replace(responses.POST, str(Endpoints.SLOTS), json={"data": {"activities_calendar": []}})

    with pytest.raises(SlotNotFoundError):
        getattr(offline_bot, method)("Gimnasio", OPEN_SLOT)


def test_failed_relogin_clears_activities(offline_bot, mocked_api, centre_slug):
    mocked_api.replace(responses.POST, str(Endpoints.USER_LOGIN), status=401)

    with pytest.raises(AuthenticationError):
        offline_bot.login("user@example.com", "wrong-password", centre_slug)

    with pytest.raises(NotLoggedInError):
        offline_bot.activities()


def test_activities_failure_after_authentication_logs_out(mocked_api, centre_slug):
    """If authentication succeeds but fetching activities fails, no authenticated state is left behind."""
    mocked_api.replace(responses.POST, str(Endpoints.SLOTS), status=500)
    bot = SportBot()

    with pytest.raises(APIError):
        bot.login("user@example.com", "password", centre_slug)

    assert bot.is_logged_in() is False
    assert bot._authenticator.authenticated is False
    assert bot._client._bearer is None


def test_login_failure_resets_state(mocked_api, centre_slug):
    mocked_api.replace(responses.POST, str(Endpoints.USER_LOGIN), status=401)
    bot = SportBot()

    with pytest.raises(AuthenticationError):
        bot.login("user@example.com", "wrong-password", centre_slug)

    assert bot.is_logged_in() is False
    with pytest.raises(NotLoggedInError):
        _ = bot.bookings_manager


@pytest.mark.parametrize("manager", ["activities_manager", "bookings_manager"])
def test_manager_requires_login(mocked_api, manager):
    bot = SportBot()

    with pytest.raises(NotLoggedInError):
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

    with pytest.raises(NotLoggedInError):
        call(bot)


def test_ensure_logged_in_keeps_valid_session(offline_bot, mocked_api):
    logins = len(_calls_to(mocked_api, Endpoints.USER_LOGIN))

    offline_bot.ensure_logged_in()

    assert len(_calls_to(mocked_api, Endpoints.USER_LOGIN)) == logins
    assert offline_bot.is_logged_in() is True


def test_ensure_logged_in_relogs_once_when_session_expired(offline_bot, mocked_api, payloads):
    logins = len(_calls_to(mocked_api, Endpoints.USER_LOGIN))
    # The session probe is rejected; the user request of the re-login then succeeds
    mocked_api.replace(responses.POST, str(Endpoints.USER), status=401)
    mocked_api.add(responses.POST, str(Endpoints.USER), json=payloads["user"])

    offline_bot.ensure_logged_in()

    login_calls = _calls_to(mocked_api, Endpoints.USER_LOGIN)
    assert len(login_calls) == logins + 1
    assert json.loads(login_calls[-1].request.body) == {"username": "user@example.com", "password": "password"}
    assert offline_bot.is_logged_in() is True


def test_ensure_logged_in_relogin_skips_activities_fetch(offline_bot, mocked_api, payloads):
    """Re-login right before a booking must not wait for the slow activities request."""
    slots_calls = len(_calls_to(mocked_api, Endpoints.SLOTS))
    mocked_api.replace(responses.POST, str(Endpoints.USER), status=401)
    mocked_api.add(responses.POST, str(Endpoints.USER), json=payloads["user"])

    offline_bot.ensure_logged_in()

    assert len(_calls_to(mocked_api, Endpoints.SLOTS)) == slots_calls
    assert len(offline_bot.activities()) > 0


def test_ensure_logged_in_failed_relogin_logs_out(offline_bot, mocked_api):
    mocked_api.replace(responses.POST, str(Endpoints.USER), status=401)
    mocked_api.replace(responses.POST, str(Endpoints.USER_LOGIN), status=500)

    with pytest.raises(AuthenticationError):
        offline_bot.ensure_logged_in()

    assert offline_bot.is_logged_in() is False
    assert offline_bot._client._bearer is None
    with pytest.raises(NotLoggedInError):
        offline_bot.activities()


def test_ensure_logged_in_after_failed_relogin_does_full_login(offline_bot, mocked_api, payloads):
    mocked_api.replace(responses.POST, str(Endpoints.USER), status=401)
    mocked_api.replace(responses.POST, str(Endpoints.USER_LOGIN), status=500)
    with pytest.raises(AuthenticationError):
        offline_bot.ensure_logged_in()
    mocked_api.replace(responses.POST, str(Endpoints.USER), json=payloads["user"])
    mocked_api.replace(responses.POST, str(Endpoints.USER_LOGIN), json=payloads["user_login"])
    slots_calls = len(_calls_to(mocked_api, Endpoints.SLOTS))

    offline_bot.ensure_logged_in()

    assert offline_bot.is_logged_in() is True
    assert len(_calls_to(mocked_api, Endpoints.SLOTS)) == slots_calls + 1


def test_ensure_logged_in_requires_login(mocked_api):
    bot = SportBot()

    with pytest.raises(NotLoggedInError):
        bot.ensure_logged_in()

    assert _calls_to(mocked_api, Endpoints.USER_LOGIN) == []


def test_ensure_logged_in_requires_successful_login(mocked_api, centre_slug):
    mocked_api.replace(responses.POST, str(Endpoints.USER_LOGIN), status=401)
    bot = SportBot()
    with pytest.raises(AuthenticationError):
        bot.login("user@example.com", "wrong-password", centre_slug)

    with pytest.raises(NotLoggedInError):
        bot.ensure_logged_in()
