import json
from datetime import datetime, timedelta

import pandas as pd
from pandas import DataFrame

from .authenticator import Authenticator
from .endpoints import Endpoints
from .utils.errors import ErrorMessages
from .utils.logger import get_logger
from .utils.time import get_day_bounds

logger = get_logger(__name__)


class Activities:
    """Handles activity fetching and slot management."""

    def __init__(self, authenticator: Authenticator) -> None:
        """Initialize the Activities class."""
        # Session
        self.session = authenticator.session
        # Nubapp credentials
        self.creds = authenticator.creds
        # Headers for requests
        self.headers = authenticator.headers

    def fetch(self, days_ahead: int = 7) -> DataFrame:
        """
        Fetch all available unique activities within a specified time range using SLOTS endpoint.

        Args:
            days_ahead (int): Number of days from now to fetch activities for. Defaults to 7.

        Returns:
            DataFrame: A DataFrame containing unique activity details with columns:
                    ['id_activity', 'name_activity', 'id_category_activity']

        Raises:
            RuntimeError: If the request fails or JSON parsing fails.
        """
        logger.info(f"Fetching activities for the next {days_ahead} days. This might take a while...")

        # Calculate date range
        start_date = datetime.now().strftime("%Y-%m-%d")
        end_date = (datetime.now() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

        # Get day bounds for the date range
        start_timestamp, _ = get_day_bounds(start_date)
        _, end_timestamp = get_day_bounds(end_date)

        # Prepare payload for SLOTS endpoint
        payload = {
            "id_application": self.creds.get("id_application"),
            "id_user": self.creds.get("id_user"),
            "start_timestamp": start_timestamp,
            "end_timestamp": end_timestamp,
        }
        # Make request to SLOTS endpoint
        response = self.session.post(Endpoints.SLOTS, headers=self.headers, data=payload)

        if response.status_code != 200:
            error_msg = ErrorMessages.failed_fetch("activities from slots")
            logger.error(f"{error_msg} Status Code: {response.status_code}")
            raise RuntimeError(error_msg)

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
            error_msg = "Invalid JSON response while fetching activities from slots."
            logger.error(error_msg)
            logger.error(f"Raw response: {response.content.decode('utf-8')}")
            raise RuntimeError(error_msg) from err
        except KeyError as err:
            error_msg = f"Missing expected key in response: {err}"
            logger.error(error_msg)
            logger.error(f"Raw response: {response.content.decode('utf-8')}")
            raise RuntimeError(error_msg) from err
        except Exception as err:
            error_msg = f"Unexpected error while parsing activities: {err}"
        else:
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
            ValueError: If the specified activity is not found.
            RuntimeError: If slots cannot be fetched.
        """
        logger.info(f"Fetching available slots for '{activity_name}' on {day}...")

        # Check if the activity exists
        activity_match = df_activities[df_activities["name_activity"] == activity_name]
        if activity_match.empty:
            error_msg = ErrorMessages.activity_not_found(
                activity_name, df_activities["name_activity"].unique().tolist()
            )
            logger.error(error_msg)
            raise ValueError(error_msg)

        activity = activity_match.iloc[0]
        id_activity = activity["id_activity"]
        id_category_activity = activity["id_category_activity"]

        # Get Unix timestamp bounds for the day
        day_bounds = get_day_bounds(day)

        # Fetch slots
        payload = {
            "id_application": self.creds["id_application"],
            "id_user": self.creds["id_user"],
            "start_timestamp": day_bounds[0],
            "end_timestamp": day_bounds[1],
            "id_category_activity": id_category_activity,
        }
        response = self.session.post(Endpoints.SLOTS, headers=self.headers, data=payload)

        if response.status_code != 200:
            error_msg = ErrorMessages.failed_fetch("slots")
            logger.error(error_msg)
            raise RuntimeError(error_msg)

        try:
            data = json.loads(response.content.decode("utf-8"))
            slots = data["data"]["activities_calendar"]
        except json.JSONDecodeError as err:
            error_msg = "Invalid JSON response while fetching slots."
            logger.error(error_msg)
            raise RuntimeError(error_msg) from err
        except KeyError as err:
            error_msg = f"Missing expected key in response: {err}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from err

        if not slots:
            warning_msg = ErrorMessages.no_slots(activity_name, day)
            logger.warning(warning_msg)
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
            warning_msg = ErrorMessages.no_matching_slots(activity_name, day)
            logger.warning(warning_msg)
            return DataFrame()

        return df_slots
