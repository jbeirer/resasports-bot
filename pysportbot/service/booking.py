import time
from datetime import datetime, timedelta
from typing import Any, Dict

import pytz
import schedule

from pysportbot import SportBot
from pysportbot.utils.errors import ErrorMessages
from pysportbot.utils.logger import get_logger

from .config_validator import DAY_MAP
from .scheduling import calculate_class_day, calculate_next_execution

logger = get_logger(__name__)


def _raise_no_matching_slots_error(activity: str, class_time: str, booking_date: str) -> None:
    """
    Helper function to raise a ValueError for no matching slots.
    """
    raise ValueError(ErrorMessages.no_matching_slots_for_time(activity, class_time, booking_date))


def attempt_booking(
    bot: SportBot,
    cls: Dict[str, Any],
    offset_seconds: int,
    retry_attempts: int = 1,
    retry_delay_minutes: int = 0,
    time_zone: str = "Europe/Madrid",
) -> None:
    activity = cls["activity"]
    class_day = cls["class_day"]
    class_time = cls["class_time"]
    booking_execution = cls["booking_execution"]

    for attempt_num in range(1, retry_attempts + 1):
        booking_date = calculate_class_day(class_day, time_zone).strftime("%Y-%m-%d")

        try:
            logger.info(f"Fetching available slots for {activity} on {booking_date}")
            available_slots = bot.daily_slots(activity=activity, day=booking_date)

            matching_slots = available_slots[available_slots["start_timestamp"] == f"{booking_date} {class_time}"]
            if matching_slots.empty:
                _raise_no_matching_slots_error(activity, class_time, booking_date)

            if booking_execution != "now":
                logger.info(f"Waiting {offset_seconds} seconds before attempting booking.")
                time.sleep(offset_seconds)

            slot_id = matching_slots.iloc[0]["start_timestamp"]
            logger.info(f"Attempting to book slot for {activity} at {slot_id} (Attempt {attempt_num}/{retry_attempts})")
            bot.book(activity=activity, start_time=slot_id)
            logger.info(f"Successfully booked {activity} at {slot_id}")

        except Exception as e:
            error_str = str(e)
            logger.warning(f"Attempt {attempt_num} failed for {activity}: {error_str}")

            if ErrorMessages.slot_already_booked() in error_str:
                logger.warning(f"{activity} at {class_time} on {booking_date} is already booked; skipping retry.")
                return

            if attempt_num < retry_attempts:
                logger.info(f"Retrying in {retry_delay_minutes} minutes...")
                time.sleep(retry_delay_minutes * 60)
        else:
            return

    logger.error(f"Failed to book {activity} after {retry_attempts} attempts.")


def schedule_bookings(
    bot: SportBot,
    config: Dict[str, Any],
    cls: Dict[str, Any],
    offset_seconds: int,
    retry_attempts: int,
    retry_delay_minutes: int,
    time_zone: str = "Europe/Madrid",
) -> None:
    booking_execution = cls["booking_execution"]
    weekly = cls["weekly"]
    activity = cls["activity"]
    class_day = cls["class_day"]
    class_time = cls["class_time"]

    if weekly:
        # For weekly bookings, schedule recurring jobs
        execution_day, execution_time = booking_execution.split()
        logger.info(
            f"Class '{activity}' on {class_day} at {class_time} "
            f"will be booked every {execution_day} at {execution_time}."
        )

        def booking_task() -> None:
            try:
                logger.info("Re-authenticating before weekly booking...")
                bot.login(config["email"], config["password"], config["centre"])
                logger.info("Re-authentication successful.")
                attempt_booking(
                    bot,
                    cls,
                    offset_seconds,
                    retry_attempts,
                    retry_delay_minutes,
                    time_zone,
                )
            except Exception:
                logger.exception(f"Failed to execute weekly booking task for {activity}")

        # e.g., schedule.every().monday.at("HH:MM:SS").do(...)
        getattr(schedule.every(), execution_day.lower()).at(execution_time).do(booking_task)

    else:
        # For one-off (non-weekly) bookings, calculate exact date/time
        next_execution = calculate_next_execution(booking_execution, time_zone)
        tz = pytz.timezone(time_zone)

        day_of_week_target = DAY_MAP[class_day.lower().strip()]
        execution_day_of_week = next_execution.weekday()

        days_to_class = (day_of_week_target - execution_day_of_week + 7) % 7
        planned_class_date_dt = next_execution + timedelta(days=days_to_class)
        planned_class_date_str = planned_class_date_dt.strftime("%Y-%m-%d (%A)")

        next_execution_str = next_execution.strftime("%Y-%m-%d (%A) %H:%M:%S %z")

        logger.info(
            f"Class '{activity}' on {planned_class_date_str} at {class_time} "
            f"will be booked on {next_execution_str}."
        )

        # Wait until the next execution time
        time_until_execution = (next_execution - datetime.now(tz)).total_seconds()
        time.sleep(max(0, time_until_execution))

        attempt_booking(
            bot,
            cls,
            offset_seconds,
            retry_attempts=retry_attempts,
            retry_delay_minutes=retry_delay_minutes,
            time_zone=time_zone,
        )
