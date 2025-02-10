import json
import unittest
from datetime import datetime
from unittest.mock import MagicMock, call, mock_open, patch

import pandas as pd
import pytz

from pysportbot.service.booking import attempt_booking, schedule_bookings

# Adjust these imports to match your actual project structure:
from pysportbot.service.config_loader import load_config
from pysportbot.service.config_validator import DAY_MAP, validate_activities, validate_config
from pysportbot.service.scheduling import calculate_class_day, calculate_next_execution
from pysportbot.service.service import run_service
from pysportbot.service.threading import get_n_threads
from pysportbot.utils.errors import ErrorMessages


class TestConfigLoader(unittest.TestCase):
    """
    Tests for config_loader.py module.
    """

    def test_load_config_valid_file(self):
        """
        Test load_config with a valid JSON file.
        """
        fake_json = json.dumps(
            {
                "email": "test@example.com",
                "password": "secret",
                "centre": "my-gim",
                "classes": [],
                "booking_execution": "now",
            }
        )
        with patch("builtins.open", mock_open(read_data=fake_json)), patch("os.path.exists", return_value=True):
            config = load_config("fake_config_path.json")
            self.assertIn("email", config)
            self.assertEqual(config["email"], "test@example.com")

    def test_load_config_file_not_found(self):
        """
        Test load_config if the file does not exist.
        """
        with self.assertRaises(FileNotFoundError):
            load_config("non_existent_config.json")

    def test_load_config_invalid_json(self):
        """
        Test load_config with an invalid JSON structure.
        """
        invalid_data = "{invalid_json: True unquoted_value}"
        # Combine into one 'with' to fix SIM117
        with patch("builtins.open", mock_open(read_data=invalid_data)), self.assertRaises(json.JSONDecodeError):
            load_config("fake_config_path.json")


class TestConfigValidator(unittest.TestCase):
    """
    Tests for config_validator.py module.
    """

    def test_validate_config_missing_required_key(self):
        """
        Test that validate_config raises an error if required keys are missing.
        """
        config_missing_email = {
            # 'email': 'someone@example.com',  # omitted on purpose
            "password": "secret",
            "centre": "my-gim",
            "classes": [],
            "booking_execution": "Monday 07:30:00",
        }
        with self.assertRaises(ValueError) as ctx:
            validate_config(config_missing_email)
        expected_message = ErrorMessages.missing_required_key("email")
        self.assertIn(expected_message, str(ctx.exception))

    def test_validate_config_invalid_class_definition(self):
        """
        Test that validate_config raises an error if 'classes' are missing required keys.
        """
        config = {
            "email": "someone@example.com",
            "password": "secret",
            "centre": "my-gim",
            "classes": [
                {
                    # missing 'activity' and 'class_time'
                    "class_day": "Monday"
                }
            ],
            "booking_execution": "Monday 07:30:00",
        }
        with self.assertRaises(ValueError) as ctx:
            validate_config(config)

        expected_message = ErrorMessages.invalid_class_definition()
        self.assertIn(expected_message, str(ctx.exception))

    def test_validate_config_booking_execution_now(self):
        """
        Test that validate_config allows 'booking_execution' to be 'now' without error.
        """
        config = {
            "email": "someone@example.com",
            "password": "secret",
            "centre": "my-gim",
            "classes": [
                {
                    "activity": "Yoga",
                    "class_day": "Monday",
                    "class_time": "10:00:00",
                }
            ],
            "booking_execution": "now",
        }
        # Should not raise
        validate_config(config)

    def test_validate_config_invalid_booking_execution_format(self):
        """
        Test that validate_config raises an error if the booking_execution format is invalid.
        """
        config = {
            "email": "someone@example.com",
            "password": "secret",
            "centre": "my-gim",
            "classes": [],
            "booking_execution": "Monday07:30:00",  # missing space
        }
        with self.assertRaises(ValueError) as ctx:
            validate_config(config)
        expected_message = ErrorMessages.invalid_booking_execution_format()
        self.assertIn(expected_message, str(ctx.exception))

    @patch("pysportbot.service.config_validator.SportBot")
    def test_validate_activities_unknown_activity(self, mock_sportbot_class):
        """
        Test that if the config specifies an activity not present in SportBot activities,
        validate_activities raises an error.
        """
        mock_bot_instance = mock_sportbot_class.return_value
        mock_bot_instance.activities.return_value = pd.DataFrame({"name_activity": ["Yoga"]})

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
            "booking_execution": "now",
        }

        with self.assertRaises(ValueError) as ctx:
            validate_activities(mock_bot_instance, config)

        expected_message = ErrorMessages.activity_not_found("CrossFit", ["Yoga"])
        self.assertIn(expected_message, str(ctx.exception))


class TestScheduling(unittest.TestCase):
    """
    Tests for scheduling.py module.
    """

    @patch("pysportbot.service.scheduling.datetime", wraps=datetime)
    def test_calculate_next_execution_future_day(self, mock_datetime):
        """
        If today is Wednesday 2024-01-10, then 'Friday 07:30:00' should be 2 days ahead (2024-01-12).
        """
        tz = pytz.timezone("Europe/Madrid")
        mock_now = tz.localize(datetime(2024, 1, 10, 12, 0, 0))
        mock_datetime.now.return_value = mock_now

        result = calculate_next_execution("Friday 07:30:00", time_zone="Europe/Madrid")
        expected = tz.localize(datetime(2024, 1, 12, 7, 30, 0))
        self.assertEqual(result, expected)

    @patch("pysportbot.service.scheduling.datetime", wraps=datetime)
    def test_calculate_next_execution_same_day_future_time(self, mock_datetime):
        """
        If today is Monday 2024-01-08 at 10:00 and booking_execution is Monday 20:00,
        the next execution is that same day 20:00.
        """
        tz = pytz.timezone("Europe/Madrid")
        mock_now = tz.localize(datetime(2024, 1, 8, 10, 0, 0))  # Monday
        mock_datetime.now.return_value = mock_now

        result = calculate_next_execution("Monday 20:00:00", "Europe/Madrid")
        expected = tz.localize(datetime(2024, 1, 8, 20, 0, 0))
        self.assertEqual(result, expected)

    @patch("pysportbot.service.scheduling.datetime", wraps=datetime)
    def test_calculate_next_execution_same_day_past_time(self, mock_datetime):
        """
        If today is Monday 2024-01-08 at 22:00 and booking_execution is Monday 20:00,
        the next execution is next Monday (7 days later).
        """
        tz = pytz.timezone("Europe/Madrid")
        mock_now = tz.localize(datetime(2024, 1, 8, 22, 0, 0))
        mock_datetime.now.return_value = mock_now

        result = calculate_next_execution("Monday 20:00:00", "Europe/Madrid")
        expected = tz.localize(datetime(2024, 1, 15, 20, 0, 0))
        self.assertEqual(result, expected)

    @patch("pysportbot.service.scheduling.datetime", wraps=datetime)
    def test_calculate_next_execution_now(self, mock_datetime):
        """
        If booking_execution is 'now', we simply return the current time.
        """
        tz = pytz.timezone("Europe/Madrid")
        mock_now = tz.localize(datetime(2024, 1, 10, 22, 0, 0))
        mock_datetime.now.return_value = mock_now

        result = calculate_next_execution("now", "Europe/Madrid")
        self.assertEqual(result, mock_now)

    @patch("pysportbot.service.scheduling.datetime", wraps=datetime)
    def test_calculate_class_day_future_day(self, mock_datetime):
        """
        If today is Wednesday 2024-01-10, the next Monday is 2024-01-15 (5 days later).
        """
        tz = pytz.timezone("Europe/Madrid")
        mock_now = tz.localize(datetime(2024, 1, 10, 12, 0, 0))
        mock_datetime.now.return_value = mock_now

        result = calculate_class_day("Monday", "Europe/Madrid")
        expected = tz.localize(datetime(2024, 1, 15, 12, 0, 0))
        self.assertEqual(result.date(), expected.date())

    @patch("pysportbot.service.scheduling.datetime", wraps=datetime)
    def test_calculate_class_day_always_next_week(self, mock_datetime):
        """
        If today is Friday at 07:30 and class_day is Friday at 18:00,
        ensure the booking is for NEXT Friday, not today.
        """
        tz = pytz.timezone("Europe/Madrid")
        mock_now = tz.localize(datetime(2024, 1, 5, 7, 30, 0))  # Simulated Friday, Jan 5, 2024, 07:30
        mock_datetime.now.return_value = mock_now

        result = calculate_class_day("Friday", "Europe/Madrid")

        # Expected: The NEXT Friday (2024-01-12), NOT today (2024-01-05)
        expected = tz.localize(datetime(2024, 1, 12, 7, 30, 0))  # Next Friday

        self.assertEqual(result.date(), expected.date())

    @patch("pysportbot.service.scheduling.datetime", wraps=datetime)
    def test_calculate_class_day_midweek_execution(self, mock_datetime):
        """
        If today is Wednesday and class_day is next Tuesday, ensure it selects the next week's Tuesday.
        """
        tz = pytz.timezone("Europe/Madrid")
        mock_now = tz.localize(datetime(2024, 1, 10, 12, 0, 0))  # Wednesday
        mock_datetime.now.return_value = mock_now

        result = calculate_class_day("Tuesday", "Europe/Madrid")

        # Expected: Next week's Tuesday (2024-01-16)
        expected = tz.localize(datetime(2024, 1, 16, 12, 0, 0))
        self.assertEqual(result.date(), expected.date())

    def test_day_map_contains_all_days(self):
        """
        Test that DAY_MAP includes all 7 days with correct indexes.
        """
        expected = {
            "monday": 0,
            "tuesday": 1,
            "wednesday": 2,
            "thursday": 3,
            "friday": 4,
            "saturday": 5,
            "sunday": 6,
        }
        self.assertEqual(DAY_MAP, expected)


class TestBooking(unittest.TestCase):
    """
    Tests for booking.py module.
    """

    @patch("pysportbot.service.booking.datetime", wraps=datetime)
    @patch("pysportbot.service.booking.time")
    @patch("pysportbot.service.booking.logger")
    def test_schedule_bookings_future_execution(self, mock_logger, mock_time, mock_datetime):
        """
        Test schedule_bookings when execution is scheduled for a future time.
        """
        # Mock current time to simulate a future execution
        tz = pytz.timezone("Europe/Madrid")
        mock_now = tz.localize(datetime(2024, 1, 8, 9, 0, 0))  # Current time
        mock_execution_time = tz.localize(datetime(2024, 1, 8, 10, 0, 0))  # 1 hour later
        mock_datetime.now.return_value = mock_now

        # Mock the calculate_next_execution function to return the future execution time
        with patch("pysportbot.service.booking.calculate_next_execution", return_value=mock_execution_time):
            mock_bot = MagicMock()
            config = {
                "email": "test@example.com",
                "password": "pass",
                "centre": "my-gim",
                "booking_execution": "2024-01-08 10:00:00",
                "classes": [{"activity": "Yoga", "class_day": "Monday", "class_time": "09:00:00"}],
            }

            # Run schedule_bookings
            schedule_bookings(
                bot=mock_bot,
                config=config,
                booking_delay=10,
                retry_attempts=2,
                retry_delay=1,
                time_zone="Europe/Madrid",
                max_threads=1,
            )

        # Assert the correct sleep calls
        time_until_execution = (mock_execution_time - mock_now).total_seconds()
        reauth_sleep = time_until_execution - 60  # Time until reauthentication
        total_remaining_time = time_until_execution  # Full time until execution

        # Expected sleep calls in the correct order
        expected_sleep_calls = [
            call(reauth_sleep),  # Time until reauthentication
            call(total_remaining_time),  # Full remaining time
            call(10),  # Booking delay
        ]
        mock_time.sleep.assert_has_calls(expected_sleep_calls, any_order=False)

        # Assert the bot.login is called
        mock_bot.login.assert_called_once_with("test@example.com", "pass", "my-gim")

        # Verify logging calls
        mock_logger.info.assert_any_call(
            f"Waiting {time_until_execution:.2f} seconds until global execution time: "
            f"{mock_execution_time.strftime('%Y-%m-%d %H:%M:%S %z')}."
        )
        mock_logger.info.assert_any_call("Re-authenticating before booking.")
        mock_logger.info.assert_any_call("Waiting 10 seconds before attempting booking.")

    @patch("pysportbot.service.booking.logger")
    @patch("pysportbot.service.scheduling.datetime", wraps=datetime)
    def test_attempt_booking_success(self, mock_datetime_sched, mock_logger):
        """
        If matching_slots is found, attempt_booking should succeed on the first try.
        """
        # Force the current date to 2024-01-10 (which is a Wednesday)
        tz = pytz.timezone("Europe/Madrid")
        mock_now = tz.localize(datetime(2024, 1, 10, 9, 0, 0))
        mock_datetime_sched.now.return_value = mock_now

        mock_bot = MagicMock()
        # The returned daily_slots matches the requested "18:00:00" on 2024-01-10
        mock_bot.daily_slots.return_value = pd.DataFrame({"start_timestamp": ["2024-01-10 18:00:00"]})

        attempt_booking(
            bot=mock_bot,
            activity="Yoga",
            class_day="Wednesday",  # This maps to 2024-01-10 from our patch
            class_time="18:00:00",
            retry_attempts=3,
            retry_delay=1,
            time_zone="Europe/Madrid",
        )
        # If a slot matches, we book exactly once
        mock_bot.book.assert_called_once()

    @patch("pysportbot.service.booking.logger")
    @patch("pysportbot.service.scheduling.datetime", wraps=datetime)
    def test_attempt_booking_no_matching_slots(self, mock_datetime_sched, mock_logger):
        """
        If no matching slot is found, attempt_booking should call the bot.book()
        method, which will raise an exception internally, and log warnings on each attempt.
        """
        # Make the current date 2024-01-10 (Wednesday)
        tz = pytz.timezone("Europe/Madrid")
        mock_now = tz.localize(datetime(2024, 1, 10, 12, 0, 0))
        mock_datetime_sched.now.return_value = mock_now

        mock_bot = MagicMock()
        # Mock the bot.book method to simulate a ValueError for no matching slots
        mock_bot.book.side_effect = ValueError(
            ErrorMessages.no_matching_slots_for_time("Yoga", "18:00:00", "2024-01-10")
        )

        attempt_booking(
            bot=mock_bot,
            activity="Yoga",
            class_day="Wednesday",
            class_time="18:00:00",
            retry_attempts=2,
            retry_delay=0,
            time_zone="Europe/Madrid",
        )

        # Check that book() was called twice (retry_attempts = 2)
        self.assertEqual(mock_bot.book.call_count, 2)

        # On the final attempt, ensure the correct error message was logged
        last_warning = mock_logger.warning.call_args_list[-1][0][0]
        self.assertIn(
            ErrorMessages.no_matching_slots_for_time("Yoga", "18:00:00", "2024-01-10"),
            last_warning,
        )

    @patch("pysportbot.service.booking.logger")
    @patch("pysportbot.service.scheduling.datetime", wraps=datetime)
    def test_attempt_booking_slot_already_booked(self, mock_datetime_sched, mock_logger):
        """
        If the slot is already booked, abort further retries.
        """
        # Current date: 2024-01-10 (Wednesday)
        tz = pytz.timezone("Europe/Madrid")
        mock_now = tz.localize(datetime(2024, 1, 10, 10, 0, 0))
        mock_datetime_sched.now.return_value = mock_now

        mock_bot = MagicMock()
        mock_bot.daily_slots.return_value = pd.DataFrame({"start_timestamp": ["2024-01-10 18:00:00"]})
        # First attempt raises 'slot already booked', so we skip subsequent attempts
        mock_bot.book.side_effect = [ValueError(ErrorMessages.slot_already_booked())]

        attempt_booking(
            bot=mock_bot,
            activity="Yoga",
            class_day="Wednesday",
            class_time="18:00:00",
            retry_attempts=3,
            retry_delay=1,
            time_zone="Europe/Madrid",
        )
        mock_bot.book.assert_called_once()  # Should only be called the first time

    @patch("pysportbot.service.booking.as_completed")
    @patch("pysportbot.service.booking.ThreadPoolExecutor")
    @patch("pysportbot.service.booking.time")
    def test_schedule_bookings(self, mock_time, mock_executor, mock_as_completed):
        """
        Ensures parallel bookings are submitted with ThreadPoolExecutor without getting stuck.
        """
        # 1. Mock the as_completed() to return an empty or a list of mock futures
        mock_future = MagicMock()
        mock_as_completed.return_value = [mock_future]

        # 2. Mock the __enter__ context manager for ThreadPoolExecutor
        mock_executor_instance = mock_executor.return_value.__enter__.return_value

        # 3. Each call to submit() returns the same mock_future (or you can create multiple)
        mock_executor_instance.submit.return_value = mock_future

        # 4. Everything else (bot, classes, etc.)
        mock_bot = MagicMock()

        config = {
            "email": "my@my.com",
            "password": "pass",
            "centre": "my-gim",
            "booking_execution": "now",
            "classes": [
                {"activity": "Yoga", "class_day": "Monday", "class_time": "09:00:00"},
                {"activity": "Boxing", "class_day": "Tuesday", "class_time": "10:00:00"},
            ],
        }

        # Call function under test
        schedule_bookings(
            bot=mock_bot,
            config=config,
            booking_delay=2,
            retry_attempts=2,
            retry_delay=1,
            time_zone="Europe/Madrid",
            max_threads=2,
        )

        # Assertions
        mock_time.sleep.assert_called_once_with(2)
        mock_executor.assert_called_once_with(max_workers=2)

        # ThreadPoolExecutor.submit should have been called for each class:
        self.assertEqual(mock_executor_instance.submit.call_count, len(config["classes"]))
        # as_completed was called with the dictionary of futures
        # but we only need to confirm it wasn't stuck
        self.assertTrue(mock_as_completed.called)


class TestThreading(unittest.TestCase):
    """
    Tests for threading.py module.
    """

    def test_get_n_threads_zero_requested_raises(self):
        """
        If 0 threads requested, raise ValueError.
        """
        with self.assertRaises(ValueError):
            get_n_threads(0, 2)

    @patch("os.cpu_count", return_value=4)
    def test_get_n_threads_user_request_greater_than_cpu(self, mock_cpu_count):
        """
        If user requests more threads than CPU, limit to the CPU count (and booking count).
        """
        result = get_n_threads(10, 3)  # user wants 10, CPU=4, bookings=3 => min=3
        self.assertEqual(result, 3)

    @patch("os.cpu_count", return_value=4)
    def test_get_n_threads_no_bookings(self, mock_cpu_count):
        """
        If there are no bookings, returns 0 threads.
        """
        result = get_n_threads(-1, 0)  # no bookings
        self.assertEqual(result, 0)

    @patch("os.cpu_count", return_value=8)
    def test_get_n_threads_auto_detect_with_fewer_bookings(self, mock_cpu_count):
        """
        If max_user_threads == -1, min(available_threads, requested_bookings).
        """
        result = get_n_threads(-1, 3)  # CPU=8, bookings=3 => min=3
        self.assertEqual(result, 3)


class TestServiceRun(unittest.TestCase):
    """
    Tests for the service.py 'run_service' function.
    """

    @patch("pysportbot.service.service.validate_config")
    @patch("pysportbot.service.service.validate_activities")
    @patch("pysportbot.service.service.get_n_threads", return_value=2)
    @patch("pysportbot.service.service.schedule_bookings")
    @patch("pysportbot.service.service.SportBot")
    def test_run_service_success(
        self,
        mock_sportbot_class,
        mock_schedule_bookings,
        mock_get_n_threads,
        mock_validate_activities,
        mock_validate_config,
    ):
        """
        If config is valid, run_service should do the full workflow:
        validate config, login, validate activities, schedule bookings, etc.
        """
        mock_config = {
            "email": "test@example.com",
            "password": "pass",
            "centre": "my-gim",
            "classes": [{"activity": "Yoga", "class_day": "Monday", "class_time": "10:00:00"}],
            "booking_execution": "now",
        }

        run_service(
            config=mock_config,
            booking_delay=10,
            retry_attempts=2,
            retry_delay=1,
            time_zone="Europe/Madrid",
            log_level="DEBUG",
            max_threads=-1,
        )

        mock_validate_config.assert_called_once_with(mock_config)
        mock_sportbot_class.assert_called_once_with(log_level="DEBUG", time_zone="Europe/Madrid")

        bot_instance = mock_sportbot_class.return_value
        bot_instance.login.assert_called_once_with("test@example.com", "pass", "my-gim")
        mock_validate_activities.assert_called_once_with(bot_instance, mock_config)
        mock_get_n_threads.assert_called_once_with(-1, 1)  # there's only 1 class
        mock_schedule_bookings.assert_called_once()

    @patch("pysportbot.service.service.validate_config", side_effect=ValueError("Invalid config"))
    def test_run_service_config_error(self, mock_validate_config):
        """
        If validate_config raises ValueError, run_service should propagate it.
        """
        with self.assertRaises(ValueError) as ctx:
            run_service(
                config={},
                booking_delay=0,
                retry_attempts=1,
                retry_delay=0,
            )
        self.assertIn("Invalid config", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
