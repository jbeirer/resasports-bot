from datetime import date, datetime, timedelta

from .config import WeeklyTime


def next_execution(execution: WeeklyTime | None, now: datetime) -> datetime:
    """
    Calculate the next execution time.

    Args:
        execution: The weekly execution day and time, or None to execute now.
        now: The current time as a timezone-aware datetime.

    Returns:
        The next execution time in the time zone of `now`. Today counts if the execution time is still ahead. A time
        that occurs twice when clocks go back resolves to the next occurrence that is still ahead.
    """
    if execution is None:
        return now

    day = now.date() + timedelta(days=(execution.weekday - now.weekday()) % 7)
    # zoneinfo picks the UTC offset in effect on that date, so DST changes are handled. Compare instants, not wall
    # times, and try both readings (fold) of a wall time that is ambiguous because clocks go back
    candidates = [datetime.combine(day, execution.time.replace(fold=fold), tzinfo=now.tzinfo) for fold in (0, 1)]
    ahead = [c for c in candidates if c.timestamp() > now.timestamp()]
    if ahead:
        return min(ahead, key=datetime.timestamp)
    return datetime.combine(day + timedelta(days=7), execution.time, tzinfo=now.tzinfo)


def next_class_date(weekday: int, now: datetime) -> date:
    """
    Calculate the date of the next class on the given weekday (0=Monday).

    The class is always strictly in the future: if today is the class day, the class is next week.
    """
    days_ahead = (weekday - now.weekday()) % 7 or 7
    return now.date() + timedelta(days=days_ahead)
