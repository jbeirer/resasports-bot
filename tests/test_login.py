# test_login.py


import pytest

from pysportbot import SportBot
from pysportbot.utils.errors import ErrorMessages


def test_bot_login_success(bot):
    """
    Test that the SportBot successfully logs in using valid credentials.
    """
    assert bot.is_logged_in(), "SportBot failed to log in with valid credentials."


def test_login_with_invalid_centre_raises_error():
    """
    Test that logging in with an invalid centre raises a ValueError with the correct message.
    """
    invalid_centre = "nonexistent-centre"
    bot = SportBot()

    with pytest.raises(ValueError, match=ErrorMessages.centre_not_found(invalid_centre)):
        bot.login("test@example.com", "somepassword", invalid_centre)


def test_login_with_invalid_credentials_raises_error():
    """
    Test that logging in with invalid credentials raises an Exception with the correct message.
    """
    bot = SportBot()

    with pytest.raises(Exception, match=ErrorMessages.login_failed()):
        bot.login("invalid_email@example.com", "wrong_password", "kirolklub")
