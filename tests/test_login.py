import os

from pysportbot import SportBot


def test_login():
    """
    Test the login functionality of the SportBot.
    """
    # Retrieve credentials from environment variables
    email = os.getenv("SPORTBOT_EMAIL")
    password = os.getenv("SPORTBOT_PASSWORD")

    assert email is not None, "SPORTBOT_EMAIL is not set in the environment."
    assert password is not None, "SPORTBOT_PASSWORD is not set in the environment."

    # Create bot instance
    bot = SportBot()

    # Attempt login
    bot.login(email, password)

    assert bot.is_logged_in() == True, "Login failed."
