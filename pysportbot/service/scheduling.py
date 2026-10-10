import logging
import time
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta

from .config import WeeklyTime

logger = logging.getLogger(__name__)

# Longest single sleep while waiting, so that long waits log their progress
MAX_SLEEP = 30.0

Clock = Callable[[], float]
Sleep = Callable[[float], None]


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


def wait_until(deadline: datetime, *, clock: Clock | None = None, sleep: Sleep | None = None) -> float:
    """
    Sleep until a wall-clock time.

    The deadline is converted to the monotonic clock once, so wall-clock adjustments during the wait do not move it.
    Long waits sleep in chunks of at most 30 seconds and log the remaining time at DEBUG.

    Args:
        deadline: A time zone aware time. A time in the past returns at once.
        clock: The monotonic clock in seconds [default: time.monotonic].
        sleep: The sleep function [default: time.sleep].

    Returns:
        The deadline on the `clock` scale, to time later steps from it.
    """
    clock = clock or time.monotonic
    sleep = sleep or time.sleep
    target = clock() + deadline.timestamp() - datetime.now(UTC).timestamp()
    while (remaining := target - clock()) > 0:
        if remaining > MAX_SLEEP:
            logger.debug(f"{remaining:.1f} seconds left until {deadline:%Y-%m-%d %H:%M:%S}.")
        sleep(min(remaining, MAX_SLEEP))
    return target
