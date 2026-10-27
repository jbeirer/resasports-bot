import logging
from datetime import date, datetime
from zoneinfo import ZoneInfo

from .activities import Activities
from .authenticator import Authenticator
from .bookings import Bookings
from .centres import Centres
from .client import ApiClient
from .exceptions import NotLoggedInError, SlotFullError, SlotNotFoundError, SportBotError
from .logging_utils import configure_logging, set_log_level
from .models import TIMESTAMP_FORMAT, Activity, Centre, Slot

logger = logging.getLogger(__name__)

# Accepted string forms of a slot start time
_START_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M")


def _parse_start(start: str) -> datetime:
    """
    Parse a 'YYYY-MM-DD HH:MM[:SS]' string into a naive datetime.

    Raises:
        ValueError: If the string has neither format.
    """
    for fmt in _START_FORMATS:
        try:
            return datetime.strptime(start.strip(), fmt)
        except ValueError:
            continue
    raise ValueError(f"Invalid start '{start}'. Use the format 'YYYY-MM-DD HH:MM[:SS]', e.g. '2025-01-03 18:00'.")


class SportBot:
    """
    Unified interface for interacting with the booking system.

    Creating a bot sends no requests. The centres are fetched on first use, and everything else needs `login()`.

    Args:
        log_level: The level of the logs printed to stderr, e.g. "INFO". None leaves logging to the application.
        time_zone: The time zone of the centre. Slot times are in this zone, and start times without a time zone
            are taken to be in it.
    """

    def __init__(self, log_level: str | None = "INFO", time_zone: str = "Europe/Madrid") -> None:
        # log_level=None leaves logging to the application: records propagate to its handlers as configured
        if log_level is not None:
            configure_logging(log_level, timezone=time_zone)
        logger.info("Initializing SportBot...")
        if log_level is not None:
            logger.info(f"Log level: {log_level}")
        logger.info(f"Time zone: {time_zone}")
        self._tz = ZoneInfo(time_zone)
        self._client = ApiClient()
        self._centres = Centres(self._client)
        self._authenticator = Authenticator(self._client)
        self._activities_manager = Activities(self._client, self._authenticator, time_zone=time_zone)
        self._bookings_manager = Bookings(self._client, self._authenticator)
        # Unique activities fetched by login(); None while logged out
        self._activities: list[Activity] | None = None
        self._is_logged_in: bool = False
        # (email, password, centre) of the last successful login, for ensure_logged_in()
        self._credentials: tuple[str, str, str] | None = None

    def set_log_level(self, level: str) -> None:
        """
        Change the level of pysportbot's logs.

        Args:
            level: The new level, e.g. "DEBUG".

        Raises:
            ValueError: If the level name is unknown.
        """
        set_log_level(level)
        logger.info(f"Log level changed to {level}.")

    def centres(self, search: str | None = None) -> list[Centre]:
        """
        List the centres that use Resasports. Needs no login.

        The centres are fetched on the first call and then cached.

        Args:
            search: Only return centres whose slug, name or town contains this text, ignoring case.

        Raises:
            APIError: If the centres cannot be fetched.
        """
        return self._centres.search(search)

    def login(self, email: str, password: str, centre: str) -> None:
        """
        Log in and fetch the activities of the centre.

        Args:
            email: The account email.
            password: The account password.
            centre: The slug of the centre, see `centres()`.

        Raises:
            CentreNotFoundError: If the account is not registered at the centre.
            AuthenticationError: If logging in fails.
            APIError: If the activities cannot be fetched.
        """
        logger.info(f"Attempting to log in to {centre}...")
        try:
            # Login to get valid credentials
            self._authenticator.login(email, password, centre)
            self._is_logged_in = True
            logger.info("Login successful!")

            # Fetch activities on first successful login
            self._activities = self._activities_manager.fetch()
        except Exception:
            self._logout()
            logger.exception("Login failed.")
            raise
        self._credentials = (email, password, centre)

    def _logout(self) -> None:
        """Reset the bot and the authenticator together, so a failed (re-)login leaves no usable token behind."""
        self._is_logged_in = False
        self._activities = None
        self._authenticator.reset()

    def ensure_logged_in(self) -> None:
        """
        Re-login with the stored credentials if the current session is no longer valid.

        Long-running programs can call this before time-critical requests, because the session may expire some time
        after `login()`. It costs one request when the session is still valid. Otherwise it logs in again with the
        email, password and centre of the last successful `login()`, which the bot keeps in memory for this purpose.
        A re-login keeps the activities fetched by `login()`, so it does not wait for the slow activities request.

        Raises:
            NotLoggedInError: If `login()` has never succeeded.
            AuthenticationError: If the re-login fails.
            APIError: If fetching the activities fails, when an earlier login failed and a full login is needed.
        """
        if self._credentials is None:
            raise NotLoggedInError()

        if not self._is_logged_in:
            # An earlier (re-)login failed, so the activities must be fetched again too
            logger.info("Not logged in. Logging in again...")
            self.login(*self._credentials)
            return

        if self._authenticator.is_session_valid():
            logger.info("Session still valid. Skipping re-authentication.")
            return

        logger.info("Session is no longer valid. Logging in again...")
        try:
            self._authenticator.login(*self._credentials)
        except Exception:
            self._logout()
            raise

    def is_logged_in(self) -> bool:
        """Whether the bot is logged in."""
        return self._is_logged_in

    def _require_activities(self) -> list[Activity]:
        if self._activities is None:
            raise NotLoggedInError()
        return self._activities

    def activities(self) -> list[Activity]:
        """
        List the activities of the centre, as fetched by `login()`.

        Raises:
            NotLoggedInError: If not logged in.
        """
        return list(self._require_activities())

    def daily_slots(self, activity: str, day: date | str) -> list[Slot]:
        """
        List the slots of an activity on one day.

        Args:
            activity: The activity name, see `activities()`.
            day: The day, as a date or a 'YYYY-MM-DD' string.

        Raises:
            NotLoggedInError: If not logged in.
            ValueError: If `day` is not a valid 'YYYY-MM-DD' date.
            ActivityNotFoundError: If the activity does not exist.
            APIError: If the slots cannot be fetched.
        """
        return self._activities_manager.daily_slots(self._require_activities(), activity, day)

    def _to_datetime(self, start: datetime | str) -> datetime:
        """Return `start` as an aware datetime in the bot's time zone; strings and naive datetimes are taken to be in it."""
        when = _parse_start(start) if isinstance(start, str) else start
        return when.replace(tzinfo=self._tz) if when.tzinfo is None else when.astimezone(self._tz)

    def find_slot(self, activity: str, start: datetime | str) -> Slot:
        """
        Find the slot of an activity that starts at a given time.

        Args:
            activity: The activity name, see `activities()`.
            start: The start time: a time zone aware datetime, or a naive datetime or a 'YYYY-MM-DD HH:MM[:SS]'
                string in the bot's time zone.

        Raises:
            NotLoggedInError: If not logged in.
            ValueError: If `start` is a string in neither format.
            ActivityNotFoundError: If the activity does not exist.
            SlotNotFoundError: If no slot of the activity starts at that time.
            APIError: If the slots cannot be fetched.
        """
        activities = self._require_activities()
        when = self._to_datetime(start)

        slots = self._activities_manager.daily_slots(activities, activity, when.date())
        slot = next((s for s in slots if s.start == when), None)
        if slot is None:
            error = SlotNotFoundError(activity, when.strftime(TIMESTAMP_FORMAT))
            logger.debug(str(error))
            raise error
        return slot

    def book(self, activity: str, start: datetime | str) -> Slot:
        """
        Book the slot of an activity that starts at a given time.

        Args:
            activity: The activity name, see `activities()`.
            start: The start time, see `find_slot()`.

        Returns:
            The booked slot, as listed before the booking.

        Raises:
            SlotFullError: If the slot has no places left. No booking request is sent.
            SlotAlreadyBookedError: If the slot is already booked.
            SlotUnavailableError: If the slot is not available.
            SlotNotBookableYetError: If the booking window has not opened yet.
            BookingError: If the booking fails for another reason.
            SlotNotFoundError: If no slot of the activity starts at that time.
            NotLoggedInError, ValueError, ActivityNotFoundError, APIError: See `find_slot()`.
        """
        slot = self.find_slot(activity, start)
        when = slot.start.strftime(TIMESTAMP_FORMAT)
        logger.info(
            f"Attempting to book class '{activity}' on {when} with ID {slot.id} (Slot capacity: {slot.inscribed}/{slot.capacity})"
        )

        # The slot was just fetched, so its counts are fresh enough to skip a booking request that cannot succeed
        if slot.is_full:
            logger.debug(f"Activity '{activity}' on {when} with ID {slot.id} is booked out...")
            raise SlotFullError(str(slot.id))

        return self.book_slot(slot)

    def book_slot(self, slot: Slot) -> Slot:
        """
        Book a slot found earlier, e.g. by `find_slot()` or `daily_slots()`, with a single request.

        Unlike `book()`, this does not look the slot up again, so it suits time-critical bookings where the slot is
        found ahead of time. It does not check whether the slot is full either, because its counts may be stale by
        now: the API decides.

        Args:
            slot: The slot to book.

        Returns:
            The given slot.

        Raises:
            NotLoggedInError: If not logged in.
            SlotAlreadyBookedError: If the slot is already booked.
            SlotUnavailableError: If the slot is not available.
            SlotNotBookableYetError: If the booking window has not opened yet.
            BookingError: If the booking fails for another reason.
            APIError: If the response is not a valid booking response.
        """
        if not self._is_logged_in:
            raise NotLoggedInError()

        when = slot.start.strftime(TIMESTAMP_FORMAT)
        try:
            self._bookings_manager.book(str(slot.id))
        except SportBotError:
            # The exception reports the failure; the booking service may try many times before the window opens
            logger.debug(f"Failed to book class '{slot.activity_name}' on {when}")
            raise
        logger.info(f"Successfully booked class '{slot.activity_name}' on {when}")
        return slot

    def cancel(self, activity: str, start: datetime | str) -> Slot:
        """
        Cancel the booking of the slot of an activity that starts at a given time.

        Args:
            activity: The activity name, see `activities()`.
            start: The start time, see `find_slot()`.

        Returns:
            The cancelled slot, as listed before the cancellation.

        Raises:
            CancellationError: If the cancellation fails, e.g. because the slot was not booked.
            SlotNotFoundError: If no slot of the activity starts at that time.
            NotLoggedInError, ValueError, ActivityNotFoundError, APIError: See `find_slot()`.
        """
        logger.debug(f"Attempting to cancel class '{activity}' on {start}")

        slot = self.find_slot(activity, start)
        when = slot.start.strftime(TIMESTAMP_FORMAT)
        try:
            self._bookings_manager.cancel(str(slot.id))
        except SportBotError:
            logger.error(f"Failed to cancel class '{activity}' on {when}")
            raise
        logger.info(f"Successfully cancelled class '{activity}' on {when}")
        return slot
