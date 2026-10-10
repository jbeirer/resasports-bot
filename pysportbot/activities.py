import json
import logging
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from .authenticator import Authenticator
from .client import ApiClient
from .endpoints import Endpoints
from .exceptions import ActivityNotFoundError, APIError
from .models import Activity, Slot

logger = logging.getLogger(__name__)

# The SLOTS endpoint is slow: a multi-day calendar regularly takes over 10 s and occasionally much longer
SLOTS_READ_TIMEOUT = 120


class Activities:
    """Handles activity fetching and slot management."""

    def __init__(self, client: ApiClient, auth: Authenticator, *, time_zone: str = "Europe/Madrid") -> None:
        """Initialize the Activities class."""
        self.client = client
        # Provides id_user and id_application for every request
        self.auth = auth
        # Time zone used to determine "today" and attached to slot times
        self.time_zone = time_zone

    def _calendar(self, start: str, end: str, **extra: Any) -> list[dict[str, Any]]:
        """
        Fetch the activities calendar between two 'YYYY-MM-DD' days, both inclusive.

        Raises:
            APIError: If the request fails or the response has no activities calendar.
        """
        payload = {
            "id_application": self.auth.id_application,
            "id_user": self.auth.id_user,
            "start_timestamp": start,
            "end_timestamp": end,
            **extra,
        }
        # Keep the client's connect timeout, with a longer read timeout for the slow SLOTS endpoint
        timeout = (self.client.timeout[0], SLOTS_READ_TIMEOUT)
        data = self.client.post_json(Endpoints.SLOTS, data=payload, timeout=timeout)
        try:
            calendar: list[dict[str, Any]] = data["data"]["activities_calendar"]
        except (KeyError, TypeError) as err:
            logger.error(f"Missing expected key in response: {err}")
            raise APIError(
                f"Missing expected key in response: {err}", endpoint=Endpoints.SLOTS, body=json.dumps(data)
            ) from err
        # An empty calendar may come as null; anything else must be a list of entries
        if calendar is None:
            return []
        if not isinstance(calendar, list):
            raise APIError("The activities calendar is not a list", endpoint=Endpoints.SLOTS, body=json.dumps(data))
        return calendar

    def fetch(self, days_ahead: int = 7) -> list[Activity]:
        """
        Fetch all available unique activities within a specified time range using SLOTS endpoint.

        Args:
            days_ahead (int): Number of days from now to fetch activities for. Defaults to 7.

        Returns:
            list[Activity]: The unique activities, in calendar order; the first entry of each activity ID wins.

        Raises:
            APIError: If the request fails or the response cannot be parsed.
        """
        logger.info(f"Fetching activities for the next {days_ahead} days. This might take a while...")

        # Date range in the configured time zone; the API expects plain 'YYYY-MM-DD' dates
        today = datetime.now(ZoneInfo(self.time_zone)).date()
        calendar = self._calendar(today.isoformat(), (today + timedelta(days=days_ahead)).isoformat())

        if not calendar:
            logger.warning("No activities found in the response.")
            return []

        # Keep the first occurrence of each activity
        activities: dict[int, Activity] = {}
        for entry in calendar:
            activity = Activity.from_api(entry)
            activities.setdefault(activity.id, activity)

        logger.info(f"Successfully fetched {len(activities)} unique activities.")
        return list(activities.values())

    def daily_slots(self, activities: list[Activity], activity_name: str, day: date | str) -> list[Slot]:
        """
        Fetch available slots for a specific activity on a given day.

        Args:
            activities (list[Activity]): The activities returned by `fetch()`.
            activity_name (str): The name of the activity.
            day (date | str): The day, as a date or in 'YYYY-MM-DD' format.

        Returns:
            list[Slot]: The slots of the activity on that day, in calendar order.

        Raises:
            ValueError: If `day` is not a valid 'YYYY-MM-DD' date.
            ActivityNotFoundError: If the specified activity is not found.
            APIError: If slots cannot be fetched or parsed.
        """
        # Fail fast on a bad date, and send it to the API in canonical 'YYYY-MM-DD' form
        day_str = _to_day(day)

        logger.info(f"Fetching available slots for '{activity_name}' on {day_str}...")

        # Check if the activity exists
        activity = next((a for a in activities if a.name == activity_name), None)
        if activity is None:
            error = ActivityNotFoundError(activity_name, list(dict.fromkeys(a.name for a in activities)))
            logger.error(str(error))
            raise error

        # Fetch slots; the API takes the same 'YYYY-MM-DD' day as start and end
        calendar = self._calendar(day_str, day_str, id_category_activity=activity.category_id)

        if not calendar:
            logger.warning(f"No slots available for activity '{activity_name}' on {day_str}.")
            return []

        logger.debug(f"Daily slots fetched for '{activity_name}' on {day_str}.")

        # The calendar lists the whole category, so only keep slots of the specified activity
        slots = [Slot.from_api(entry, self.time_zone) for entry in calendar]
        slots = [slot for slot in slots if slot.activity_id == activity.id]
        if not slots:
            logger.warning(f"No matching slots found for activity '{activity_name}' on {day_str}.")

        return slots


def _to_day(day: date | str) -> str:
    """
    Return `day` in 'YYYY-MM-DD' form.

    Raises:
        ValueError: If `day` is a string that is not a valid ISO date.
    """
    if isinstance(day, datetime):
        return day.date().isoformat()
    if isinstance(day, date):
        return day.isoformat()
    try:
        return date.fromisoformat(day).isoformat()
    except ValueError as err:
        raise ValueError(f"Invalid day '{day}'. Use the format 'YYYY-MM-DD', e.g. '2025-01-03'.") from err
