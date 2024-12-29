import logging

from pandas import DataFrame

from .activities import Activities
from .authenticator import Authenticator
from .bookings import Bookings
from .session import Session
from .utils.errors import ErrorMessages
from .utils.logger import set_log_level, setup_logger


class SportBot:
    """Unified interface for interacting with the booking system."""

    def __init__(self, log_level: str = "INFO") -> None:
        setup_logger(log_level)
        self._logger = logging.getLogger("SportBot")
        self._logger.info("Initializing SportBot...")
        self._session: Session = Session()
        self._auth: Authenticator = Authenticator(self._session)
        self._activities: Activities = Activities(self._session)
        self._bookings: Bookings = Bookings(self._session)
        self._df_activities: DataFrame | None = None

    def set_log_level(self, log_level: str) -> None:
        set_log_level(log_level)
        self._logger.info(f"Log level changed to {log_level}.")

    def login(self, email: str, password: str) -> None:
        self._logger.info("Attempting to log in...")
        self._auth.login(email, password)
        self._df_activities = self._activities.fetch()
        self._logger.info("Login successful!")

    def activities(self, limit: int | None = None) -> DataFrame:
        if self._df_activities is None:
            self._logger.error(ErrorMessages.NO_ACTIVITIES_LOADED)
            raise ValueError(ErrorMessages.NO_ACTIVITIES_LOADED)
        df = self._df_activities[["name_activity", "id_activity"]]
        return df.head(limit) if limit else df

    def daily_slots(self, activity: str, day: str, limit: int | None = None) -> DataFrame:
        if self._df_activities is None:
            self._logger.error(ErrorMessages.NO_ACTIVITIES_LOADED)
            raise ValueError(ErrorMessages.NO_ACTIVITIES_LOADED)
        df = self._activities.daily_slots(self._df_activities, activity, day)
        return df.head(limit) if limit else df

    def book(self, activity: str, start_time: str) -> None:
        if self._df_activities is None:
            self._logger.error(ErrorMessages.NO_ACTIVITIES_LOADED)
            raise ValueError(ErrorMessages.NO_ACTIVITIES_LOADED)
        slots = self.daily_slots(activity, start_time.split(" ")[0])
        matching_slot = slots[slots["start_timestamp"] == start_time]
        if matching_slot.empty:
            error_msg = ErrorMessages.slot_not_found(activity, start_time)
            self._logger.error(error_msg)
            raise IndexError(error_msg)
        self._bookings.book(matching_slot.iloc[0]["id_activity_calendar"])

    def cancel(self, activity: str, start_time: str) -> None:
        if self._df_activities is None:
            self._logger.error(ErrorMessages.NO_ACTIVITIES_LOADED)
            raise ValueError(ErrorMessages.NO_ACTIVITIES_LOADED)
        slots = self.daily_slots(activity, start_time.split(" ")[0])
        matching_slot = slots[slots["start_timestamp"] == start_time]
        if matching_slot.empty:
            error_msg = ErrorMessages.slot_not_found(activity, start_time)
            self._logger.error(error_msg)
            raise IndexError(error_msg)
        self._bookings.cancel(matching_slot.iloc[0]["id_activity_calendar"])
