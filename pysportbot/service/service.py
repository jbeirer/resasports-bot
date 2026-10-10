import logging
import math

from pysportbot import SportBot
from pysportbot.service.booking import schedule_bookings
from pysportbot.service.config import ServiceConfig, validate_activities
from pysportbot.service.results import BookingResult, log_summary
from pysportbot.service.retry import RetryPolicy

logger = logging.getLogger(__name__)


def run_service(
    config: ServiceConfig,
    *,
    booking_delay: float = 0,
    retry_attempts: int = 3,
    retry_delay: float = 5,
    poll_interval: float = 0.5,
    poll_window: float = 60,
    time_zone: str = "Europe/Madrid",
    log_level: str = "INFO",
    max_threads: int | None = None,
    dry_run: bool = False,
) -> list[BookingResult]:
    """
    Run the booking service with the given configuration.

    Args:
        config (ServiceConfig): The parsed service configuration, e.g. from `load_config`.
        booking_delay (float): Delay in seconds before booking execution.
        retry_attempts (int): Maximum number of booking attempts per class that fail with an error that may be
            temporary, such as a network error.
        retry_delay (float): Delay in seconds after such an error.
        poll_interval (float): Delay in seconds between attempts while a slot is not bookable yet or not found.
        poll_window (float): How long to keep polling, in seconds after the execution time.
        time_zone (str): Time zone for the booking.
        log_level (str): Logging level for the service.
        max_threads (int | None): Maximum number of classes booked in parallel. None books all classes in parallel.
        dry_run (bool): Do everything, including waiting and finding the slots, but send no booking requests.

    Returns:
        list[BookingResult]: One result per class, in the order of the configuration.

    Raises:
        ValueError: If retry_attempts < 1, poll_interval <= 0, max_threads < 1, or booking_delay, retry_delay or
            poll_window is negative.
        ConfigError: If an activity in the configuration does not exist.
    """
    # Validate service arguments
    policy = RetryPolicy(
        retry_attempts=retry_attempts,
        retry_delay=retry_delay,
        poll_interval=poll_interval,
        poll_window=poll_window,
    )
    if not (math.isfinite(booking_delay) and booking_delay >= 0):
        raise ValueError(f"booking_delay must be a non-negative number of seconds, got {booking_delay}.")
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

    results = schedule_bookings(
        bot,
        config,
        policy,
        booking_delay=booking_delay,
        time_zone=time_zone,
        max_threads=n_threads,
        dry_run=dry_run,
    )

    log_summary(results)
    failed = sum(not r.ok for r in results)
    if failed:
        logger.error(f"{failed} of {len(results)} classes could not be booked.")
    else:
        logger.info("Dry run completed." if dry_run else "All bookings completed.")
    return results
