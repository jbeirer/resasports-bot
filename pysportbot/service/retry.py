import math
from dataclasses import dataclass
from typing import Literal

import requests

from pysportbot.exceptions import (
    APIError,
    BookingError,
    SlotAlreadyBookedError,
    SlotFullError,
    SlotNotBookableYetError,
    SlotNotFoundError,
    SlotUnavailableError,
)

Action = Literal["poll", "retry", "stop"]


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """
    When to try booking a class again, see `classify()`.

    Attributes:
        retry_attempts: The maximum number of attempts that fail with an error that may be temporary, e.g. a
            network error. Polls do not count.
        retry_delay: Seconds to wait after such an error.
        poll_interval: Seconds between attempts while the slot is not bookable yet or not found.
        poll_window: Seconds after the execution time to keep polling.

    Raises:
        ValueError: If retry_attempts < 1, poll_interval <= 0, or retry_delay or poll_window is negative.
    """

    retry_attempts: int = 3
    retry_delay: float = 5.0
    poll_interval: float = 0.5
    poll_window: float = 60.0

    def __post_init__(self) -> None:
        if self.retry_attempts < 1:
            raise ValueError(f"retry_attempts must be at least 1, got {self.retry_attempts}.")
        for name in ("retry_delay", "poll_window"):
            value = getattr(self, name)
            if not (math.isfinite(value) and value >= 0):
                raise ValueError(f"{name} must be a non-negative number of seconds, got {value}.")
        if not (math.isfinite(self.poll_interval) and self.poll_interval > 0):
            raise ValueError(f"poll_interval must be a positive number of seconds, got {self.poll_interval}.")


def classify(error: Exception) -> Action:
    """
    Decide what to do after a failed booking attempt.

    Returns:
        "poll" if the booking window may not have opened yet: try again after the poll interval, until the poll
        window ends. "retry" if the error may be temporary: try again after the retry delay, up to the retry attempts.
        "stop" if trying again cannot help.
    """
    # The API may answer "not available" until the window opens, and the calendar may be published late
    if isinstance(error, SlotNotBookableYetError | SlotUnavailableError | SlotNotFoundError):
        return "poll"
    if isinstance(error, SlotAlreadyBookedError | SlotFullError):
        return "stop"
    # A plain BookingError has an unknown error code
    if isinstance(error, APIError | BookingError | requests.RequestException):
        return "retry"
    return "stop"
