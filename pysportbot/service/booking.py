import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any

import pytz

from pysportbot import SportBot
from pysportbot.utils.errors import ErrorMessages
from pysportbot.utils.logger import get_logger

from .scheduling import calculate_class_day, calculate_next_execution

logger = get_logger(__name__)


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
            bot.book(activity=activity, start_time=f"{booking_date} {class_time}")

        except Exception as e:
            error_str = str(e)
            logger.warning(f"Attempt {attempt_num} failed: {error_str}")

            # Decide whether to retry based on the error message
            if ErrorMessages.slot_already_booked() in error_str:
                logger.warning("Slot already booked; skipping further retries.")
                return
            if ErrorMessages.slot_capacity_full() in error_str:
                logger.warning("Slot capacity full; skipping further retries.")
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
    config: dict[str, Any],
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

    # Booking execution day and time
    booking_execution = config["booking_execution"]

    # Exact time when booking will be executed (modulo global booking delay)
    execution_time = calculate_next_execution(booking_execution, time_zone)

    # Get the time now
    now = datetime.now(pytz.timezone(time_zone))

    # Calculate the seconds until execution
    time_until_execution = (execution_time - now).total_seconds()

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

        # Re-authenticate before booking
        logger.info("Re-authenticating before booking.")
        try:
            bot.login(config["email"], config["password"], config["centre"])
        except Exception:
            logger.warning("Re-authentication failed before booking execution.")

        # Wait the remaining time until execution
        now = datetime.now(pytz.timezone(time_zone))
        remaining_time = (execution_time - now).total_seconds()
        if remaining_time > 0:
            logger.info(f"Waiting {remaining_time:.2f} seconds until booking execution.")
            time.sleep(remaining_time)

    # Global booking delay
    if booking_delay > 0:
        logger.info(f"Waiting {booking_delay} seconds before attempting booking.")
        time.sleep(booking_delay)

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
                logger.error(f"Booking for '{activity}' at {class_time} failed.")
