import os

import pytest

from pysportbot import SportBot


@pytest.fixture(scope="module")
def bot():
    """Fixture to create a SportBot instance and log in."""
    # Get credentials from environment
    email = os.getenv("SPORTBOT_EMAIL")
    password = os.getenv("SPORTBOT_PASSWORD")
    centre = os.getenv("SPORTBOT_CENTRE")

    # Check credentials have been retrieved successfully
    assert email is not None, "SPORTBOT_EMAIL is not set in the environment."
    assert password is not None, "SPORTBOT_PASSWORD is not set in the environment."
    assert centre is not None, "SPORTBOT_CENTRE is not set in the environment."

    # Create a new SportBot instance with DEBUG logging
    bot = SportBot(log_level="DEBUG", print_centres=False, time_zone="Europe/Madrid")

    # Log in to user account
    bot.login(email, password, centre)

    return bot
