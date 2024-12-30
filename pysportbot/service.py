#!/usr/bin/env python3

import argparse
import json
import time
from datetime import datetime, timedelta
from typing import Any, Dict, cast

import pytz
import schedule

from pysportbot import SportBot
from pysportbot.utils.errors import ErrorMessages
from pysportbot.utils.logger import get_logger

logger = get_logger(__name__)

DAY_MAP = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}


def load_config(config_path: str) -> Dict[str, Any]:
    with open(config_path) as f:
        return cast(Dict[str, Any], json.load(f))


def validate_config(config: Dict[str, Any]) -> None:
    required_keys = ["email", "password", "classes"]
    for key in required_keys:
        if key not in config:
            raise ValueError(ErrorMessages.missing_required_key(key))

    for cls in config["classes"]:
        if (
            "activity" not in cls
            or "class_day" not in cls
            or "class_time" not in cls
            or "booking_execution" not in cls
            or "weekly" not in cls
        ):
            raise ValueError(ErrorMessages.invalid_class_definition())

        if cls["weekly"] and cls["booking_execution"] == "now":
            raise ValueError(ErrorMessages.invalid_weekly_now())

        if cls["booking_execution"] != "now":
            day_and_time = cls["booking_execution"].split()
            if len(day_and_time) != 2:
                raise ValueError(ErrorMessages.invalid_booking_execution_format())
            _, exec_time = day_and_time
            try:
                datetime.strptime(exec_time, "%H:%M:%S")
            except ValueError as err:
                raise ValueError(ErrorMessages.invalid_booking_execution_format()) from err


def validate_activities(bot: SportBot, config: Dict[str, Any]) -> None:
    logger.info("Fetching available activities for validation...")
    available_activities = bot.activities()
    available_activity_names = set(available_activities["name_activity"].tolist())

    logger.debug(f"Available activities: {available_activity_names}")

    for cls in config["classes"]:
        activity_name = cls["activity"]
        if activity_name not in available_activity_names:
            raise ValueError(ErrorMessages.activity_not_found(activity_name, list(available_activity_names)))
    logger.info("All activities in the configuration file have been validated.")


def validate_config_and_activities(config: Dict[str, Any], bot: SportBot) -> None:
    validate_config(config)
    validate_activities(bot, config)


def calculate_next_execution(booking_execution: str, time_zone: str = "Europe/Madrid") -> datetime:
    """
    Calculate the next execution time based on the booking execution day and time.

    Args:
        booking_execution (str): Execution in the format 'Day HH:MM:SS' or 'now'.
        time_zone (str): The timezone for localization.

    Returns:
        datetime: The next execution time as a timezone-aware datetime.
    """
    tz = pytz.timezone(time_zone)

    # Handle the special case where execution is "now"
    if booking_execution == "now":
        return datetime.now(tz)

    # Split the booking execution string into day and time components
    execution_day, execution_time = booking_execution.split()
    now = datetime.now(tz)

    # Map the day name to a day-of-week index (0 = Monday, 6 = Sunday)
    day_of_week_target = DAY_MAP[execution_day.lower().strip()]
    current_weekday = now.weekday()

    # Parse the execution time
    exec_time = datetime.strptime(execution_time, "%H:%M:%S").time()

    # Determine the next execution date
    if day_of_week_target == current_weekday and now.time() < exec_time:
        # If the target day is today and the time is in the future, schedule for today
        next_execution_date = now
    else:
        # Otherwise, calculate the next occurrence of the target day
        days_ahead = day_of_week_target - current_weekday
        if days_ahead <= 0:  # If the target day is earlier this week, move to the next week
            days_ahead += 7
        next_execution_date = now + timedelta(days=days_ahead)

    # Combine the execution date and time into a naive datetime
    execution_datetime = datetime.combine(next_execution_date.date(), exec_time)

    # Localize the naive datetime to the specified timezone
    if execution_datetime.tzinfo is None:
        execution_datetime = tz.localize(execution_datetime)

    return execution_datetime


def calculate_class_day(class_day: str, time_zone: str = "Europe/Madrid") -> datetime:
    tz = pytz.timezone(time_zone)
    now = datetime.now(tz)
    target_weekday = DAY_MAP[class_day.lower().strip()]
    days_ahead = target_weekday - now.weekday()
    if days_ahead < 0:
        days_ahead += 7
    return now + timedelta(days=days_ahead)


def _raise_no_matching_slots_error(activity: str, class_time: str, booking_date: str) -> None:
    """
    Helper function to raise a ValueError for no matching slots.
    This satisfies TRY301 by moving the long raise statement out of the main code.
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
            logger.info(
                f"Attempting to book slot for {activity} at {slot_id} " f"(Attempt {attempt_num}/{retry_attempts})"
            )
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
                bot.login(config["email"], config["password"])
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

        getattr(schedule.every(), execution_day.lower()).at(execution_time).do(booking_task)

    else:
        # For non-weekly bookings, calculate exact dates
        next_execution = calculate_next_execution(booking_execution, time_zone)
        tz = pytz.timezone(time_zone)

        day_of_week_target = DAY_MAP[class_day.lower().strip()]
        execution_day_of_week = next_execution.weekday()

        # Find the next class date relative to the execution time
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


def run_service(
    config: Dict[str, Any],
    offset_seconds: int,
    retry_attempts: int,
    retry_delay_minutes: int,
    time_zone: str = "Europe/Madrid",
) -> None:
    bot = SportBot()
    bot.login(config["email"], config["password"])

    validate_config_and_activities(config, bot)

    for cls in config["classes"]:
        schedule_bookings(
            bot,
            config,
            cls,
            offset_seconds,
            retry_attempts,
            retry_delay_minutes,
            time_zone,
        )

    if schedule.jobs:
        logger.info("Weekly bookings scheduled. Running the scheduler...")
        while True:
            schedule.run_pending()
            time.sleep(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the pysportbot as a service.")
    parser.add_argument("--config", type=str, required=True, help="Path to the JSON configuration file.")
    parser.add_argument("--offset-seconds", type=int, default=10, help="Time offset in seconds before booking.")
    parser.add_argument("--retry-attempts", type=int, default=3, help="Number of retry attempts for weekly bookings.")
    parser.add_argument(
        "--retry-delay-minutes", type=int, default=2, help="Delay in minutes between retries for weekly bookings."
    )
    parser.add_argument("--time_zone", type=str, default="Europe/Madrid", help="Timezone for the service.")
    args = parser.parse_args()

    config = load_config(args.config)
    run_service(config, args.offset_seconds, args.retry_attempts, args.retry_delay_minutes, args.time_zone)


if __name__ == "__main__":
    main()
