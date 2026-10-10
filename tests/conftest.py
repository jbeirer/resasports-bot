import json
import logging
import threading
from datetime import datetime, tzinfo
from pathlib import Path
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
import responses

from pysportbot import SportBot
from pysportbot.endpoints import Endpoints

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# Default happy-path response for every endpoint the library calls
DEFAULT_RESPONSES = [
    (responses.POST, Endpoints.CENTRE, "centres.json"),
    (responses.POST, Endpoints.USER_LOGIN, "user_login.json"),
    (responses.GET, Endpoints.SPORT_USER_TOKEN, "sport_user_token.json"),
    (responses.POST, Endpoints.USER, "user.json"),
    (responses.POST, Endpoints.SLOTS, "activities_calendar.json"),
]


# A Friday one week before the fixture's slots on Friday 2030-01-04
FROZEN_NOW = datetime(2029, 12, 28, 7, 30, tzinfo=ZoneInfo("Europe/Madrid"))
CREDENTIALS_ENV = {
    "SPORTBOT_EMAIL": "user@example.com",
    "SPORTBOT_PASSWORD": "password",
    "SPORTBOT_CENTRE": "test-centre",
}
# Books the fixture's open Gimnasio slot on Friday 2030-01-04 when run at FROZEN_NOW
CONFIG_WITHOUT_CREDENTIALS = {
    "booking_execution": "now",
    "classes": [{"activity": "Gimnasio", "class_day": "Friday", "class_time": "12:00"}],
}


def load_fixture(name: str) -> dict:
    """Load a JSON payload from tests/fixtures/."""
    return json.loads((FIXTURES_DIR / name).read_text())


@pytest.fixture
def payloads() -> dict[str, dict]:
    """Fresh copies of all fixture payloads, keyed by file stem (e.g. payloads["user_login"])."""
    return {path.stem: load_fixture(path.name) for path in FIXTURES_DIR.glob("*.json")}


@pytest.fixture
def pysportbot_caplog(caplog, monkeypatch):
    """
    `caplog` that also captures pysportbot's own logs.

    `caplog` listens on the root logger, but `configure_logging()` (called by `SportBot()`) stops the "pysportbot"
    logger from propagating there. Setting `propagate = True` up front would be undone by the next `SportBot()`, so
    attach caplog's handler to the "pysportbot" logger directly, with propagation off so records are captured once.
    """
    logger = logging.getLogger("pysportbot")
    monkeypatch.setattr(logger, "propagate", False)
    logger.addHandler(caplog.handler)
    yield caplog
    logger.removeHandler(caplog.handler)


@pytest.fixture
def mocked_api():
    """
    Intercept all HTTP traffic with default happy-path responses registered.

    Unregistered requests raise ConnectionError. Override a response with
    `mocked_api.replace(...)` or `mocked_api.upsert(...)`.
    """
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        for method, url, fixture in DEFAULT_RESPONSES:
            rsps.add(method, str(url), json=load_fixture(fixture))
        rsps.add(responses.POST, str(Endpoints.BOOKING), json={"success": True})
        rsps.add(responses.POST, str(Endpoints.CANCELLATION), json={"success": True})
        yield rsps


@pytest.fixture
def centre_slug() -> str:
    return load_fixture("centres.json")["applications"][0]["slug"]


@pytest.fixture
def offline_bot(mocked_api, centre_slug) -> SportBot:
    """A SportBot logged in against the mocked API."""
    bot = SportBot(log_level="DEBUG")
    bot.login("user@example.com", "password", centre_slug)
    return bot


class FakeClock:
    """
    A clock that only moves when `sleep()` is called, so waiting takes no real time.

    `monotonic()` starts at 0 and `now()` at `start`, and both move together.
    """

    def __init__(self, start: datetime = FROZEN_NOW) -> None:
        self.start = start
        self.elapsed = 0.0
        self._lock = threading.Lock()

    def monotonic(self) -> float:
        return self.elapsed

    def sleep(self, seconds: float) -> None:
        assert seconds >= 0
        with self._lock:
            self.elapsed += seconds

    def now(self, tz: tzinfo | None = None) -> datetime:
        return datetime.fromtimestamp(self.start.timestamp() + self.elapsed, tz or self.start.tzinfo)


@pytest.fixture
def fake_clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def frozen_now(fake_clock):
    """Start the service's wall clock at FROZEN_NOW. It only moves with the sleeps of `mock_time`."""
    with (
        patch("pysportbot.service.booking.datetime", wraps=datetime) as booking_datetime,
        patch("pysportbot.service.scheduling.datetime", wraps=datetime) as scheduling_datetime,
    ):
        booking_datetime.now.side_effect = fake_clock.now
        scheduling_datetime.now.side_effect = fake_clock.now
        yield


@pytest.fixture
def mock_time(fake_clock):
    """Replace the service's `time` module with `fake_clock`, recording the calls, so sleeps take no real time."""
    with patch("pysportbot.service.booking.time", MagicMock(wraps=fake_clock)) as mock:
        yield mock


@pytest.fixture
def config_path(tmp_path):
    """A service config file without credentials."""
    path = tmp_path / "config.json"
    path.write_text(json.dumps(CONFIG_WITHOUT_CREDENTIALS))
    return path


@pytest.fixture
def credentials_env(monkeypatch) -> dict[str, str]:
    """Set the SPORTBOT_* credential env vars to the test account."""
    for name, value in CREDENTIALS_ENV.items():
        monkeypatch.setenv(name, value)
    return CREDENTIALS_ENV
