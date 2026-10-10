import logging
from typing import Any

from pysportbot import SportBot
from pysportbot.service.booking import schedule_bookings
from pysportbot.service.config_validator import validate_activities, validate_config
from pysportbot.service.threading import get_n_threads

logger = logging.getLogger(__name__)


def run_service(
    config: dict[str, Any],
    booking_delay: int,
    retry_attempts: int,
    retry_delay: int,
    time_zone: str = "Europe/Madrid",
    log_level: str = "INFO",
    max_threads: int = -1,
) -> None:
    """
    Run the booking service with the given configuration.

    Args:
        config (dict): Configuration dictionary for booking service.
        booking_delay (int): Delay before each booking attempt.
        retry_attempts (int): Number of retry attempts.
        retry_delay (int): Delay between retry attempts in minutes.
        time_zone (str): Time zone for the booking.
        log_level (str): Logging level for the service.

    Raises:
        ValueError: If retry_attempts < 1, retry_delay < 0, booking_delay < 0, or the config is invalid.
    """
    # Validate service arguments
    if retry_attempts < 1:
        raise ValueError(f"retry_attempts must be at least 1, got {retry_attempts}.")
    if retry_delay < 0:
        raise ValueError(f"retry_delay must not be negative, got {retry_delay}.")
    if booking_delay < 0:
        raise ValueError(f"booking_delay must not be negative, got {booking_delay}.")

    # Validate configuration
    validate_config(config)

    # Initialize the SportBot and authenticate
    # Note: will re-authenticate before booking execution
    # to ensure the session is still valid
    bot = SportBot(log_level=log_level, time_zone=time_zone)
    bot.login(config["email"], config["password"], config["centre"])

    # Validate activities in the configuration
    validate_activities(bot, config)

    # Determine the number of threads, where threads -1 defaults to all available cores
    requested_bookings = len(config["classes"])
    max_threads = get_n_threads(max_threads, requested_bookings)

    # Schedule bookings in parallel
    schedule_bookings(
        bot,
        config,
        booking_delay,
        retry_attempts,
        retry_delay,
        time_zone,
        max_threads,
    )

    logger.info("All bookings completed.")
