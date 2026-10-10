import json
import logging
from pathlib import Path

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
