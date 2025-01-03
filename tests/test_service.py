import unittest
from datetime import datetime
from unittest.mock import patch

import pandas as pd
import pytz

from pysportbot.service.config_validator import validate_activities, validate_config
from pysportbot.service.scheduling import calculate_class_day, calculate_next_execution
from pysportbot.utils.errors import ErrorMessages


class TestService(unittest.TestCase):
    """
    A suite of tests for pysportbot.service that mocks out dependencies like SportBot,
    scheduling, and time.
    """

    # ------------------------------------------------------------------------
    # 1. Tests for config validation
    # ------------------------------------------------------------------------
    def test_validate_config_missing_required_key(self):
        """
        Test that validate_config raises an error if required keys are missing.
        The actual error message is: "Missing required key in config: email"
        """
        config_missing_email = {
            # 'email': 'someone@example.com',  # Oops, we forgot to include it
            "password": "secret",
            "centre": "my-gim",
            "classes": [],
            "booking_execution": "Monday 07:30:00",
        }
        with self.assertRaises(ValueError) as ctx:
            validate_config(config_missing_email)

        # Match the actual message from ErrorMessages.missing_required_key(key)
        expected_message = ErrorMessages.missing_required_key("email")
        self.assertIn(expected_message, str(ctx.exception))

    def test_validate_config_invalid_class_definition(self):
        """
        Test that validate_config raises an error if 'classes' are missing required keys.
        The actual message is from ErrorMessages.invalid_class_definition(),
        e.g. "Each class must include 'activity', 'class_day', and 'class_time'."
        """
        config = {
            "email": "someone@example.com",
            "password": "secret",
            "centre": "my-gim",
            "classes": [
                {
                    # Missing "activity", "class_day", and "class_time"
                    "weekly": True
                }
            ],
            "booking_execution": "Monday 07:30:00",
        }
        with self.assertRaises(ValueError) as ctx:
            validate_config(config)

        expected_message = ErrorMessages.invalid_class_definition()
        self.assertIn(expected_message, str(ctx.exception))

    # ------------------------------------------------------------------------
    # 2. Tests for validating activities against SportBot
    # ------------------------------------------------------------------------

    @patch("pysportbot.service.config_validator.SportBot")
    def test_validate_activities_unknown_activity(self, mock_sportbot_class):
        """
        Test that if the config specifies an activity not present in SportBot activities,
        validate_activities raises an error.
        The actual message is from ErrorMessages.activity_not_found(...),
        e.g. "No activity found with the name 'CrossFit'. Available activities are: Yoga."
        """
        # Mock the SportBot instance and available activities
        mock_bot_instance = mock_sportbot_class.return_value
        mock_bot_instance.activities.return_value = pd.DataFrame({"name_activity": ["Yoga"]})

        # Define a configuration with an unknown activity
        config = {
            "email": "test@example.com",
            "password": "password",
            "centre": "my-gim",
            "classes": [
                {
                    "activity": "CrossFit",
                    "class_day": "Monday",
                    "class_time": "18:00:00",
                }
            ],
        }

        with self.assertRaises(ValueError) as ctx:
            validate_activities(mock_bot_instance, config)

        expected_message = ErrorMessages.activity_not_found("CrossFit", ["Yoga"])
        self.assertIn(expected_message, str(ctx.exception))

    # ------------------------------------------------------------------------
    # 3. Tests for the utility functions that calculate execution dates
    # ------------------------------------------------------------------------

    @patch("pysportbot.service.scheduling.datetime", wraps=datetime)
    def test_calculate_next_execution(self, mock_datetime):
        """
        If today is Wednesday 2024-01-10, then 'Friday 07:30:00' should be 2 days ahead (2024-01-12).
        """
        tz = pytz.timezone("Europe/Madrid")
        mock_now = tz.localize(datetime(2024, 1, 10, 12, 0, 0))
        mock_datetime.now.return_value = mock_now

        result = calculate_next_execution("Friday 07:30:00", time_zone="Europe/Madrid")
        expected = tz.localize(datetime(2024, 1, 12, 7, 30, 0))
        self.assertEqual(result, expected)

    @patch("pysportbot.service.scheduling.datetime")
    def test_calculate_class_day(self, mock_datetime):
        """
        If today is Wednesday 2024-01-10, the next Monday is 2024-01-15 (5 days later).
        """
        tz = pytz.timezone("Europe/Madrid")
        mock_now = tz.localize(datetime(2024, 1, 10, 12, 0, 0))
        mock_datetime.now.return_value = mock_now

        result = calculate_class_day("Monday", time_zone="Europe/Madrid")
        expected = tz.localize(datetime(2024, 1, 15, 12, 0, 0))
        self.assertEqual(result.date(), expected.date())


if __name__ == "__main__":
    unittest.main()
