import itertools
import json
import threading
from datetime import datetime, time, timedelta
from unittest.mock import MagicMock, call
from zoneinfo import ZoneInfo

import pytest
import requests
import responses

from pysportbot.endpoints import Endpoints
from pysportbot.exceptions import (
    ActivityNotFoundError,
    APIError,
    BookingError,
    NotLoggedInError,
    SlotAlreadyBookedError,
    SlotFullError,
    SlotNotBookableYetError,
    SlotNotFoundError,
    SlotUnavailableError,
)
from pysportbot.service.booking import attempt_booking, schedule_bookings
from pysportbot.service.config import ClassSpec, ServiceConfig, WeeklyTime
from pysportbot.service.results import BookingResult, BookingStatus, log_summary
from pysportbot.service.retry import RetryPolicy, classify
from pysportbot.service.scheduling import wait_until

MADRID = ZoneInfo("Europe/Madrid")
FRIDAY = 4
# The fixture's Gimnasio slots on Friday 2030-01-04
OPEN_SLOT_START = datetime(2030, 1, 4, 12, 0, tzinfo=MADRID)  # places left, slot 5004
FULL_SLOT_START = datetime(2030, 1, 4, 10, 0, tzinfo=MADRID)  # n_inscribed == n_capacity, slot 5002
GYM = ClassSpec("Gimnasio", FRIDAY, time(12, 0))
POLICY = RetryPolicy(retry_attempts=3, retry_delay=1, poll_interval=0.5, poll_window=60)

BOOKED = {"json": {"success": True}}
ALREADY_BOOKED = {"json": {"success": False, "error": 5}}
UNAVAILABLE = {"json": {"success": False, "error": 6}}
NOT_BOOKABLE_YET = {"json": {"success": False, "error": 28}}
UNKNOWN_ERROR = {"json": {"success": False, "error": 99}}
SERVER_ERROR = {"status": 500}
READ_TIMEOUT = {"body": requests.exceptions.ReadTimeout("Read timed out.")}
CONNECTION_ERROR = {"body": requests.exceptions.ConnectionError("Connection reset.")}


def _answer_bookings(mocked_api, *answers):
    """Answer the booking requests in this order; the last answer repeats."""
    mocked_api.remove(responses.POST, str(Endpoints.BOOKING))
    for answer in answers:
        mocked_api.add(responses.POST, str(Endpoints.BOOKING), **answer)


def _urls(mocked_api, since=0):
    return [c.request.url for c in mocked_api.calls[since:]]


def _booking_calls(mocked_api):
    return [url for url in _urls(mocked_api) if url == str(Endpoints.BOOKING)]


@pytest.fixture
def attempt(offline_bot, fake_clock):
    """Run `attempt_booking` for the open Gimnasio slot on the fake clock; returns the result and the sleep mock."""

    def run(policy=POLICY, start=OPEN_SLOT_START, **kwargs):
        sleep = MagicMock(side_effect=fake_clock.sleep)
        spec = ClassSpec("Gimnasio", FRIDAY, start.time())
        result = attempt_booking(offline_bot, spec, start, policy, clock=fake_clock.monotonic, sleep=sleep, **kwargs)
        return result, sleep

    return run


# classify and RetryPolicy


@pytest.mark.parametrize(
    ("error", "action"),
    [
        (SlotNotBookableYetError("1", 28), "poll"),
        (SlotUnavailableError("1", 6), "poll"),
        (SlotNotFoundError("Yoga", "2030-01-04 12:00:00"), "poll"),
        (APIError("Unexpected HTTP status", endpoint="x", status_code=500), "retry"),
        (BookingError("1", 99), "retry"),
        (requests.exceptions.ReadTimeout(), "retry"),
        (requests.exceptions.ConnectionError(), "retry"),
        (SlotAlreadyBookedError("1", 5), "stop"),
        (SlotFullError("1"), "stop"),
        (NotLoggedInError(), "stop"),
        (ActivityNotFoundError("Zumba", ["Yoga"]), "stop"),
        (ValueError("bug"), "stop"),
    ],
    ids=lambda value: type(value).__name__ if isinstance(value, Exception) else value,
)
def test_classify(error, action):
    assert classify(error) == action


@pytest.mark.parametrize(
    ("kwargs", "name"),
    [
        ({"retry_attempts": 0}, "retry_attempts"),
        ({"retry_delay": -1}, "retry_delay"),
        ({"retry_delay": float("nan")}, "retry_delay"),
        ({"poll_interval": 0}, "poll_interval"),
        ({"poll_interval": float("inf")}, "poll_interval"),
        ({"poll_window": -0.5}, "poll_window"),
    ],
)
def test_retry_policy_rejects_invalid_values(kwargs, name):
    with pytest.raises(ValueError, match=name):
        RetryPolicy(**kwargs)


@pytest.mark.parametrize(
    ("status", "ok"),
    [
        (BookingStatus.BOOKED, True),
        (BookingStatus.ALREADY_BOOKED, True),
        (BookingStatus.DRY_RUN, True),
        (BookingStatus.FULL, False),
        (BookingStatus.NOT_FOUND, False),
        (BookingStatus.FAILED, False),
    ],
)
def test_booking_result_ok(status, ok):
    assert BookingResult(GYM, OPEN_SLOT_START, status, attempts=1).ok is ok


# attempt_booking


def test_attempt_booking_success(attempt, mocked_api):
    result, sleep = attempt()

    assert result.status == BookingStatus.BOOKED
    assert result.attempts == 1
    assert result.slot is not None and result.slot.id == 5004
    assert result.error is None
    sleep.assert_not_called()


def test_polls_while_not_bookable_yet(attempt, mocked_api):
    _answer_bookings(mocked_api, NOT_BOOKABLE_YET, NOT_BOOKABLE_YET, NOT_BOOKABLE_YET, BOOKED)

    result, sleep = attempt()

    assert result.status == BookingStatus.BOOKED
    assert result.attempts == 4
    assert sleep.call_args_list == [call(0.5)] * 3


def test_polls_while_unavailable(attempt, mocked_api):
    _answer_bookings(mocked_api, UNAVAILABLE, BOOKED)

    result, sleep = attempt()

    assert result.status == BookingStatus.BOOKED
    sleep.assert_called_once_with(0.5)


def test_gives_up_polling_after_poll_window(attempt, mocked_api, fake_clock):
    _answer_bookings(mocked_api, NOT_BOOKABLE_YET)

    result, sleep = attempt(RetryPolicy(retry_attempts=1, poll_interval=0.5, poll_window=2))

    assert result.status == BookingStatus.FAILED
    assert not result.ok
    assert "not bookable" in result.error
    # Attempts at 0, 0.5, 1, 1.5 and 2 s: polls do not use up the retry attempts
    assert result.attempts == 5
    assert sleep.call_args_list == [call(0.5)] * 4
    assert fake_clock.elapsed == 2


def test_last_poll_happens_at_end_of_poll_window(attempt, mocked_api, fake_clock):
    _answer_bookings(mocked_api, NOT_BOOKABLE_YET)

    result, sleep = attempt(RetryPolicy(poll_interval=0.5, poll_window=1.2))

    assert sleep.call_args_list == [call(0.5), call(0.5), call(pytest.approx(0.2))]
    assert fake_clock.elapsed == pytest.approx(1.2)
    assert result.attempts == 4


def test_deadline_passing_between_clock_reads_does_not_crash(offline_bot, mocked_api):
    _answer_bookings(mocked_api, NOT_BOOKABLE_YET)
    # Just before the deadline on the first read, past it on any later read
    clock = MagicMock(side_effect=itertools.chain([0.9], itertools.repeat(1.1)))
    sleeps = []

    def sleep(seconds):
        if seconds < 0:
            raise ValueError("sleep length must be non-negative")  # As time.sleep
        sleeps.append(seconds)

    result = attempt_booking(offline_bot, GYM, OPEN_SLOT_START, POLICY, poll_until=1.0, clock=clock, sleep=sleep)

    assert result.status == BookingStatus.FAILED
    assert sleeps == [pytest.approx(0.1)]


def test_stops_when_already_booked(attempt, mocked_api):
    _answer_bookings(mocked_api, ALREADY_BOOKED)

    result, sleep = attempt()

    assert result.status == BookingStatus.ALREADY_BOOKED
    assert result.ok
    assert result.attempts == 1
    sleep.assert_not_called()


@pytest.mark.parametrize(
    "error",
    [
        pytest.param(SERVER_ERROR, id="api-error"),
        pytest.param(UNKNOWN_ERROR, id="unknown-error-code"),
        pytest.param(CONNECTION_ERROR, id="connection-error"),
    ],
)
def test_retries_errors_that_may_be_temporary(attempt, mocked_api, error):
    _answer_bookings(mocked_api, error, error, BOOKED)

    result, sleep = attempt()

    assert result.status == BookingStatus.BOOKED
    assert result.attempts == 3
    assert sleep.call_args_list == [call(1), call(1)]


def test_fails_after_retry_attempts(attempt, mocked_api):
    _answer_bookings(mocked_api, SERVER_ERROR)

    result, sleep = attempt()

    assert result.status == BookingStatus.FAILED
    assert result.attempts == 3
    assert len(_booking_calls(mocked_api)) == 3
    assert sleep.call_args_list == [call(1), call(1)]
    assert "HTTP 500" in result.error


def test_timed_out_booking_that_went_through_counts_as_already_booked(attempt, mocked_api, pysportbot_caplog):
    # The first request reached the server, but its response did not arrive in time
    _answer_bookings(mocked_api, READ_TIMEOUT, ALREADY_BOOKED)

    result, _ = attempt()

    assert result.status == BookingStatus.ALREADY_BOOKED
    assert result.attempts == 2
    assert "an earlier attempt that failed with a network error probably worked" in pysportbot_caplog.text


def test_polls_until_slot_is_published(attempt, mocked_api, payloads):
    mocked_api.remove(responses.POST, str(Endpoints.SLOTS))
    mocked_api.add(responses.POST, str(Endpoints.SLOTS), json={"data": {"activities_calendar": []}})
    mocked_api.add(responses.POST, str(Endpoints.SLOTS), json=payloads["activities_calendar"])

    result, sleep = attempt()

    assert result.status == BookingStatus.BOOKED
    assert result.attempts == 2
    sleep.assert_called_once_with(0.5)


def test_slot_not_found_after_poll_window(attempt, mocked_api):
    result, _ = attempt(RetryPolicy(poll_interval=0.5, poll_window=1), start=OPEN_SLOT_START.replace(hour=23))

    assert result.status == BookingStatus.NOT_FOUND
    assert result.attempts == 3
    assert result.slot is None
    assert _booking_calls(mocked_api) == []


def test_stops_when_slot_full(attempt, mocked_api, full_slot_refused):
    result, sleep = attempt(start=FULL_SLOT_START)

    assert result.status == BookingStatus.FULL
    assert result.attempts == 1
    # One request, in case one of the places is the user's
    assert len(_booking_calls(mocked_api)) == 1
    sleep.assert_not_called()


def test_full_slot_already_booked_by_user(attempt, mocked_api):
    _answer_bookings(mocked_api, ALREADY_BOOKED)

    result, _ = attempt(start=FULL_SLOT_START)

    assert result.status == BookingStatus.ALREADY_BOOKED
    assert len(_booking_calls(mocked_api)) == 1


def test_full_slot_is_not_polled(attempt, mocked_api):
    # The API's error code for a full slot is unknown, and "not available" would otherwise be polled
    _answer_bookings(mocked_api, UNAVAILABLE)

    result, sleep = attempt(start=FULL_SLOT_START)

    assert result.status == BookingStatus.FULL
    assert result.attempts == 1
    sleep.assert_not_called()


def test_pre_resolved_slot_is_booked_with_one_request(attempt, offline_bot, mocked_api):
    slot = offline_bot.find_slot("Gimnasio", OPEN_SLOT_START)
    n_calls = len(mocked_api.calls)
    _answer_bookings(mocked_api, NOT_BOOKABLE_YET, BOOKED)

    result, _ = attempt(slot=slot)

    assert result.status == BookingStatus.BOOKED
    assert result.slot is slot
    assert _urls(mocked_api, n_calls) == [str(Endpoints.BOOKING)] * 2


def test_dry_run_sends_no_booking(attempt, mocked_api):
    result, _ = attempt(dry_run=True)

    assert result.status == BookingStatus.DRY_RUN
    assert result.ok
    assert _booking_calls(mocked_api) == []


def test_unexpected_error_fails_without_raising(fake_clock, pysportbot_caplog):
    bot = MagicMock()
    bot.find_slot.side_effect = RuntimeError("bug")

    result = attempt_booking(bot, GYM, OPEN_SLOT_START, POLICY, clock=fake_clock.monotonic, sleep=fake_clock.sleep)

    assert result.status == BookingStatus.FAILED
    assert result.error == "bug"
    assert "Traceback" in pysportbot_caplog.text


# wait_until


def test_wait_until_sleeps_in_chunks(frozen_now, fake_clock):
    sleep = MagicMock(side_effect=fake_clock.sleep)

    target = wait_until(fake_clock.start + timedelta(seconds=95), clock=fake_clock.monotonic, sleep=sleep)

    assert sleep.call_args_list == [call(30), call(30), call(30), call(5)]
    assert target == fake_clock.elapsed == 95


def test_wait_until_past_deadline_returns_at_once(frozen_now, fake_clock):
    sleep = MagicMock(side_effect=fake_clock.sleep)

    target = wait_until(fake_clock.start - timedelta(seconds=10), clock=fake_clock.monotonic, sleep=sleep)

    sleep.assert_not_called()
    assert target == -10


# schedule_bookings

# Executes 10 minutes after the fake clock's start on Friday 2029-12-28 07:30, for the fixture's open Gimnasio slot on the following Friday
SCHEDULED_CONFIG = ServiceConfig(
    email="user@example.com",
    password="password",
    centre="test-centre",
    execution=WeeklyTime(FRIDAY, time(7, 40)),
    classes=(GYM,),
)


def _record_request_times(mocked_api, fake_clock, endpoint, body):
    """Answer requests to `endpoint` with `body`, and return the list that collects the fake time of each request."""
    times = []

    def callback(request):
        times.append(fake_clock.elapsed)
        return 200, {}, json.dumps(body)

    mocked_api.remove(responses.POST, str(endpoint))
    mocked_api.add_callback(responses.POST, str(endpoint), callback=callback)
    return times


def test_schedule_bookings_resolves_slot_before_execution(
    offline_bot, mocked_api, frozen_now, mock_time, fake_clock, payloads
):
    n_calls = len(mocked_api.calls)
    slots_times = _record_request_times(mocked_api, fake_clock, Endpoints.SLOTS, payloads["activities_calendar"])
    booking_times = _record_request_times(mocked_api, fake_clock, Endpoints.BOOKING, {"success": True})

    results = schedule_bookings(offline_bot, SCHEDULED_CONFIG, POLICY)

    assert [r.status for r in results] == [BookingStatus.BOOKED]
    # Re-login check and slot lookup 60 s before execution, then only the booking request at execution
    assert _urls(mocked_api, n_calls) == [str(Endpoints.USER), str(Endpoints.SLOTS), str(Endpoints.BOOKING)]
    assert slots_times == [540]
    assert booking_times == [600]


def test_schedule_bookings_looks_up_unpublished_slot_when_booking(
    offline_bot, mocked_api, frozen_now, mock_time, payloads
):
    mocked_api.remove(responses.POST, str(Endpoints.SLOTS))
    mocked_api.add(responses.POST, str(Endpoints.SLOTS), json={"data": {"activities_calendar": []}})
    mocked_api.add(responses.POST, str(Endpoints.SLOTS), json=payloads["activities_calendar"])
    n_calls = len(mocked_api.calls)

    results = schedule_bookings(offline_bot, SCHEDULED_CONFIG, POLICY)

    assert [r.status for r in results] == [BookingStatus.BOOKED]
    assert _urls(mocked_api, n_calls) == [
        str(Endpoints.USER),
        str(Endpoints.SLOTS),
        str(Endpoints.SLOTS),
        str(Endpoints.BOOKING),
    ]


def test_schedule_bookings_waits_booking_delay(offline_bot, mocked_api, frozen_now, mock_time, fake_clock):
    booking_times = _record_request_times(mocked_api, fake_clock, Endpoints.BOOKING, {"success": True})

    schedule_bookings(offline_bot, SCHEDULED_CONFIG, POLICY, booking_delay=1.5)

    assert booking_times == [601.5]
    assert mock_time.sleep.call_args_list[-1] == call(1.5)


def test_schedule_bookings_continues_when_relogin_fails(frozen_now, mock_time, pysportbot_caplog):
    bot = MagicMock()
    bot.ensure_logged_in.side_effect = Exception("Network error")

    results = schedule_bookings(bot, SCHEDULED_CONFIG, POLICY)

    assert "Re-authentication failed before booking execution with Network error." in pysportbot_caplog.text
    assert bot.ensure_logged_in.call_count == POLICY.retry_attempts
    bot.book_slot.assert_called_once_with(bot.find_slot.return_value)
    assert [r.status for r in results] == [BookingStatus.BOOKED]


def test_schedule_bookings_retries_failed_relogin(frozen_now, mock_time):
    bot = MagicMock()
    bot.ensure_logged_in.side_effect = [Exception("Network error"), None]

    schedule_bookings(bot, SCHEDULED_CONFIG, POLICY)

    assert bot.ensure_logged_in.call_count == 2
    # The retry delay at 540 s, then the remaining 59 s until execution in chunks
    assert mock_time.sleep.call_args_list[-3:] == [call(1), call(30), call(29)]


def test_schedule_bookings_stops_relogin_retries_at_booking_time(frozen_now, mock_time, fake_clock):
    bot = MagicMock()
    bot.ensure_logged_in.side_effect = Exception("Network error")
    booking_times = []
    bot.book_slot.side_effect = lambda slot: booking_times.append(fake_clock.elapsed)

    schedule_bookings(bot, SCHEDULED_CONFIG, RetryPolicy(retry_attempts=5, retry_delay=50))

    # Attempts at 540 and 590 s: another one at 640 s would be after the booking time
    assert bot.ensure_logged_in.call_count == 2
    assert booking_times == [600]


def test_slow_lookup_does_not_delay_other_classes(frozen_now, mock_time):
    slow, fast = ClassSpec("Slow", FRIDAY, time(9, 0)), ClassSpec("Fast", FRIDAY, time(12, 0))
    config = ServiceConfig(
        email="user@example.com",
        password="password",
        centre="test-centre",
        execution=WeeklyTime(FRIDAY, time(7, 40)),
        classes=(slow, fast),
    )
    fast_booked = threading.Event()
    events = []

    def find_slot(activity, start):
        if activity == "Slow":
            # Blocks until the other class is booked; a lookup that delays all bookings would time out here
            events.append(("slow lookup done", fast_booked.wait(timeout=5)))
        return activity

    def book_slot(slot):
        events.append((f"{slot} booked", True))
        if slot == "Fast":
            fast_booked.set()
        return slot

    bot = MagicMock(**{"find_slot.side_effect": find_slot, "book_slot.side_effect": book_slot})

    results = schedule_bookings(bot, config, POLICY, max_threads=2)

    assert events == [("Fast booked", True), ("slow lookup done", True), ("Slow booked", True)]
    assert [r.status for r in results] == [BookingStatus.BOOKED, BookingStatus.BOOKED]


def test_booking_delay_does_not_shorten_poll_window(offline_bot, mocked_api, frozen_now, mock_time, fake_clock):
    booking_times = _record_request_times(mocked_api, fake_clock, Endpoints.BOOKING, {"success": False, "error": 28})

    results = schedule_bookings(
        offline_bot, SCHEDULED_CONFIG, RetryPolicy(poll_interval=10, poll_window=60), booking_delay=90
    )

    # Booking starts at 600 + 90 s and polls for the full window, although the delay is longer than the window
    assert booking_times == [690, 700, 710, 720, 730, 740, 750]
    assert results[0].status == BookingStatus.FAILED


def test_max_threads_does_not_delay_lookups(frozen_now, mock_time):
    classes = tuple(ClassSpec(name, FRIDAY, time(9 + i, 0)) for i, name in enumerate(("A", "B", "C")))
    config = ServiceConfig(
        email="user@example.com",
        password="password",
        centre="test-centre",
        execution=WeeklyTime(FRIDAY, time(7, 40)),
        classes=classes,
    )
    looked_up = []
    all_looked_up = threading.Event()
    waited = []

    def find_slot(activity, start):
        looked_up.append(activity)
        if len(looked_up) == len(classes):
            all_looked_up.set()
        return activity

    def book_slot(slot):
        # With a single booking thread, B and C would only be looked up after A is booked
        waited.append(all_looked_up.wait(timeout=5))
        return slot

    bot = MagicMock(**{"find_slot.side_effect": find_slot, "book_slot.side_effect": book_slot})

    results = schedule_bookings(bot, config, POLICY, max_threads=1)

    assert waited == [True, True, True]
    assert [r.status for r in results] == [BookingStatus.BOOKED] * 3


def test_class_queued_behind_max_threads_gets_full_poll_window(frozen_now, mock_time, fake_clock):
    first, second = ClassSpec("First", FRIDAY, time(9, 0)), ClassSpec("Second", FRIDAY, time(12, 0))
    config = ServiceConfig(
        email="user@example.com",
        password="password",
        centre="test-centre",
        execution=WeeklyTime(FRIDAY, time(7, 40)),
        classes=(first, second),
    )
    second_attempts = []

    def book_slot(slot):
        if slot == "Second":
            second_attempts.append(fake_clock.elapsed)
            if len(second_attempts) > 1:
                return slot
        raise SlotNotBookableYetError(slot, 28)

    bot = MagicMock(**{"find_slot.side_effect": lambda activity, start: activity, "book_slot.side_effect": book_slot})

    results = schedule_bookings(bot, config, RetryPolicy(poll_interval=10, poll_window=30), max_threads=1)

    # The first class polls from 600 to 630 s; the second only starts then, and still polls
    assert [r.status for r in results] == [BookingStatus.FAILED, BookingStatus.BOOKED]
    assert second_attempts == [630, 640]


def test_dry_run_uses_slot_found_ahead_of_time(offline_bot, mocked_api, frozen_now, mock_time):
    n_calls = len(mocked_api.calls)

    results = schedule_bookings(offline_bot, SCHEDULED_CONFIG, POLICY, dry_run=True)

    assert [r.status for r in results] == [BookingStatus.DRY_RUN]
    assert results[0].slot is not None and results[0].slot.id == 5004
    # Only the re-login check and the lookup ahead of time
    assert _urls(mocked_api, n_calls) == [str(Endpoints.USER), str(Endpoints.SLOTS)]


def test_dry_run_of_cancelled_slot_fails(attempt, mocked_api, payloads):
    calendar = payloads["activities_calendar"]
    next(e for e in calendar["data"]["activities_calendar"] if e["id_activity_calendar"] == 5004)["cancelled"] = 1
    mocked_api.replace(responses.POST, str(Endpoints.SLOTS), json=calendar)

    result, sleep = attempt(dry_run=True)

    assert result.status == BookingStatus.FAILED
    assert not result.ok
    assert result.error == "Slot 5004 is cancelled, so booking it would fail."
    sleep.assert_not_called()


def test_schedule_bookings_now_books_at_once(frozen_now, mock_time):
    bot = MagicMock()
    config = ServiceConfig(
        email="user@example.com", password="password", centre="test-centre", execution=None, classes=(GYM,)
    )

    schedule_bookings(bot, config, POLICY)

    # Logged in just now, so no re-login and no lookup ahead of time
    bot.ensure_logged_in.assert_not_called()
    bot.find_slot.assert_called_once_with(activity="Gimnasio", start=OPEN_SLOT_START)
    bot.book_slot.assert_called_once_with(bot.find_slot.return_value)
    mock_time.sleep.assert_not_called()


def test_schedule_bookings_returns_results_in_config_order(
    offline_bot, mocked_api, frozen_now, mock_time, full_slot_refused
):
    config = ServiceConfig(
        email="user@example.com",
        password="password",
        centre="test-centre",
        execution=None,
        classes=(ClassSpec("Gimnasio", FRIDAY, time(10, 0)), GYM),
    )

    results = schedule_bookings(offline_bot, config, POLICY, max_threads=2)

    assert [(r.start, r.status) for r in results] == [
        (FULL_SLOT_START, BookingStatus.FULL),
        (OPEN_SLOT_START, BookingStatus.BOOKED),
    ]


def test_log_summary(pysportbot_caplog):
    log_summary(
        [
            BookingResult(GYM, OPEN_SLOT_START, BookingStatus.BOOKED, attempts=4),
            BookingResult(
                ClassSpec("Yoga", FRIDAY, time(18, 0, 30)),
                datetime(2030, 1, 4, 18, 0, 30, tzinfo=MADRID),
                BookingStatus.ALREADY_BOOKED,
                attempts=1,
            ),
        ]
    )

    assert pysportbot_caplog.messages[-3:] == [
        "ACTIVITY  DAY                TIME      STATUS          ATTEMPTS",
        "Gimnasio  Friday 2030-01-04  12:00     booked          4",
        "Yoga      Friday 2030-01-04  18:00:30  already booked  1",
    ]
