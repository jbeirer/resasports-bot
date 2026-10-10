# pysportbot/sportbot.py

import logging

from pandas import DataFrame

from .activities import Activities
from .authenticator import Authenticator
from .bookings import Bookings
from .centres import Centres
from .client import ApiClient
from .exceptions import (
    ActivityNotFoundError,
    APIError,
    AuthenticationError,
    BookingError,
    CancellationError,
    CentreNotFoundError,
    ConfigError,
    NotLoggedInError,
    SlotAlreadyBookedError,
    SlotFullError,
    SlotNotBookableYetError,
    SlotNotFoundError,
    SlotUnavailableError,
    SportBotError,
)
from .logging_utils import configure_logging, set_log_level

# Silence pysportbot by default; SportBot() or configure_logging() opt into output
logging.getLogger(__name__).addHandler(logging.NullHandler())

__all__ = [
    "APIError",
    "ActivityNotFoundError",
    "AuthenticationError",
    "BookingError",
    "CancellationError",
    "CentreNotFoundError",
    "ConfigError",
    "NotLoggedInError",
    "SlotAlreadyBookedError",
    "SlotFullError",
    "SlotNotBookableYetError",
    "SlotNotFoundError",
    "SlotUnavailableError",
    "SportBot",
    "SportBotError",
]


class SportBot:
    """Unified interface for interacting with the booking system."""

    def __init__(
        self, log_level: str | None = "INFO", print_centres: bool = False, time_zone: str = "Europe/Madrid"
    ) -> None:
        # log_level=None leaves logging to the application: records propagate to its handlers as configured
        if log_level is not None:
            configure_logging(log_level, timezone=time_zone)
        self._logger = logging.getLogger(__name__)
        self._logger.info("Initializing SportBot...")
        if log_level is not None:
            self._logger.info(f"Log level: {log_level}")
        self._logger.info(f"Time zone: {time_zone}")
        self._time_zone = time_zone
        self._client = ApiClient()
        self._centres = Centres(self._client, print_centres)
        self._authenticator = Authenticator(self._client)
        self._activities: Activities | None = None
        self._bookings: Bookings | None = None
        self._df_activities: DataFrame | None = None
        self._is_logged_in: bool = False
        # (email, password, centre) of the last successful login, for ensure_logged_in()
        self._credentials: tuple[str, str, str] | None = None

    @property
    def activities_manager(self) -> Activities:
        """Get the activities manager, ensuring user is logged in."""
        if not self._is_logged_in:
            raise NotLoggedInError()

        # Lazy initialization - create only when first needed
        if self._activities is None:
            self._activities = Activities(self._client, self._authenticator, time_zone=self._time_zone)
        return self._activities

    @property
    def bookings_manager(self) -> Bookings:
        """Get the bookings manager, ensuring user is logged in."""
        if not self._is_logged_in:
            raise NotLoggedInError()

        # Lazy initialization - create only when first needed
        if self._bookings is None:
            self._bookings = Bookings(self._client, self._authenticator)
        return self._bookings

    def set_log_level(self, log_level: str) -> None:
        set_log_level(log_level)
        self._logger.info(f"Log level changed to {log_level}.")

    def login(self, email: str, password: str, centre: str) -> None:
        # Check if the selected centre is valid
        self._centres.check_centre(centre)
        self._logger.info(f"Selected centre: {centre}")

        self._logger.info("Attempting to log in...")
        try:
            # Login to get valid credentials
            self._authenticator.login(email, password)
            self._is_logged_in = True
            self._logger.info("Login successful!")

            # Fetch activities on first successful login
            self._df_activities = self.activities_manager.fetch()
        except Exception:
            # Clean up on failure
            self._is_logged_in = False
            self._df_activities = None
            self._logger.exception("Login failed.")
            raise
        self._credentials = (email, password, centre)

    def ensure_logged_in(self) -> None:
        """
        Re-login with the stored credentials if the current session is no longer valid.

        Long-running programs can call this before time-critical requests, because the session may expire some time
        after `login()`. It costs one request when the session is still valid. Otherwise it calls `login()` again with
        the email, password and centre of the last successful login.

        Raises:
            NotLoggedInError: If `login()` has never succeeded.
            AuthenticationError: If the re-login fails.
            APIError: If fetching the activities after the re-login fails.
        """
        if self._credentials is None:
            raise NotLoggedInError()

        if self._is_logged_in and self._authenticator.is_session_valid():
            self._logger.info("Session still valid. Skipping re-authentication.")
            return

        self._logger.info("Session is no longer valid. Logging in again...")
        self.login(*self._credentials)

    def is_logged_in(self) -> bool:
        """Returns the login status."""
        return self._is_logged_in

    def activities(self, limit: int | None = None) -> DataFrame:
        if self._df_activities is None:
            raise NotLoggedInError()

        df = self._df_activities[["name_activity", "id_activity"]]
        return df.head(limit) if limit else df

    def daily_slots(self, activity: str, day: str, limit: int | None = None) -> DataFrame:
        if self._df_activities is None:
            raise NotLoggedInError()

        df = self.activities_manager.daily_slots(self._df_activities, activity, day)
        return df.head(limit) if limit else df

    def book(self, activity: str, start_time: str) -> None:
        if self._df_activities is None:
            raise NotLoggedInError()

        # Fetch the daily slots for the activity
        slots = self.daily_slots(activity, start_time.split(" ")[0])

        # Find the slot that matches the start time; without slots, daily_slots returns a DataFrame without columns
        matching_slot = slots[slots["start_timestamp"] == start_time] if not slots.empty else slots

        # If no matching slot is found, raise an error
        if matching_slot.empty:
            error = SlotNotFoundError(activity, start_time)
            self._logger.error(str(error))
            raise error

        # The targeted slot
        target_slot = matching_slot.iloc[0]
        # The unique slot ID
        slot_id = target_slot["id_activity_calendar"]
        # The total member capacity of the slot
        slot_capacity = target_slot["n_capacity"]
        # The number of members already inscribed in the slot
        slot_n_inscribed = target_slot["n_inscribed"]
        # Log slot capacity
        self._logger.info(
            f"Attempting to book class '{activity}' on {start_time} with ID {slot_id} (Slot capacity: {slot_n_inscribed}/{slot_capacity})"
        )

        # Check if the slot is already booked out
        if slot_n_inscribed >= slot_capacity:
            self._logger.error(f"Activity '{activity}' on {start_time} with ID {slot_id} is booked out...")
            raise SlotFullError(slot_id)

        # Attempt to book the slot
        try:
            self.bookings_manager.book(slot_id)
            self._logger.info(f"Successfully booked class '{activity}' on {start_time}")
        except SportBotError:
            self._logger.error(f"Failed to book class '{activity}' on {start_time}")
            raise

    def cancel(self, activity: str, start_time: str) -> None:
        self._logger.debug(f"Attempting to cancel class '{activity}' on {start_time}")

        if self._df_activities is None:
            raise NotLoggedInError()

        slots = self.daily_slots(activity, start_time.split(" ")[0])
        matching_slot = slots[slots["start_timestamp"] == start_time] if not slots.empty else slots
        if matching_slot.empty:
            error = SlotNotFoundError(activity, start_time)
            self._logger.error(str(error))
            raise error

        slot_id = matching_slot.iloc[0]["id_activity_calendar"]
        try:
            self.bookings_manager.cancel(slot_id)
            self._logger.info(f"Successfully cancelled class '{activity}' on {start_time}")
        except SportBotError:
            self._logger.error(f"Failed to cancel class '{activity}' on {start_time}")
            raise
