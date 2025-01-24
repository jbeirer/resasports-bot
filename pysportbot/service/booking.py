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


def _raise_no_matching_slots_error(activity: str, class_time: str, booking_date: str) -> None:
    raise ValueError(ErrorMessages.no_matching_slots_for_time(activity, class_time, booking_date))


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
    Attempt to book a slot for a specific sports class with configurable retry mechanism.
    
    Parameters:
        bot (SportBot): The SportBot instance used for booking classes.
        activity (str): Name of the sports activity to book.
        class_day (str): Day of the week for the desired class.
        class_time (str): Specific time of the class to book.
        retry_attempts (int, optional): Maximum number of booking attempts. Defaults to 1.
        retry_delay (int, optional): Delay in seconds between retry attempts. Defaults to 0.
        time_zone (str, optional): Time zone for calculating the booking date. Defaults to "Europe/Madrid".
    
    Behavior:
        - Calculates the exact booking date based on the class day and time zone
        - Retrieves available slots for the specified activity
        - Attempts to book a matching slot with configurable retry logic
        - Stops retrying if the slot is already booked
        - Logs detailed information about booking attempts and failures
    
    Raises:
        ValueError: If no matching slots are found for the specified activity and time
    
    Notes:
        - Does not raise an exception if all booking attempts fail
        - Allows other bookings to proceed even if this specific booking fails
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
    config: dict[str, Any],
    booking_delay: int,
    retry_attempts: int,
    retry_delay: int,
    time_zone: str,
    max_threads: int,
) -> None:
    """
    Schedule and execute sports class bookings in parallel with precise timing and re-authentication.
    
    Coordinates booking attempts for multiple sports classes using a thread pool, with configurable retry mechanisms and global execution timing. Handles re-authentication before booking and manages parallel execution of booking attempts.
    
    Parameters:
        bot (SportBot): Authenticated SportBot instance for making class bookings.
        config (dict): Configuration dictionary containing booking details.
            - "classes" (list): List of class configurations to book
            - "booking_execution" (str): Global execution time for bookings
            - "email" (str): User's login email
            - "password" (str): User's login password
            - "centre" (str): Sports center identifier
        booking_delay (int): Global delay in seconds before initiating bookings
        retry_attempts (int): Number of retry attempts for each booking
        retry_delay (int): Delay between booking retry attempts in seconds
        time_zone (str): Timezone for booking calculations (e.g., "Europe/Madrid")
        max_threads (int): Maximum number of concurrent booking threads
    
    Behavior:
        - Logs planned bookings for each class
        - Calculates precise global execution time
        - Re-authenticates 60 seconds before booking execution
        - Waits for the exact booking time
        - Applies a global booking delay
        - Submits booking attempts in parallel
        - Logs individual booking attempt results
    
    Raises:
        Exception: If re-authentication fails or any booking attempt encounters a critical error
    """
    # Log planned bookings
    for cls in config["classes"]:
        logger.info(f"Scheduled to book '{cls['activity']}' next {cls['class_day']} at {cls['class_time']}.")

    # Booking execution day and time
    booking_execution = config["booking_execution"]

    # Exact time when booking will be executed (modulo global boooking delay)
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
        # Wait for re-authentication
        time.sleep(reauth_time)

        # Re-authenticate before booking
        logger.info("Re-authenticating before booking.")
        try:
            bot.login(config["email"], config["password"], config["centre"])
        except Exception:
            logger.exception("Re-authentication failed before booking execution.")
            raise

        # Wait the remaining time until execution
        now = datetime.now(pytz.timezone(time_zone))
        remaining_time = (execution_time - now).total_seconds()
        if remaining_time > 0:
            logger.info(f"Waiting {remaining_time:.2f} seconds until booking execution.")
            time.sleep(remaining_time)

    # Global booking delay
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
                logger.exception(f"Booking for '{activity}' at {class_time} failed.")
