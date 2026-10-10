import os
from pathlib import Path

import pytest

from pysportbot import SportBot

LIVE_DIR = Path(__file__).parent


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(items):
    """Mark every test under tests/live/ as live, before `-m` deselection runs."""
    for item in items:
        if LIVE_DIR in item.path.parents:
            item.add_marker(pytest.mark.live)


@pytest.fixture(scope="session", autouse=True)
def live_credentials():
    """Skip every live test (not only those using `bot`) when credentials are missing."""
    email = os.getenv("SPORTBOT_EMAIL")
    password = os.getenv("SPORTBOT_PASSWORD")
    centre = os.getenv("SPORTBOT_CENTRE")

    if not (email and password and centre):
        pytest.skip("SPORTBOT_EMAIL, SPORTBOT_PASSWORD and SPORTBOT_CENTRE must be set to run live tests.")

    return email, password, centre


@pytest.fixture(scope="module")
def bot(live_credentials):
    """Fixture to create a SportBot instance and log in against the real API."""
    email, password, centre = live_credentials

    # Create a new SportBot instance with DEBUG logging
    bot = SportBot(log_level="DEBUG", time_zone="Europe/Madrid")

    # Log in to user account
    bot.login(email, password, centre)

    return bot
