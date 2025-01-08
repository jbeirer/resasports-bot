from typing import Any, Dict

from pysportbot import SportBot
from pysportbot.service.booking import schedule_bookings
from pysportbot.service.config_validator import validate_activities, validate_config
from pysportbot.service.threading import get_n_threads
from pysportbot.utils.logger import get_logger


def run_service(
    config: Dict[str, Any],
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
    """
    # Initialize logger
    logger = get_logger(__name__)
    logger.setLevel(log_level)

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
