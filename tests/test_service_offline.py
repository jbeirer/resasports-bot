import json
import sys
from dataclasses import replace
from datetime import datetime, time, timedelta
from unittest.mock import MagicMock, call, patch
from zoneinfo import ZoneInfo

import pytest
import requests
import responses

from pysportbot.endpoints import Endpoints
from pysportbot.service.__main__ import main
from pysportbot.service.booking import attempt_booking, schedule_bookings
from pysportbot.service.config import ClassSpec, ServiceConfig, WeeklyTime, load_config
from pysportbot.service.scheduling import next_execution
from pysportbot.service.service import run_service

MADRID = ZoneInfo("Europe/Madrid")
FRIDAY, SUNDAY = 4, 6
# The fixture's Gimnasio slots on Friday 2030-01-04
OPEN_SLOT_START = datetime(2030, 1, 4, 12, 0, tzinfo=MADRID)  # places left
FULL_SLOT_START = datetime(2030, 1, 4, 10, 0, tzinfo=MADRID)  # n_inscribed == n_capacity

VALID_CONFIG = ServiceConfig(
    email="user@example.com",
    password="password",
    centre="test-centre",
    execution=WeeklyTime(FRIDAY, time(7, 30)),
    classes=(ClassSpec("Gimnasio", FRIDAY, time(12, 0)),),
)
CREDENTIALS_ENV = {
    "SPORTBOT_EMAIL": "user@example.com",
    "SPORTBOT_PASSWORD": "password",
    "SPORTBOT_CENTRE": "test-centre",
}
# A Friday one week before the fixture's slots on Friday 2030-01-04
FROZEN_NOW = datetime(2029, 12, 28, 7, 30, tzinfo=MADRID)
CONFIG_WITHOUT_CREDENTIALS = {
    "booking_execution": "now",
    "classes": [{"activity": "Gimnasio", "class_day": "Friday", "class_time": "12:00"}],
}


def _booking_calls(mocked_api):
    return [c for c in mocked_api.calls if c.request.url == str(Endpoints.BOOKING)]


@pytest.fixture
def frozen_now():
    with patch("pysportbot.service.booking.datetime", wraps=datetime) as mock_datetime:
        mock_datetime.now.return_value = FROZEN_NOW
        yield


@pytest.fixture
def config_path(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps(CONFIG_WITHOUT_CREDENTIALS))
    return path


@pytest.fixture
def mock_time():
    with patch("pysportbot.service.booking.time") as mock:
        yield mock


def _attempt(bot, retry_attempts=3, retry_delay=1):
    attempt_booking(
        bot,
        activity="Gimnasio",
        start=OPEN_SLOT_START,
        retry_attempts=retry_attempts,
        retry_delay=retry_delay,
    )


@pytest.mark.parametrize("error_code", [6, 28])
def test_attempt_booking_retries_until_success(offline_bot, mocked_api, mock_time, error_code):
    mocked_api.replace(responses.POST, str(Endpoints.BOOKING), json={"success": False, "error": error_code})
    mocked_api.add(responses.POST, str(Endpoints.BOOKING), json={"success": True})

    _attempt(offline_bot)

    assert len(_booking_calls(mocked_api)) == 2
    mock_time.sleep.assert_called_once_with(1)


@pytest.mark.parametrize(
    "error",
    [
        pytest.param(requests.exceptions.ReadTimeout("Read timed out."), id="read-timeout"),
        pytest.param(requests.exceptions.ConnectionError("Connection reset."), id="connection-error"),
    ],
)
def test_attempt_booking_retries_after_network_error(offline_bot, mocked_api, mock_time, error):
    mocked_api.replace(responses.POST, str(Endpoints.BOOKING), body=error)
    mocked_api.add(responses.POST, str(Endpoints.BOOKING), json={"success": True})

    _attempt(offline_bot)

    assert len(_booking_calls(mocked_api)) == 2
    mock_time.sleep.assert_called_once_with(1)


@pytest.mark.parametrize(
    "response_kwargs",
    [
        pytest.param({"json": {"success": False, "error": 99}}, id="unknown-error-code"),
        pytest.param({"status": 500}, id="api-error"),
    ],
)
def test_attempt_booking_retries_after_other_error(offline_bot, mocked_api, mock_time, response_kwargs):
    mocked_api.replace(responses.POST, str(Endpoints.BOOKING), **response_kwargs)
    mocked_api.add(responses.POST, str(Endpoints.BOOKING), json={"success": True})

    _attempt(offline_bot)

    assert len(_booking_calls(mocked_api)) == 2
    mock_time.sleep.assert_called_once_with(1)


def test_attempt_booking_retries_when_slot_not_found(offline_bot, mocked_api, mock_time):
    attempt_booking(offline_bot, activity="Gimnasio", start=OPEN_SLOT_START.replace(hour=23), retry_attempts=3)

    assert _booking_calls(mocked_api) == []
    assert mock_time.sleep.call_count == 2


def test_attempt_booking_retries_when_calendar_empty(offline_bot, mocked_api, mock_time):
    mocked_api.replace(responses.POST, str(Endpoints.SLOTS), json={"data": {"activities_calendar": []}})

    _attempt(offline_bot)

    assert _booking_calls(mocked_api) == []
    assert mock_time.sleep.call_count == 2


def test_attempt_booking_stops_when_already_booked(offline_bot, mocked_api, mock_time):
    mocked_api.replace(responses.POST, str(Endpoints.BOOKING), json={"success": False, "error": 5})

    _attempt(offline_bot)

    assert len(_booking_calls(mocked_api)) == 1
    mock_time.sleep.assert_not_called()


def test_attempt_booking_stops_when_slot_full(offline_bot, mocked_api, mock_time):
    attempt_booking(offline_bot, activity="Gimnasio", start=FULL_SLOT_START, retry_attempts=3)

    assert _booking_calls(mocked_api) == []
    mock_time.sleep.assert_not_called()


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"retry_attempts": 0}, id="retry_attempts=0"),
        pytest.param({"retry_delay": -1}, id="retry_delay<0"),
        pytest.param({"booking_delay": -1}, id="booking_delay<0"),
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


@pytest.mark.parametrize(
    ("now", "hours_until_execution"),
    [
        # Saturday 07:30 -> Sunday 07:30 is 23 real hours when clocks go forward, and 25 when they go back
        pytest.param(datetime(2026, 3, 28, 7, 30), 23, id="spring-forward"),
        pytest.param(datetime(2026, 10, 24, 7, 30), 25, id="fall-back"),
    ],
)
def test_schedule_bookings_waits_real_time_across_dst_change(mock_time, now, hours_until_execution):
    start = now.replace(tzinfo=MADRID)
    seconds_until_execution = hours_until_execution * 3600
    # The clock when the service wakes up to re-authenticate, 60 s before execution
    reauth_now = datetime.fromtimestamp(start.timestamp() + seconds_until_execution - 60, MADRID)
    config = replace(VALID_CONFIG, execution=WeeklyTime(SUNDAY, time(7, 30)))

    with (
        patch("pysportbot.service.booking.datetime", wraps=datetime) as booking_datetime,
        patch("pysportbot.service.booking.attempt_booking"),
    ):
        booking_datetime.now.side_effect = [start, reauth_now]
        schedule_bookings(MagicMock(), config, 0, 1, 0, "Europe/Madrid", 1)

    assert mock_time.sleep.call_args_list == [call(seconds_until_execution - 60), call(60)]


def test_run_service_books_now_with_env_credentials(mocked_api, mock_time, frozen_now, config_path):
    config = load_config(config_path, env=CREDENTIALS_ENV)

    run_service(config, booking_delay=0, retry_attempts=1, retry_delay=0)

    assert len(_booking_calls(mocked_api)) == 1
    mock_time.sleep.assert_not_called()


def test_cli_books_now_with_env_credentials(mocked_api, mock_time, frozen_now, config_path, monkeypatch):
    for name, value in CREDENTIALS_ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(sys, "argv", ["pysportbot.service", "--config", str(config_path), "--max-threads", "-1"])

    main()

    assert len(_booking_calls(mocked_api)) == 1


def test_cli_reports_config_error_without_traceback(mocked_api, tmp_path, monkeypatch, capsys):
    for name in CREDENTIALS_ENV:
        monkeypatch.delenv(name, raising=False)
    path = tmp_path / "config.json"
    path.write_text(json.dumps({**CONFIG_WITHOUT_CREDENTIALS, "center": "test-centre"}))
    monkeypatch.setattr(sys, "argv", ["pysportbot.service", "--config", str(path)])

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 2
    err = capsys.readouterr().err
    assert "unknown key 'center', did you mean 'centre'?" in err
    assert "SPORTBOT_EMAIL" in err
    assert "Traceback" not in err
    assert len(mocked_api.calls) == 0


@pytest.mark.parametrize("value", ["0", "-2", "two"])
def test_cli_rejects_invalid_max_threads(value, config_path, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["pysportbot.service", "--config", str(config_path), "--max-threads", value])

    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 2
    assert "--max-threads" in capsys.readouterr().err
