# tests/test_service.py

import unittest
from datetime import datetime
from unittest.mock import patch

import pandas as pd
import pytz

# Import the objects we want to test from the pysportbot.service module
from pysportbot.service import (
    calculate_class_day,
    calculate_next_execution,
    run_service,
    validate_config,
    validate_config_and_activities,
)
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
            "classes": [],
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
        e.g. "Each class must include 'activity', 'class_day', 'class_time', 'booking_execution', and 'weekly'."
        """
        config = {
            "email": "someone@example.com",
            "password": "secret",
            "classes": [
                {
                    # Missing "activity", "class_day", etc.
                    "weekly": True
                }
            ],
        }
        with self.assertRaises(ValueError) as ctx:
            validate_config(config)

        expected_message = ErrorMessages.invalid_class_definition()
        self.assertIn(
            expected_message,
            str(ctx.exception),
        )

    def test_validate_config_invalid_weekly_now(self):
        """
        Test that validate_config raises an error if weekly == True but booking_execution == 'now'.
        The actual message is from ErrorMessages.invalid_weekly_now(),
        e.g. "Invalid combination: cannot use weekly=True with booking_execution='now'."
        """
        config = {
            "email": "someone@example.com",
            "password": "secret",
            "classes": [
                {
                    "activity": "Yoga",
                    "class_day": "Monday",
                    "class_time": "18:00:00",
                    "booking_execution": "now",
                    "weekly": True,
                }
            ],
        }
        with self.assertRaises(ValueError) as ctx:
            validate_config(config)

        expected_message = ErrorMessages.invalid_weekly_now()
        self.assertIn(
            expected_message,
            str(ctx.exception),
        )

    # ------------------------------------------------------------------------
    # 2. Tests for validating activities against SportBot
    # ------------------------------------------------------------------------

    @patch("pysportbot.service.SportBot")  # Correct import path
    def test_validate_config_and_activities_unknown_activity(self, mock_sportbot_class):
        """
        Test that if the config specifies an activity not present in SportBot activities,
        validate_config_and_activities raises an error.
        The actual message is from ErrorMessages.activity_not_found(...),
        e.g. "No activity found with the name 'CrossFit'. Available activities are: Yoga."
        """
        mock_bot_instance = mock_sportbot_class.return_value
        # Suppose available activities is only "Yoga", but config has "CrossFit"
        mock_bot_instance.activities.return_value = pd.DataFrame({"name_activity": ["Yoga"]})

        config = {
            "email": "test@example.com",
            "password": "password",
            "classes": [
                {
                    "activity": "CrossFit",
                    "class_day": "Monday",
                    "class_time": "18:00:00",
                    "booking_execution": "now",
                    "weekly": False,
                }
            ],
        }

        with self.assertRaises(ValueError) as ctx:
            validate_config_and_activities(config, mock_bot_instance)

        expected_message = ErrorMessages.activity_not_found("CrossFit", ["Yoga"])
        self.assertIn(expected_message, str(ctx.exception))

    # ------------------------------------------------------------------------
    # 3. Tests for the utility functions that calculate execution dates
    # ------------------------------------------------------------------------

    @patch("pysportbot.service.datetime", wraps=datetime)  # Use the real datetime for unmocked methods
    def test_calculate_next_execution(self, mock_datetime):
        """
        If today is Wednesday 2024-01-10, then 'Friday 07:30:00' should be 2 days ahead (2024-01-12).
        """
        tz = pytz.timezone("Europe/Madrid")
        mock_now = tz.localize(datetime(2024, 1, 10, 12, 0, 0))  # Wednesday
        mock_datetime.now.return_value = mock_now

        # Call the function
        result = calculate_next_execution("Friday 07:30:00", time_zone="Europe/Madrid")

        # Expected result
        expected = tz.localize(datetime(2024, 1, 12, 7, 30, 0))

        # Assert
        self.assertEqual(result, expected)

    @patch("pysportbot.service.datetime")  # Correct import path
    def test_calculate_class_day(self, mock_datetime):
        """
        If today is Wednesday 2024-01-10, the next Monday is 2024-01-15 (5 days later).
        """
        tz = pytz.timezone("Europe/Madrid")
        mock_now = tz.localize(datetime(2024, 1, 10, 12, 0, 0))  # Wednesday
        mock_datetime.now.return_value = mock_now

        result = calculate_class_day("Monday", time_zone="Europe/Madrid")
        expected = tz.localize(datetime(2024, 1, 15, 12, 0, 0))
        self.assertEqual(result.date(), expected.date())

    # ------------------------------------------------------------------------
    # 4. Tests for the main booking logic (weekly vs. one-off)
    # ------------------------------------------------------------------------

    @patch("pysportbot.service.datetime", wraps=datetime)
    @patch("pysportbot.service.SportBot")
    @patch("pysportbot.service.schedule.run_pending")
    @patch("pysportbot.service.time.sleep", return_value=None)
    def test_weekly_scheduling(self, mock_sleep, mock_run_pending, mock_sportbot_class, mock_datetime):
        """
        Test that run_service schedules a weekly job and (theoretically) calls schedule.run_pending() in a loop.
        """
        tz = pytz.timezone("Europe/Madrid")
        fixed_now = tz.localize(datetime(2024, 1, 3, 12, 0, 0))  # Wednesday
        mock_datetime.now.return_value = fixed_now

        mock_bot_instance = mock_sportbot_class.return_value
        mock_bot_instance.activities.return_value = pd.DataFrame({"name_activity": ["Yoga"]})
        mock_bot_instance.daily_slots.return_value = pd.DataFrame({"start_timestamp": ["2024-01-08 18:00:00"]})

        config = {
            "email": "test@example.com",
            "password": "password",
            "classes": [
                {
                    "activity": "Yoga",
                    "class_day": "Monday",
                    "class_time": "18:00:00",
                    "booking_execution": "Friday 07:30:00",
                    "weekly": True,
                }
            ],
        }

        # Ensure schedule.jobs is patched to avoid infinite loops
        with patch("pysportbot.service.schedule.jobs", new=[]):
            run_service(
                config,
                offset_seconds=0,
                retry_attempts=1,
                retry_delay_minutes=0,
                time_zone="Europe/Madrid",
            )

        mock_bot_instance.login.assert_called_with("test@example.com", "password")
        self.assertTrue(mock_bot_instance.login.called, "Expected login to be called")

    @patch("pysportbot.service.datetime")
    @patch("pysportbot.service.SportBot")
    @patch("pysportbot.service.schedule.run_pending")
    @patch("pysportbot.service.time.sleep", return_value=None)
    def test_now_scheduling(self, mock_sleep, mock_run_pending, mock_sportbot_class, mock_datetime):
        """
        Test that a one-off booking with "now" triggers an immediate booking
        (no infinite scheduling loop).
        """
        # Mock datetime.now() to a fixed date
        tz = pytz.timezone("Europe/Madrid")
        fixed_now = tz.localize(datetime(2024, 1, 7, 12, 0, 0))  # Sunday
        mock_datetime.now.return_value = fixed_now
        mock_datetime.strptime.side_effect = lambda s, fmt: datetime.strptime(s, fmt)

        mock_bot_instance = mock_sportbot_class.return_value
        mock_bot_instance.activities.return_value = pd.DataFrame({"name_activity": ["Yoga"]})
        # Booking date should be 2024-01-08 (Monday)
        mock_bot_instance.daily_slots.return_value = pd.DataFrame({"start_timestamp": ["2024-01-08 18:00:00"]})

        config = {
            "email": "test@example.com",
            "password": "password",
            "classes": [
                {
                    "activity": "Yoga",
                    "class_day": "Monday",
                    "class_time": "18:00:00",
                    "booking_execution": "now",
                    "weekly": False,
                }
            ],
        }

        run_service(
            config,
            offset_seconds=0,
            retry_attempts=1,
            retry_delay_minutes=0,
            time_zone="Europe/Madrid",
        )

        # Check calls
        mock_bot_instance.daily_slots.assert_called_once()
        mock_bot_instance.book.assert_called_with(activity="Yoga", start_time="2024-01-08 18:00:00")

        # "now" booking should not enter an infinite loop
        mock_run_pending.assert_not_called()

    # ------------------------------------------------------------------------
    # 5. Tests for error handling (no matching slots, already booked, retries)
    # ------------------------------------------------------------------------

    @patch("pysportbot.service.SportBot")
    @patch("pysportbot.service.schedule.run_pending")
    @patch("pysportbot.service.time.sleep", return_value=None)
    def test_no_matching_slots_error(self, mock_sleep, mock_run_pending, mock_sportbot_class):
        """
        If daily_slots() returns no row matching class_time, we expect a ValueError.
        However, run_service handles it internally and logs an error instead of raising.
        Thus, we'll check the log messages.
        """
        mock_bot_instance = mock_sportbot_class.return_value
        mock_bot_instance.activities.return_value = pd.DataFrame({"name_activity": ["Yoga"]})
        mock_bot_instance.daily_slots.return_value = pd.DataFrame({"start_timestamp": []})

        config = {
            "email": "test@example.com",
            "password": "password",
            "classes": [
                {
                    "activity": "Yoga",
                    "class_day": "Monday",
                    "class_time": "18:00:00",
                    "booking_execution": "now",
                    "weekly": False,
                }
            ],
        }

        # We need to mock datetime to return a fixed date for calculate_class_day
        with patch("pysportbot.service.datetime") as mock_datetime:
            tz = pytz.timezone("Europe/Madrid")
            fixed_now = tz.localize(datetime(2024, 1, 7, 12, 0, 0))  # Sunday
            mock_datetime.now.return_value = fixed_now
            mock_datetime.strptime.side_effect = lambda s, fmt: datetime.strptime(s, fmt)

            with self.assertLogs("pysportbot.service", level="WARNING") as cm:
                run_service(
                    config, offset_seconds=0, retry_attempts=1, retry_delay_minutes=0, time_zone="Europe/Madrid"
                )

        # Expected log messages:
        # WARNING  pysportbot.service:service.py:155 Attempt 1 failed for Yoga: No matching slots available for Yoga at 18:00:00 on 2024-01-08
        # ERROR    pysportbot.service:service.py:167 Failed to book Yoga after 1 attempts.

        expected_warning = ErrorMessages.no_matching_slots_for_time("Yoga", "18:00:00", "2024-01-08")
        self.assertIn(expected_warning, cm.output[0])

        expected_error = "Failed to book Yoga after 1 attempts."
        self.assertIn(expected_error, cm.output[1])

    @patch("pysportbot.service.SportBot")  # Correct import path
    @patch("pysportbot.service.schedule.run_pending")  # Correct import path
    @patch("pysportbot.service.time.sleep", return_value=None)  # Correct import path
    def test_slot_already_booked_error(self, mock_sleep, mock_run_pending, mock_sportbot_class):
        """
        If bot.book(...) raises a slot_already_booked error, the code should skip further retries.
        """
        mock_bot_instance = mock_sportbot_class.return_value
        mock_bot_instance.activities.return_value = pd.DataFrame({"name_activity": ["Yoga"]})
        mock_bot_instance.daily_slots.return_value = pd.DataFrame({"start_timestamp": ["2024-01-08 18:00:00"]})

        # The "slot already booked" message
        already_booked_msg = ErrorMessages.slot_already_booked()
        mock_bot_instance.book.side_effect = ValueError(already_booked_msg)

        config = {
            "email": "test@example.com",
            "password": "password",
            "classes": [
                {
                    "activity": "Yoga",
                    "class_day": "Monday",
                    "class_time": "18:00:00",
                    "booking_execution": "now",
                    "weekly": False,
                }
            ],
        }

        # Mock datetime to set the booking date to 2024-01-08
        with patch("pysportbot.service.datetime") as mock_datetime:
            tz = pytz.timezone("Europe/Madrid")
            fixed_now = tz.localize(datetime(2024, 1, 7, 12, 0, 0))  # Sunday
            mock_datetime.now.return_value = fixed_now
            mock_datetime.strptime.side_effect = lambda s, fmt: datetime.strptime(s, fmt)

            with self.assertLogs("pysportbot.service", level="WARNING") as cm:
                run_service(
                    config, offset_seconds=0, retry_attempts=2, retry_delay_minutes=1, time_zone="Europe/Madrid"
                )

        # Expected log messages:
        # WARNING  pysportbot.service:service.py:155 Attempt 1 failed for Yoga: The slot is already booked.
        # ERROR    pysportbot.service:service.py:167 Failed to book Yoga after 2 attempts.

        expected_warning = already_booked_msg
        self.assertIn(expected_warning, cm.output[0])

        # Ensure that book was called only once
        mock_bot_instance.book.assert_called_once()

    @patch("pysportbot.service.SportBot")
    @patch("pysportbot.service.schedule.run_pending")
    @patch("pysportbot.service.time.sleep", return_value=None)
    def test_retry_mechanism(self, mock_sleep, mock_run_pending, mock_sportbot_class):
        """
        If booking fails for a reason other than 'already booked',
        the service should retry up to 'retry_attempts'.
        """
        mock_bot_instance = mock_sportbot_class.return_value
        mock_bot_instance.activities.return_value = pd.DataFrame({"name_activity": ["Yoga"]})
        mock_bot_instance.daily_slots.return_value = pd.DataFrame({"start_timestamp": ["2024-01-08 18:00:00"]})

        # Modify the side_effect to raise an error on every booking attempt
        def side_effect(*args, **kwargs):
            raise ValueError("Some random booking error")

        mock_bot_instance.book.side_effect = side_effect

        config = {
            "email": "test@example.com",
            "password": "password",
            "classes": [
                {
                    "activity": "Yoga",
                    "class_day": "Monday",
                    "class_time": "18:00:00",
                    "booking_execution": "now",
                    "weekly": False,
                }
            ],
        }

        # Mock datetime to set the booking date to 2024-01-08
        with patch("pysportbot.service.datetime") as mock_datetime:
            tz = pytz.timezone("Europe/Madrid")
            fixed_now = tz.localize(datetime(2024, 1, 7, 12, 0, 0))  # Sunday
            mock_datetime.now.return_value = fixed_now
            mock_datetime.strptime.side_effect = lambda s, fmt: datetime.strptime(s, fmt)

            with self.assertLogs("pysportbot.service", level="WARNING") as cm:
                run_service(
                    config, offset_seconds=0, retry_attempts=2, retry_delay_minutes=1, time_zone="Europe/Madrid"
                )

        # Expected log messages:
        # WARNING  pysportbot.service:service.py:155 Attempt 1 failed for Yoga: Some random booking error
        # WARNING  pysportbot.service:service.py:155 Attempt 2 failed for Yoga: Some random booking error
        # ERROR    pysportbot.service:service.py:167 Failed to book Yoga after 2 attempts.

        expected_warning_1 = "Attempt 1 failed for Yoga: Some random booking error"
        expected_warning_2 = "Attempt 2 failed for Yoga: Some random booking error"
        expected_error = "Failed to book Yoga after 2 attempts."

        # Ensure that all expected log messages are present
        self.assertIn(expected_warning_1, cm.output[0])
        self.assertIn(expected_warning_2, cm.output[1])
        self.assertIn(expected_error, cm.output[2])

        # We expect exactly two calls to book(): both fail
        self.assertEqual(mock_bot_instance.book.call_count, 2)
        self.assertTrue(mock_sleep.called, "Expected to sleep between retries")


if __name__ == "__main__":
    unittest.main()