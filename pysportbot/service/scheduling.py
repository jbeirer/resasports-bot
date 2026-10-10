from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .config_validator import DAY_MAP


def calculate_next_execution(booking_execution: str, time_zone: str = "Europe/Madrid") -> datetime:
    """
    Calculate the next execution time based on the booking execution day and time.

    Args:
        booking_execution (str): Execution in the format 'Day HH:MM:SS' or 'now'.
        time_zone (str): The timezone for localization.

    Returns:
        datetime: The next execution time as a timezone-aware datetime.
    """
    tz = ZoneInfo(time_zone)

    # Handle the special case where execution is "now"
    if booking_execution == "now":
        return datetime.now(tz)

    execution_day, execution_time = booking_execution.split()
    now = datetime.now(tz)

    # Map the day name to a day-of-week index
    day_of_week_target = DAY_MAP[execution_day.lower().strip()]
    current_weekday = now.weekday()

    # Parse the execution time
    exec_time = datetime.strptime(execution_time, "%H:%M:%S").time()

    # Determine the next execution date
    if day_of_week_target == current_weekday and now.time() < exec_time:
        next_execution_date = now
    else:
        days_ahead = day_of_week_target - current_weekday
        if days_ahead <= 0:
            days_ahead += 7
        next_execution_date = now + timedelta(days=days_ahead)

    # Combine date and time; zoneinfo picks the UTC offset in effect on that date, so DST changes are handled
    return datetime.combine(next_execution_date.date(), exec_time, tzinfo=tz)


def calculate_class_day(class_day: str, time_zone: str = "Europe/Madrid") -> datetime:
    tz = ZoneInfo(time_zone)
    now = datetime.now(tz)
    target_weekday = DAY_MAP[class_day.lower().strip()]
    days_ahead = target_weekday - now.weekday()
    # Ensure we always book for the upcoming week
    if days_ahead <= 0:
        days_ahead += 7
    return now + timedelta(days=days_ahead)
