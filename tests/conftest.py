import os

import pytest

from pysportbot import SportBot


@pytest.fixture(scope="module")
def bot():
    """Fixture to create a SportBot instance and log in."""
    # Get credentials from environment
    email = os.getenv("SPORTBOT_EMAIL")
    password = os.getenv("SPORTBOT_PASSWORD")

    # Check credentials have been retrieved successfully
    assert email is not None, "SPORTBOT_EMAIL is not set in the environment."
    assert password is not None, "SPORTBOT_PASSWORD is not set in the environment."

    # Create a new SportBot instance with DEBUG logging
    bot = SportBot(log_level="DEBUG")

    # Log in to user account
    bot.login(email, password)

    return bot
