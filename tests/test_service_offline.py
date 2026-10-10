from dataclasses import replace
from datetime import datetime, time, timedelta
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest

from pysportbot.endpoints import Endpoints
from pysportbot.service.booking import schedule_bookings
from pysportbot.service.config import ClassSpec, ServiceConfig, WeeklyTime, load_config
from pysportbot.service.results import BookingStatus
from pysportbot.service.retry import RetryPolicy
from pysportbot.service.scheduling import next_execution
from pysportbot.service.service import run_service

MADRID = ZoneInfo("Europe/Madrid")
FRIDAY, SUNDAY = 4, 6

VALID_CONFIG = ServiceConfig(
    email="user@example.com",
    password="password",
    centre="test-centre",
    execution=WeeklyTime(FRIDAY, time(7, 30)),
    classes=(ClassSpec("Gimnasio", FRIDAY, time(12, 0)),),
)


def _booking_calls(mocked_api):
    return [c for c in mocked_api.calls if c.request.url == str(Endpoints.BOOKING)]


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"retry_attempts": 0}, id="retry_attempts=0"),
        pytest.param({"retry_delay": -1}, id="retry_delay<0"),
        pytest.param({"booking_delay": -1}, id="booking_delay<0"),
        pytest.param({"poll_interval": 0}, id="poll_interval=0"),
        pytest.param({"poll_window": -1}, id="poll_window<0"),
    ],
)
def test_run_service_rejects_invalid_arguments(mocked_api, overrides):
    kwargs = {"booking_delay": 0, "retry_attempts": 1, "retry_delay": 0, **overrides}
    config = replace(VALID_CONFIG, execution=None)

    with pytest.raises(ValueError, match=next(iter(overrides))):
        run_service(config, **kwargs)

    assert len(mocked_api.calls) == 0


@pytest.mark.parametrize(
    ("now", "expected", "utc_offset"),
    [
        # Clocks go forward on Sunday 2026-03-29 at 02:00: CET (+01:00) -> CEST (+02:00)
        pytest.param(
            datetime(2026, 3, 27, 12, 0), datetime(2026, 3, 29, 7, 30), timedelta(hours=2), id="spring-forward"
        ),
        # Clocks go back on Sunday 2026-10-25 at 03:00: CEST (+02:00) -> CET (+01:00)
        pytest.param(datetime(2026, 10, 23, 12, 0), datetime(2026, 10, 25, 7, 30), timedelta(hours=1), id="fall-back"),
    ],
)
def test_next_execution_across_dst_change(now, expected, utc_offset):
    result = next_execution(WeeklyTime(SUNDAY, time(7, 30)), now.replace(tzinfo=MADRID))

    assert result.replace(tzinfo=None) == expected
    assert result.utcoffset() == utc_offset
    assert result == (expected - utc_offset).replace(tzinfo=ZoneInfo("UTC"))


UTC = ZoneInfo("UTC")


@pytest.mark.parametrize(
    ("now_utc", "expected_utc"),
    [
        # Clocks go back on Sunday 2026-10-25 at 03:00 CEST, so 02:00-03:00 happens twice: 00:00-01:00 and 01:00-02:00 UTC
        pytest.param(datetime(2026, 10, 25, 0, 15), datetime(2026, 10, 25, 0, 30), id="first-pass-before"),
        pytest.param(datetime(2026, 10, 25, 0, 45), datetime(2026, 10, 25, 1, 30), id="first-pass-after"),
        pytest.param(datetime(2026, 10, 25, 1, 15), datetime(2026, 10, 25, 1, 30), id="second-pass-before"),
        pytest.param(datetime(2026, 10, 25, 1, 45), datetime(2026, 11, 1, 1, 30), id="second-pass-after"),
        # Clocks go forward on Sunday 2026-03-29 at 02:00 CET, so 02:30 does not exist and runs at 03:30 CEST
        pytest.param(datetime(2026, 3, 29, 0, 45), datetime(2026, 3, 29, 1, 30), id="nonexistent-time"),
    ],
)
def test_next_execution_at_ambiguous_dst_time_is_ahead(now_utc, expected_utc):
    now = now_utc.replace(tzinfo=UTC).astimezone(MADRID)

    result = next_execution(WeeklyTime(SUNDAY, time(2, 30)), now)

    # Aware datetimes in a repeated or skipped hour never equal those in another zone (PEP 495), so compare instants
    assert result.timestamp() == expected_utc.replace(tzinfo=UTC).timestamp()
    assert result.timestamp() > now.timestamp()


@pytest.mark.parametrize(
    ("now", "hours_until_execution"),
    [
        # Saturday 07:30 -> Sunday 07:30 is 23 real hours when clocks go forward, and 25 when they go back
        pytest.param(datetime(2026, 3, 28, 7, 30), 23, id="spring-forward"),
        pytest.param(datetime(2026, 10, 24, 7, 30), 25, id="fall-back"),
    ],
)
def test_schedule_bookings_waits_real_time_across_dst_change(
    frozen_now, mock_time, fake_clock, now, hours_until_execution
):
    fake_clock.start = now.replace(tzinfo=MADRID)
    seconds_until_execution = hours_until_execution * 3600
    config = replace(VALID_CONFIG, execution=WeeklyTime(SUNDAY, time(7, 30)))
    bot = MagicMock()
    relogin_times = []
    bot.ensure_logged_in.side_effect = lambda: relogin_times.append(fake_clock.elapsed)

    schedule_bookings(bot, config, RetryPolicy())

    # Re-authenticate 60 s before execution, and book at execution
    assert relogin_times == [seconds_until_execution - 60]
    assert fake_clock.elapsed == seconds_until_execution
    bot.book_slot.assert_called_once()


def test_run_service_books_now_with_env_credentials(mocked_api, mock_time, frozen_now, config_path, credentials_env):
    config = load_config(config_path, env=credentials_env)

    results = run_service(config, booking_delay=0, retry_attempts=1, retry_delay=0)

    assert [r.status for r in results] == [BookingStatus.BOOKED]
    assert len(_booking_calls(mocked_api)) == 1
    mock_time.sleep.assert_not_called()
