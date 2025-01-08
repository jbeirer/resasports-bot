import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any, Dict

import pytz

from pysportbot import SportBot
from pysportbot.utils.errors import ErrorMessages
from pysportbot.utils.logger import get_logger

from .scheduling import calculate_class_day, calculate_next_execution

logger = get_logger(__name__)


def _raise_no_matching_slots_error(activity: str, class_time: str, booking_date: str) -> None:
    raise ValueError(ErrorMessages.no_matching_slots_for_time(activity, class_time, booking_date))


def wait_for_execution(booking_execution: str, time_zone: str) -> None:
    """
    Wait until the specified global execution time.

    Args:
        booking_execution (str): Global execution time in "Day HH:MM:SS" format.
        time_zone (str): Timezone for calculation.
    """
    tz = pytz.timezone(time_zone)
    execution_time = calculate_next_execution(booking_execution, time_zone)
    now = datetime.now(tz)
    time_until_execution = (execution_time - now).total_seconds()

    if time_until_execution > 0:
        logger.info(
            f"Waiting {time_until_execution:.2f} seconds until global execution time: "
            f"{execution_time.strftime('%Y-%m-%d %H:%M:%S %z')}."
        )
        time.sleep(time_until_execution)


def attempt_booking(
    bot: SportBot,
    activity: str,
    class_day: str,
    class_time: str,
    retry_attempts: int = 1,
    retry_delay: int = 0,
    time_zone: str = "Europe/Madrid",
) -> None:
    """
    Attempt to book a slot for the given class.

    Args:
        bot (SportBot): The SportBot instance.
        activity (str): Activity name.
        class_day (str): Day of the class.
        class_time (str): Time of the class.
        retry_attempts (int): Number of retry attempts.
        retry_delay (int): Delay between retries.
        time_zone (str): Time zone for execution.
    """
    for attempt_num in range(1, retry_attempts + 1):
        booking_date = calculate_class_day(class_day, time_zone).strftime("%Y-%m-%d")

        try:
            available_slots = bot.daily_slots(activity=activity, day=booking_date)

            matching_slots = available_slots[available_slots["start_timestamp"] == f"{booking_date} {class_time}"]
            if matching_slots.empty:
                _raise_no_matching_slots_error(activity, class_time, booking_date)

            slot_id = matching_slots.iloc[0]["start_timestamp"]
            logger.info(f"Attempting to book '{activity}' at {slot_id} (Attempt {attempt_num}/{retry_attempts}).")
            bot.book(activity=activity, start_time=slot_id)

        except Exception as e:
            error_str = str(e)
            logger.warning(f"Attempt {attempt_num} failed: {error_str}")

            if ErrorMessages.slot_already_booked() in error_str:
                logger.warning("Slot already booked; skipping further retries.")
                return

            if attempt_num < retry_attempts:
                logger.info(f"Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
        else:
            return

    # If all attempts fail, log an error
    # Do not raise an exception to allow other bookings to proceed
    logger.error(f"Failed to book '{activity}' at {class_time} on {booking_date} after {retry_attempts} attempts.")


def schedule_bookings(
    bot: SportBot,
    config: Dict[str, Any],
    booking_delay: int,
    retry_attempts: int,
    retry_delay: int,
    time_zone: str,
    max_threads: int,
) -> None:
    """
    Execute bookings in parallel with a limit on the number of threads.

    Args:
        bot (SportBot): The SportBot instance.
        classes (list): List of class configurations.
        booking_execution (str): Global execution time for all bookings.
        booking_delay (int): Delay before each booking attempt.
        retry_attempts (int): Number of retry attempts.
        retry_delay (int): Delay between retries.
        time_zone (str): Timezone for booking.
        max_threads (int): Maximum number of threads to use.
    """
    # Log planned bookings
    for cls in config["classes"]:
        logger.info(f"Scheduled to book '{cls['activity']}' next {cls['class_day']} at {cls['class_time']}.")

    # Wait globally before starting bookings
    wait_for_execution(config["booking_execution"], time_zone)

    # Global booking delay
    logger.info(f"Waiting {booking_delay} seconds before attempting booking.")
    time.sleep(booking_delay)

    # Re-authenticate before booking
    logger.debug("Re-authenticating before booking.")
    try:
        bot.login(config["email"], config["password"], config["centre"])
    except Exception:
        logger.exception("Re-authentication failed before booking execution.")
        raise

    # Submit bookings in parallel
    with ThreadPoolExecutor(max_workers=max_threads) as executor:
        future_to_class = {
            executor.submit(
                attempt_booking,
                bot,
                cls["activity"],
                cls["class_day"],
                cls["class_time"],
                retry_attempts,
                retry_delay,
                time_zone,
            ): cls
            for cls in config["classes"]
        }

        for future in as_completed(future_to_class):
            cls = future_to_class[future]
            activity, class_time = cls["activity"], cls["class_time"]
            try:
                future.result()
            except Exception:
                logger.exception(f"Booking for '{activity}' at {class_time} failed.")
