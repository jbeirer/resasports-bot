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


def test_login_with_invalid_centre_raises_error(live_credentials):
    """
    Test that logging in to a centre the account is not registered at raises a CentreNotFoundError.
    """
    email, password, centre = live_credentials
    bot = SportBot()

    with pytest.raises(CentreNotFoundError) as exc_info:
        bot.login(email, password, "nonexistent-centre")

    # The error lists the centres of the account, so it includes the one the account logs in to
    assert centre in exc_info.value.available


def test_login_with_invalid_credentials_raises_error():
    """
    Test that logging in with invalid credentials raises an AuthenticationError.
    """
    bot = SportBot()

    with pytest.raises(AuthenticationError):
        bot.login("invalid_email@example.com", "wrong_password", "kirolklub")
