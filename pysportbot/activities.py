import json
import logging
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
from pandas import DataFrame

from .authenticator import Authenticator
from .client import ApiClient
from .endpoints import Endpoints
from .exceptions import ActivityNotFoundError, APIError

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
        # Time zone used to determine "today"
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
        return calendar

    def fetch(self, days_ahead: int = 7) -> DataFrame:
        """
        Fetch all available unique activities within a specified time range using SLOTS endpoint.

        Args:
            days_ahead (int): Number of days from now to fetch activities for. Defaults to 7.

        Returns:
            DataFrame: A DataFrame containing unique activity details with columns:
                    ['id_activity', 'name_activity', 'id_category_activity']

        Raises:
            APIError: If the request fails or the response cannot be parsed.
        """
        logger.info(f"Fetching activities for the next {days_ahead} days. This might take a while...")

        # Date range in the configured time zone; the API expects plain 'YYYY-MM-DD' dates
        today = datetime.now(ZoneInfo(self.time_zone)).date()
        activities = self._calendar(today.isoformat(), (today + timedelta(days=days_ahead)).isoformat())

        if not activities:
            logger.warning("No activities found in the response.")
            return pd.DataFrame(columns=["id_activity", "name_activity", "id_category_activity"])

        try:
            # Keep the first occurrence of each activity, and only the required columns
            df_activities = pd.DataFrame(activities).drop_duplicates(subset=["id_activity"])
            df_activities = df_activities[["id_activity", "name_activity", "id_category_activity"]].reset_index(
                drop=True
            )
        except Exception as err:
            logger.error(f"Unexpected error while parsing activities: {err}")
            raise APIError(f"Unexpected error while parsing activities: {err}", endpoint=Endpoints.SLOTS) from err

        logger.info(f"Successfully fetched {len(df_activities)} unique activities.")
        return df_activities

    def daily_slots(self, df_activities: DataFrame, activity_name: str, day: str) -> DataFrame:
        """
        Fetch available slots for a specific activity on a given day.

        Args:
            df_activities (DataFrame): The DataFrame of activities.
            activity_name (str): The name of the activity.
            day (str): The day in 'YYYY-MM-DD' format.

        Returns:
            DataFrame: A DataFrame containing available slots.

        Raises:
            ValueError: If `day` is not a valid 'YYYY-MM-DD' date.
            ActivityNotFoundError: If the specified activity is not found.
            APIError: If slots cannot be fetched.
        """
        # Fail fast on a bad date, and send it to the API in canonical 'YYYY-MM-DD' form
        try:
            day = date.fromisoformat(day).isoformat()
        except ValueError as err:
            raise ValueError(f"Invalid day '{day}'. Use the format 'YYYY-MM-DD', e.g. '2025-01-03'.") from err

        logger.info(f"Fetching available slots for '{activity_name}' on {day}...")

        # Check if the activity exists
        activity_match = df_activities[df_activities["name_activity"] == activity_name]
        if activity_match.empty:
            error = ActivityNotFoundError(activity_name, df_activities["name_activity"].unique().tolist())
            logger.error(str(error))
            raise error

        activity = activity_match.iloc[0]
        id_activity = activity["id_activity"]
        id_category_activity = activity["id_category_activity"]

        # Fetch slots; the API takes the same 'YYYY-MM-DD' day as start and end
        slots = self._calendar(day, day, id_category_activity=id_category_activity)

        if not slots:
            logger.warning(f"No slots available for activity '{activity_name}' on {day}.")
            return DataFrame()

        logger.debug(f"Daily slots fetched for '{activity_name}' on {day}.")

        # Filter desired columns
        columns = [
            "name_activity",
            "id_activity_calendar",
            "id_activity",
            "id_category_activity",
            "start_timestamp",
            "end_timestamp",
            "n_inscribed",
            "n_capacity",
            "n_waiting_list",
            "cancelled",
            "trainer_name",
        ]
        df_slots = pd.DataFrame(slots)

        # Ensure only desired columns are selected without KeyError
        df_slots = df_slots.loc[:, df_slots.columns.intersection(columns)]

        # Only select rows of the specified activity
        df_slots = df_slots[df_slots.id_activity == int(id_activity)]
        if df_slots.empty:
            logger.warning(f"No matching slots found for activity '{activity_name}' on {day}.")
            return DataFrame()

        return df_slots
