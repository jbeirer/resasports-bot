import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any, Dict, List

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
    offset_seconds: int,
    retry_attempts: int = 1,
    retry_delay_minutes: int = 0,
    time_zone: str = "Europe/Madrid",
) -> None:
    """
    Attempt to book a slot for the given class.

    Args:
        bot (SportBot): The SportBot instance.
        activity (str): Activity name.
        class_day (str): Day of the class.
        class_time (str): Time of the class.
        offset_seconds (int): Delay before attempting booking.
        retry_attempts (int): Number of retry attempts.
        retry_delay_minutes (int): Delay between retries.
        time_zone (str): Time zone for execution.
    """
    for attempt_num in range(1, retry_attempts + 1):
        booking_date = calculate_class_day(class_day, time_zone).strftime("%Y-%m-%d")

        try:
            logger.info(f"Fetching available slots for '{activity}' on {booking_date}.")
            available_slots = bot.daily_slots(activity=activity, day=booking_date)

            matching_slots = available_slots[available_slots["start_timestamp"] == f"{booking_date} {class_time}"]
            if matching_slots.empty:
                _raise_no_matching_slots_error(activity, class_time, booking_date)

            logger.info(f"Waiting {offset_seconds} seconds before attempting booking.")
            time.sleep(offset_seconds)

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
                logger.info(f"Retrying in {retry_delay_minutes} minutes...")
                time.sleep(retry_delay_minutes * 60)
        else:
            # If the booking attempt succeeds, log and exit
            logger.info(f"Successfully booked '{activity}' at {slot_id}.")
            return

    # If all attempts fail, log an error
    logger.error(f"Failed to book '{activity}' after {retry_attempts} attempts.")


def schedule_bookings_parallel(
    bot: SportBot,
    classes: List[Dict[str, Any]],
    booking_execution: str,
    offset_seconds: int,
    retry_attempts: int,
    retry_delay_minutes: int,
    time_zone: str,
    max_threads: int,
) -> None:
    """
    Execute bookings in parallel with a limit on the number of threads.

    Args:
        bot (SportBot): The SportBot instance.
        classes (list): List of class configurations.
        booking_execution (str): Global execution time for all bookings.
        offset_seconds (int): Delay before each booking attempt.
        retry_attempts (int): Number of retry attempts.
        retry_delay_minutes (int): Delay between retries.
        time_zone (str): Timezone for booking.
        max_threads (int): Maximum number of threads to use.
    """
    # Log planned bookings
    for cls in classes:
        logger.info(f"Scheduled to book '{cls['activity']}' next {cls['class_day']} at {cls['class_time']}.")

    # Wait globally before starting bookings
    wait_for_execution(booking_execution, time_zone)

    with ThreadPoolExecutor(max_workers=max_threads) as executor:
        future_to_class = {
            executor.submit(
                attempt_booking,
                bot,
                cls["activity"],
                cls["class_day"],
                cls["class_time"],
                offset_seconds,
                retry_attempts,
                retry_delay_minutes,
                time_zone,
            ): cls
            for cls in classes
        }

        for future in as_completed(future_to_class):
            cls = future_to_class[future]
            activity, class_time = cls["activity"], cls["class_time"]
            try:
                future.result()
                logger.info(f"Booking for '{activity}' at {class_time} completed successfully.")
            except Exception:
                logger.exception(f"Booking for '{activity}' at {class_time} failed.")
