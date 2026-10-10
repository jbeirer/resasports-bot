# pysportbot/sportbot.py

import logging

from pandas import DataFrame

from .activities import Activities
from .authenticator import Authenticator
from .bookings import Bookings
from .centres import Centres
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
from .session import Session
from .utils.logger import set_log_level, setup_logger

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

    def __init__(self, log_level: str = "INFO", print_centres: bool = False, time_zone: str = "Europe/Madrid") -> None:
        setup_logger(log_level, timezone=time_zone)
        self._logger = logging.getLogger("SportBot")
        self._logger.info("Initializing SportBot...")
        self._logger.info(f"Log level: {log_level}")
        self._logger.info(f"Time zone: {time_zone}")
        self._time_zone = time_zone
        self._centres = Centres(print_centres)
        self._session: Session = Session()
        self._auth: Authenticator | None = None
        self._activities: Activities | None = None
        self._bookings: Bookings | None = None
        self._df_activities: DataFrame | None = None
        self._is_logged_in: bool = False

    @property
    def activities_manager(self) -> Activities:
        """Get the activities manager, ensuring user is logged in."""
        if not self._is_logged_in or self._auth is None:
            raise NotLoggedInError()

        # Lazy initialization - create only when first needed
        if self._activities is None:
            self._activities = Activities(self._auth, time_zone=self._time_zone)
        return self._activities

    @property
    def bookings_manager(self) -> Bookings:
        """Get the bookings manager, ensuring user is logged in."""
        if not self._is_logged_in or self._auth is None:
            raise NotLoggedInError()

        # Lazy initialization - create only when first needed
        if self._bookings is None:
            self._bookings = Bookings(self._auth)
        return self._bookings

    def set_log_level(self, log_level: str) -> None:
        set_log_level(log_level)
        self._logger.info(f"Log level changed to {log_level}.")

    def login(self, email: str, password: str, centre: str) -> None:
        # Check if the selected centre is valid
        self._centres.check_centre(centre)
        self._logger.info(f"Selected centre: {centre}")

        # Initialize the Authenticator
        self._auth = Authenticator(self._session, centre)

        self._logger.info("Attempting to log in...")
        try:
            # Login to get valid credentials
            self._auth.login(email, password)
            self._is_logged_in = True
            self._logger.info("Login successful!")

            # Fetch activities on first successful login
            self._df_activities = self.activities_manager.fetch()
        except Exception:
            self._is_logged_in = False
            # Clean up on failure
            self._activities = None
            self._bookings = None
            self._auth = None
            self._logger.exception("Login failed.")
            raise

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

        # Find the slot that matches the start time
        matching_slot = slots[slots["start_timestamp"] == start_time]

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
        matching_slot = slots[slots["start_timestamp"] == start_time]
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
