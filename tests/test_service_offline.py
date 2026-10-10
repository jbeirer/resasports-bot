from datetime import datetime
from unittest.mock import patch

import pytest
import pytz
import requests
import responses

from pysportbot.endpoints import Endpoints
from pysportbot.exceptions import ConfigError
from pysportbot.service.booking import attempt_booking
from pysportbot.service.config_validator import validate_config
from pysportbot.service.service import run_service

# A Friday one week before the fixture's slots on Friday 2030-01-04
FROZEN_NOW = pytz.timezone("Europe/Madrid").localize(datetime(2029, 12, 28, 7, 30))
OPEN_SLOT_TIME = "12:00:00"  # Gimnasio, places left
FULL_SLOT_TIME = "10:00:00"  # Gimnasio, n_inscribed == n_capacity

VALID_CONFIG = {
    "email": "user@example.com",
    "password": "password",
    "centre": "test-centre",
    "booking_execution": "Friday 07:30:00",
    "classes": [{"activity": "Gimnasio", "class_day": "Friday", "class_time": OPEN_SLOT_TIME}],
}


def _booking_calls(mocked_api):
    return [c for c in mocked_api.calls if c.request.url == str(Endpoints.BOOKING)]


@pytest.fixture
def frozen_class_day():
    """Make `calculate_class_day("Friday")` resolve to 2030-01-04."""
    with patch("pysportbot.service.scheduling.datetime", wraps=datetime) as mock_datetime:
        mock_datetime.now.return_value = FROZEN_NOW
        yield


@pytest.fixture
def mock_time():
    with patch("pysportbot.service.booking.time") as mock:
        yield mock


def _attempt(bot, retry_attempts=3, retry_delay=1):
    attempt_booking(
        bot,
        activity="Gimnasio",
        class_day="Friday",
        class_time=OPEN_SLOT_TIME,
        retry_attempts=retry_attempts,
        retry_delay=retry_delay,
    )


@pytest.mark.parametrize("error_code", [6, 28])
def test_attempt_booking_retries_until_success(offline_bot, mocked_api, frozen_class_day, mock_time, error_code):
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
def test_attempt_booking_retries_after_network_error(offline_bot, mocked_api, frozen_class_day, mock_time, error):
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
def test_attempt_booking_retries_after_other_error(
    offline_bot, mocked_api, frozen_class_day, mock_time, response_kwargs
):
    mocked_api.replace(responses.POST, str(Endpoints.BOOKING), **response_kwargs)
    mocked_api.add(responses.POST, str(Endpoints.BOOKING), json={"success": True})

    _attempt(offline_bot)

    assert len(_booking_calls(mocked_api)) == 2
    mock_time.sleep.assert_called_once_with(1)


def test_attempt_booking_retries_when_slot_not_found(offline_bot, mocked_api, frozen_class_day, mock_time):
    attempt_booking(offline_bot, activity="Gimnasio", class_day="Friday", class_time="23:00:00", retry_attempts=3)

    assert _booking_calls(mocked_api) == []
    assert mock_time.sleep.call_count == 2


def test_attempt_booking_stops_when_already_booked(offline_bot, mocked_api, frozen_class_day, mock_time):
    mocked_api.replace(responses.POST, str(Endpoints.BOOKING), json={"success": False, "error": 5})

    _attempt(offline_bot)

    assert len(_booking_calls(mocked_api)) == 1
    mock_time.sleep.assert_not_called()


def test_attempt_booking_stops_when_slot_full(offline_bot, mocked_api, frozen_class_day, mock_time):
    attempt_booking(offline_bot, activity="Gimnasio", class_day="Friday", class_time=FULL_SLOT_TIME, retry_attempts=3)

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
    config = {**VALID_CONFIG, "booking_execution": "now"}

    with pytest.raises(ValueError, match=next(iter(overrides))):
        run_service(config, **kwargs)

    assert len(mocked_api.calls) == 0


def test_validate_config_accepts_valid_config():
    validate_config(VALID_CONFIG)


def test_validate_config_normalizes_day_names():
    config = {
        **VALID_CONFIG,
        "booking_execution": "FRIDAY 07:30:00",
        "classes": [{"activity": "Gimnasio", "class_day": " monday ", "class_time": OPEN_SLOT_TIME}],
    }

    validate_config(config)


@pytest.mark.parametrize("day", ["Funday", "Mon", "Lunes"])
def test_validate_config_rejects_invalid_execution_day(day):
    config = {**VALID_CONFIG, "booking_execution": f"{day} 07:30:00"}

    with pytest.raises(ConfigError, match=f"Invalid day '{day}'"):
        validate_config(config)


@pytest.mark.parametrize("day", ["Funday", "Mon", "", 1])
def test_validate_config_rejects_invalid_class_day(day):
    config = {**VALID_CONFIG, "classes": [{**VALID_CONFIG["classes"][0], "class_day": day}]}

    with pytest.raises(ConfigError, match=f"Invalid day '{day}'"):
        validate_config(config)


@pytest.mark.parametrize("class_time", ["18:00", "25:00:00", "6pm", "", 1800])
def test_validate_config_rejects_invalid_class_time(class_time):
    config = {**VALID_CONFIG, "classes": [{**VALID_CONFIG["classes"][0], "class_time": class_time}]}

    with pytest.raises(ConfigError, match=f"Invalid class_time '{class_time}'"):
        validate_config(config)
