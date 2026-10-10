import json
import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
from pandas import DataFrame

from .authenticator import Authenticator
from .endpoints import Endpoints
from .exceptions import ActivityNotFoundError, APIError

logger = logging.getLogger(__name__)

# The SLOTS endpoint is slow: a multi-day calendar regularly takes over 10 s and occasionally much longer
SLOTS_READ_TIMEOUT = 120


class Activities:
    """Handles activity fetching and slot management."""

    def __init__(self, authenticator: Authenticator, *, time_zone: str = "Europe/Madrid") -> None:
        """Initialize the Activities class."""
        # Session
        self.session = authenticator.session
        # Nubapp credentials
        self.creds = authenticator.creds
        # Headers for requests
        self.headers = authenticator.headers
        # (connect, read) timeout for requests, with a longer read timeout for the slow SLOTS endpoint
        connect_timeout, _ = authenticator.timeout
        self.timeout = (connect_timeout, SLOTS_READ_TIMEOUT)
        # Time zone used to determine "today"
        self.time_zone = time_zone

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

        # Prepare payload for SLOTS endpoint
        payload = {
            "id_application": self.creds.get("id_application"),
            "id_user": self.creds.get("id_user"),
            "start_timestamp": today.isoformat(),
            "end_timestamp": (today + timedelta(days=days_ahead)).isoformat(),
        }
        # Make request to SLOTS endpoint
        response = self.session.post(Endpoints.SLOTS, headers=self.headers, data=payload, timeout=self.timeout)

        if response.status_code != 200:
            logger.error(f"Failed to fetch activities from slots. Status Code: {response.status_code}")
            raise APIError(
                "Failed to fetch activities from slots",
                endpoint=Endpoints.SLOTS,
                status_code=response.status_code,
                body=response.text,
            )

        try:
            data = json.loads(response.content.decode("utf-8"))
            activities = data["data"]["activities_calendar"]

            if not activities:
                logger.warning("No activities found in the response.")
                return pd.DataFrame(columns=["id_activity", "name_activity", "id_category_activity"])

            # Create DataFrame from activities
            df_activities = pd.DataFrame(activities)

            # Drop duplicates based on 'id_activity' and keep first occurrence
            df_activities = df_activities.drop_duplicates(subset=["id_activity"])

            # Select only required columns and reset index
            df_activities = df_activities[["id_activity", "name_activity", "id_category_activity"]].reset_index(
                drop=True
            )

        except json.JSONDecodeError as err:
            logger.error("Invalid JSON response while fetching activities from slots.")
            logger.error(f"Raw response: {response.content.decode('utf-8')}")
            raise APIError(
                "Invalid JSON response while fetching activities from slots",
                endpoint=Endpoints.SLOTS,
                status_code=response.status_code,
                body=response.text,
            ) from err
        except KeyError as err:
            logger.error(f"Missing expected key in response: {err}")
            logger.error(f"Raw response: {response.content.decode('utf-8')}")
            raise APIError(
                f"Missing expected key in response: {err}",
                endpoint=Endpoints.SLOTS,
                status_code=response.status_code,
                body=response.text,
            ) from err
        except Exception as err:
            logger.error(f"Unexpected error while parsing activities: {err}")
            raise APIError(
                f"Unexpected error while parsing activities: {err}",
                endpoint=Endpoints.SLOTS,
                status_code=response.status_code,
                body=response.text,
            ) from err

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
        payload = {
            "id_application": self.creds["id_application"],
            "id_user": self.creds["id_user"],
            "start_timestamp": day,
            "end_timestamp": day,
            "id_category_activity": id_category_activity,
        }
        response = self.session.post(Endpoints.SLOTS, headers=self.headers, data=payload, timeout=self.timeout)

        if response.status_code != 200:
            logger.error(f"Failed to fetch slots. Status Code: {response.status_code}")
            raise APIError(
                "Failed to fetch slots",
                endpoint=Endpoints.SLOTS,
                status_code=response.status_code,
                body=response.text,
            )

        try:
            data = json.loads(response.content.decode("utf-8"))
            slots = data["data"]["activities_calendar"]
        except json.JSONDecodeError as err:
            logger.error("Invalid JSON response while fetching slots.")
            raise APIError(
                "Invalid JSON response while fetching slots",
                endpoint=Endpoints.SLOTS,
                status_code=response.status_code,
                body=response.text,
            ) from err
        except KeyError as err:
            logger.error(f"Missing expected key in response: {err}")
            raise APIError(
                f"Missing expected key in response: {err}",
                endpoint=Endpoints.SLOTS,
                status_code=response.status_code,
                body=response.text,
            ) from err

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
