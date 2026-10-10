import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from functools import partial
from zoneinfo import ZoneInfo

import requests

from pysportbot import SportBot
from pysportbot.exceptions import SlotAlreadyBookedError, SlotFullError, SportBotError

from .config import WEEKDAY_NAMES, ServiceConfig
from .scheduling import next_class_date, next_execution

logger = logging.getLogger(__name__)


def attempt_booking(
    bot: SportBot,
    activity: str,
    start: datetime,
    retry_attempts: int = 1,
    retry_delay: int = 0,
    *,
    dry_run: bool = False,
) -> None:
    """
    Attempt to book a slot for the given class.

    Args:
        bot (SportBot): The SportBot instance.
        activity (str): Activity name.
        start (datetime): Timezone-aware start time of the class.
        retry_attempts (int): Number of retry attempts.
        retry_delay (int): Delay between retries.
        dry_run (bool): Find the slot and check that it is open, but send no booking request.
    """
    for attempt_num in range(1, retry_attempts + 1):
        try:
            if dry_run:
                _dry_run_booking(bot, activity, start)
            else:
                bot.book(activity=activity, start=start)

        except (SlotAlreadyBookedError, SlotFullError) as e:
            # Retrying cannot succeed
            logger.warning(f"Attempt {attempt_num} failed: {e} Skipping further retries.")
            return

        except (SportBotError, requests.RequestException) as e:
            # E.g. not bookable yet, unavailable, slot not found, unexpected API response or network error
            logger.warning(f"Attempt {attempt_num} failed: {e}")

            if attempt_num < retry_attempts:
                logger.info(f"Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
        else:
            return

    # If all attempts fail, log an error
    # Do not raise an exception to allow other bookings to proceed
    logger.error(f"Failed to book {_describe(activity, start)} after {retry_attempts} attempts.")


def _dry_run_booking(bot: SportBot, activity: str, start: datetime) -> None:
    """
    Check that the slot exists and is open, and log what booking would do, without sending a booking request.

    Raises:
        SlotFullError: If the slot has no places left, as `SportBot.book()` would.
        SportBotError: If the slot cannot be found, see `SportBot.find_slot()`.
    """
    slot = bot.find_slot(activity=activity, start=start)
    if slot.cancelled:
        logger.warning(f"DRY RUN: {_describe(activity, start)} is cancelled, so booking it would fail.")
    elif slot.is_full:
        raise SlotFullError(str(slot.id))
    else:
        logger.info(
            f"DRY RUN: would book {_describe(activity, start)} "
            f"(slot {slot.id}, {slot.inscribed}/{slot.capacity} places taken)."
        )


def _describe(activity: str, start: datetime) -> str:
    """Describe a class as e.g. "'Yoga' on Monday 2026-01-12 at 18:00"."""
    time_format = "%H:%M:%S" if start.second else "%H:%M"
    return f"'{activity}' on {WEEKDAY_NAMES[start.weekday()]} {start:%Y-%m-%d} at {start.strftime(time_format)}"


def schedule_bookings(
    bot: SportBot,
    config: ServiceConfig,
    booking_delay: int,
    retry_attempts: int,
    retry_delay: int,
    time_zone: str,
    max_threads: int,
    *,
    dry_run: bool = False,
) -> None:
    """
    Execute bookings in parallel with a limit on the number of threads.

    Args:
        bot (SportBot): The SportBot instance.
        config (ServiceConfig): The service configuration.
        booking_delay (int): Delay before each booking attempt.
        retry_attempts (int): Number of retry attempts.
        retry_delay (int): Delay between retries.
        time_zone (str): Timezone for booking.
        max_threads (int): Maximum number of threads to use.
        dry_run (bool): Find the slots, but send no booking requests.
    """
    tz = ZoneInfo(time_zone)
    now = datetime.now(tz)

    # Exact time when booking will be executed (modulo global booking delay)
    execution_time = next_execution(config.execution, now)

    # Classes are booked for the week following the execution
    bookings = [
        (cls.activity, datetime.combine(next_class_date(cls.weekday, execution_time), cls.time, tzinfo=tz))
        for cls in config.classes
    ]
    for activity, start in bookings:
        logger.info(f"Scheduled to book {_describe(activity, start)}.")

    # Calculate the seconds until execution. Subtracting datetimes that share a ZoneInfo gives the wall-clock
    # difference, which is off by an hour across a DST change, so compare the absolute timestamps instead
    time_until_execution = execution_time.timestamp() - now.timestamp()

    if time_until_execution > 0:
        logger.info(
            f"Waiting {time_until_execution:.2f} seconds until global execution time: "
            f"{execution_time.strftime('%Y-%m-%d %H:%M:%S %z')}."
        )
        # Re-authenticate 60 seconds before booking execution
        reauth_time = time_until_execution - 60

        if reauth_time <= 0:
            logger.debug("Less than 60 seconds remain until execution; re-authenticating now.")
        else:
            logger.debug(f"Re-authenticating in {reauth_time:.2f} seconds.")
            time.sleep(reauth_time)

        # Re-authenticate before booking if necessary
        try:
            bot.ensure_logged_in()
        except Exception as e:
            logger.warning(f"Re-authentication failed before booking execution with {e}.")

        # Wait the remaining time until execution
        now = datetime.now(tz)
        remaining_time = execution_time.timestamp() - now.timestamp()
        if remaining_time > 0:
            logger.info(f"Waiting {remaining_time:.2f} seconds until booking execution.")
        time.sleep(max(0, remaining_time))

    # Global booking delay
    if booking_delay > 0:
        logger.info(f"Waiting {booking_delay} seconds before attempting booking.")
        time.sleep(booking_delay)

    # Submit bookings in parallel
    book = partial(attempt_booking, bot, retry_attempts=retry_attempts, retry_delay=retry_delay, dry_run=dry_run)
    with ThreadPoolExecutor(max_workers=max_threads) as executor:
        future_to_booking = {
            executor.submit(book, activity=activity, start=start): (activity, start) for activity, start in bookings
        }

        for future in as_completed(future_to_booking):
            activity, start = future_to_booking[future]
            try:
                future.result()
            except Exception:
                logger.exception(f"Booking {_describe(activity, start)} failed.")
