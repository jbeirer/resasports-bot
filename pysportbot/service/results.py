import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from pysportbot.models import Slot

from .config import WEEKDAY_NAMES, ClassSpec

logger = logging.getLogger(__name__)


class BookingStatus(StrEnum):
    """The outcome of booking one class."""

    BOOKED = "booked"
    ALREADY_BOOKED = "already booked"
    FULL = "full"
    NOT_FOUND = "not found"
    FAILED = "failed"
    DRY_RUN = "dry run"


_OK_STATUSES = frozenset({BookingStatus.BOOKED, BookingStatus.ALREADY_BOOKED, BookingStatus.DRY_RUN})


@dataclass(frozen=True, slots=True)
class BookingResult:
    """
    The outcome of booking one class.

    Attributes:
        spec: The class from the configuration.
        start: The time zone aware start time of the class that was booked, i.e. its next occurrence.
        status: The outcome.
        attempts: The number of booking attempts, polls included.
        slot: The slot, if it was found.
        error: The last error, if the class was not booked.
    """

    spec: ClassSpec
    start: datetime
    status: BookingStatus
    attempts: int
    slot: Slot | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        """Whether the class is booked, or would be in a dry run."""
        return self.status in _OK_STATUSES


def format_time(when: datetime) -> str:
    """Format the time of day as "HH:MM", with seconds only if there are any."""
    return when.strftime("%H:%M:%S" if when.second else "%H:%M")


def describe(activity: str, start: datetime) -> str:
    """Describe a class as e.g. "'Yoga' on Monday 2026-01-12 at 18:00"."""
    return f"'{activity}' on {WEEKDAY_NAMES[start.weekday()]} {start:%Y-%m-%d} at {format_time(start)}"


def log_summary(results: Sequence[BookingResult]) -> None:
    """Log a table of the results: activity, day, time, status and attempts."""
    headers = ("ACTIVITY", "DAY", "TIME", "STATUS", "ATTEMPTS")
    rows = [
        (
            r.spec.activity,
            f"{WEEKDAY_NAMES[r.start.weekday()]} {r.start:%Y-%m-%d}",
            format_time(r.start),
            str(r.status),
            str(r.attempts),
        )
        for r in results
    ]
    widths = [max([len(header), *(len(row[i]) for row in rows)]) for i, header in enumerate(headers)]
    logger.info("Booking summary:")
    for line in (headers, *rows):
        logger.info("  ".join(cell.ljust(width) for cell, width in zip(line, widths, strict=True)).rstrip())
