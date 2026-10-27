from typing import ClassVar


class SportBotError(Exception):
    """Base class for every error raised by pysportbot."""


class APIError(SportBotError):
    """The API returned an unexpected HTTP status, a non-JSON body or a body with missing fields."""

    def __init__(self, reason: str, *, endpoint: str, status_code: int | None = None, body: str = "") -> None:
        self.reason = reason
        self.endpoint = str(endpoint)
        self.status_code = status_code
        self.body = body[:200]
        status = f", HTTP {status_code}" if status_code is not None else ""
        super().__init__(f"{reason} ({self.endpoint}{status}).")


class AuthenticationError(SportBotError):
    """Logging in failed, because of bad credentials or an unexpected authentication response."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"Login failed: {reason}. Please check your credentials and try again.")


class NotLoggedInError(SportBotError):
    """The method requires a successful login first."""

    def __init__(self) -> None:
        super().__init__("You must log in first.")


class ConfigError(SportBotError):
    """The service configuration is invalid."""


class CentreNotFoundError(SportBotError):
    """The account is not registered at the centre."""

    def __init__(self, centre: str, available: list[str] | None = None) -> None:
        self.centre = centre
        # Slugs of the centres the account is registered at
        self.available = available or []
        message = f"Centre '{centre}' not found among the centres of this account"
        super().__init__(f"{message}: {', '.join(self.available)}." if self.available else f"{message}.")


class ActivityNotFoundError(SportBotError):
    """The activity is not offered by the centre."""

    def __init__(self, activity: str, available: list[str]) -> None:
        self.activity = activity
        self.available = available
        super().__init__(
            f"No activity found with the name '{activity}'. Available activities are: {', '.join(available)}."
        )


class SlotNotFoundError(SportBotError):
    """No slot of the activity starts at the requested time."""

    def __init__(self, activity: str, start: str) -> None:
        self.activity = activity
        self.start = start
        super().__init__(f"No slot found for activity '{activity}' at {start}.")


class BookingError(SportBotError):
    """Booking a slot failed. Raised directly for API error codes without a dedicated subclass."""

    _summary: ClassVar[str] = "Booking slot {slot_id} failed"

    def __init__(self, slot_id: str, code: int | None = None) -> None:
        self.slot_id = slot_id
        self.code = code
        suffix = f" (error code {code})" if code is not None else ""
        super().__init__(f"{self._summary.format(slot_id=slot_id)}{suffix}.")


class SlotAlreadyBookedError(BookingError):
    """The slot is already booked by the user (API error code 5)."""

    _summary = "Slot {slot_id} is already booked"


class SlotUnavailableError(BookingError):
    """The slot is not available for booking (API error code 6)."""

    _summary = "Slot {slot_id} is not available"


class SlotNotBookableYetError(BookingError):
    """The booking window of the slot has not opened yet (API error code 28)."""

    _summary = "Slot {slot_id} is not bookable yet"


class SlotFullError(BookingError):
    """The slot has no places left. Detected before any booking request is sent."""

    _summary = "Slot {slot_id} is full and cannot be booked"


class CancellationError(SportBotError):
    """Cancelling a slot failed, e.g. because the slot was not booked."""

    def __init__(self, slot_id: str) -> None:
        self.slot_id = slot_id
        super().__init__(f"Cancellation of slot {slot_id} failed. The slot may not have been booked.")
