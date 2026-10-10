from datetime import date, datetime, timedelta

from .config import WeeklyTime


def next_execution(execution: WeeklyTime | None, now: datetime) -> datetime:
    """
    Calculate the next execution time.

    Args:
        execution: The weekly execution day and time, or None to execute now.
        now: The current time as a timezone-aware datetime.

    Returns:
        The next execution time in the time zone of `now`. Today counts if the execution time is still ahead.
    """
    if execution is None:
        return now

    days_ahead = (execution.weekday - now.weekday()) % 7
    if days_ahead == 0 and now.time() >= execution.time:
        days_ahead = 7

    # zoneinfo picks the UTC offset in effect on that date, so DST changes are handled
    return datetime.combine(now.date() + timedelta(days=days_ahead), execution.time, tzinfo=now.tzinfo)


def next_class_date(weekday: int, now: datetime) -> date:
    """
    Calculate the date of the next class on the given weekday (0=Monday).

    The class is always strictly in the future: if today is the class day, the class is next week.
    """
    days_ahead = (weekday - now.weekday()) % 7 or 7
    return now.date() + timedelta(days=days_ahead)
