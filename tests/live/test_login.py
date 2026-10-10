# test_login.py


import pytest

from pysportbot import AuthenticationError, CentreNotFoundError, SportBot


def test_bot_login_success(bot):
    """
    Test that the SportBot successfully logs in using valid credentials.
    """
    assert bot.is_logged_in(), "SportBot failed to log in with valid credentials."


def test_centres_include_logged_in_centre(bot, live_credentials):
    """
    Test that the centre used for login is listed, and found by searching for its slug.
    """
    centre = live_credentials[2]
    assert centre in [c.slug for c in bot.centres()]
    assert centre in [c.slug for c in bot.centres(search=centre.upper())]


def test_login_with_invalid_centre_raises_error():
    """
    Test that logging in with an invalid centre raises a CentreNotFoundError.
    """
    invalid_centre = "nonexistent-centre"
    bot = SportBot()

    with pytest.raises(CentreNotFoundError):
        bot.login("test@example.com", "somepassword", invalid_centre)


def test_login_with_invalid_credentials_raises_error():
    """
    Test that logging in with invalid credentials raises an AuthenticationError.
    """
    bot = SportBot()

    with pytest.raises(AuthenticationError):
        bot.login("invalid_email@example.com", "wrong_password", "kirolklub")
