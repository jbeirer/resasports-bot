import os
from typing import Any, Dict

from pysportbot import SportBot
from pysportbot.service.booking import schedule_bookings
from pysportbot.service.config_validator import validate_activities, validate_config
from pysportbot.utils.logger import get_logger


def run_service(
    config: Dict[str, Any],
    booking_delay: int,
    retry_attempts: int,
    retry_delay: int,
    time_zone: str = "Europe/Madrid",
    log_level: str = "INFO",
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
    bot = SportBot(log_level=log_level, time_zone=time_zone)
    bot.login(config["email"], config["password"], config["centre"])

    # Validate activities in the configuration
    validate_activities(bot, config)

    # Determine the number of threads
    max_threads = min(len(config["classes"]), os.cpu_count() or 1)
    logger.info(f"Using up to {max_threads} threads for booking {len(config['classes'])} activities.")

    # Schedule bookings in parallel
    schedule_bookings(
        bot,
        config["classes"],
        config["booking_execution"],
        booking_delay,
        retry_attempts,
        retry_delay,
        time_zone,
        max_threads,
    )

    logger.info("All bookings completed.")
