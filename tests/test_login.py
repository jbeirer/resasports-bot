import pytest

from pysportbot.utils.errors import ErrorMessages


def test_login(bot):

    # Check if the bot is logged in
    assert bot.is_logged_in(), "Bot failed to log in."


def test_login_failure():
    """Test login with invalid credentials."""
    from pysportbot import SportBot

    bot = SportBot()
    with pytest.raises(Exception, match=ErrorMessages.login_failed()):
        bot.login("invalid_email@example.com", "wrong_password")
