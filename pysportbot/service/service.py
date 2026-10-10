import logging

from pysportbot import SportBot
from pysportbot.service.booking import schedule_bookings
from pysportbot.service.config import ServiceConfig, validate_activities

logger = logging.getLogger(__name__)


def run_service(
    config: ServiceConfig,
    *,
    booking_delay: int = 0,
    retry_attempts: int = 3,
    retry_delay: int = 5,
    time_zone: str = "Europe/Madrid",
    log_level: str = "INFO",
    max_threads: int | None = None,
    dry_run: bool = False,
) -> None:
    """
    Run the booking service with the given configuration.

    Args:
        config (ServiceConfig): The parsed service configuration, e.g. from `load_config`.
        booking_delay (int): Delay in seconds before booking execution.
        retry_attempts (int): Number of booking attempts per class.
        retry_delay (int): Delay in seconds between retry attempts.
        time_zone (str): Time zone for the booking.
        log_level (str): Logging level for the service.
        max_threads (int | None): Maximum number of classes booked in parallel. None books all classes in parallel.
        dry_run (bool): Do everything, including waiting and finding the slots, but send no booking requests.

    Raises:
        ValueError: If retry_attempts < 1, retry_delay < 0, booking_delay < 0 or max_threads < 1.
        ConfigError: If an activity in the configuration does not exist.
    """
    # Validate service arguments
    if retry_attempts < 1:
        raise ValueError(f"retry_attempts must be at least 1, got {retry_attempts}.")
    if retry_delay < 0:
        raise ValueError(f"retry_delay must not be negative, got {retry_delay}.")
    if booking_delay < 0:
        raise ValueError(f"booking_delay must not be negative, got {booking_delay}.")
    if max_threads is not None and max_threads < 1:
        raise ValueError(f"max_threads must be at least 1, got {max_threads}.")

    # Initialize the SportBot and authenticate
    # Note: will re-authenticate before booking execution
    # to ensure the session is still valid
    bot = SportBot(log_level=log_level, time_zone=time_zone)
    logger.info(f"Booking execution: {config.execution or 'now'}")
    if dry_run:
        logger.info("DRY RUN: no booking requests will be sent.")
    bot.login(config.email, config.password, config.centre)

    # Validate activities in the configuration
    validate_activities(bot, config)

    # Booking is I/O-bound, so book all classes in parallel unless capped
    n_threads = len(config.classes) if max_threads is None else min(max_threads, len(config.classes))
    logger.debug(f"Using {n_threads} threads to book {len(config.classes)} classes.")

    # Schedule bookings in parallel
    schedule_bookings(
        bot,
        config,
        booking_delay,
        retry_attempts,
        retry_delay,
        time_zone,
        n_threads,
        dry_run=dry_run,
    )

    logger.info("Dry run completed." if dry_run else "All bookings completed.")
