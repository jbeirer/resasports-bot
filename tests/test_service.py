import unittest
from datetime import date, datetime, time
from unittest.mock import MagicMock, call, patch
from zoneinfo import ZoneInfo

from pysportbot import Activity
from pysportbot.exceptions import ConfigError, SlotAlreadyBookedError, SlotNotFoundError
from pysportbot.service.booking import attempt_booking, schedule_bookings
from pysportbot.service.config import ClassSpec, ServiceConfig, WeeklyTime
from pysportbot.service.scheduling import next_class_date, next_execution
from pysportbot.service.service import run_service

TZ = ZoneInfo("Europe/Madrid")
MONDAY, TUESDAY, WEDNESDAY, FRIDAY = 0, 1, 2, 4


def make_config(classes, execution=None):
    return ServiceConfig(
        email="test@example.com", password="pass", centre="my-gim", execution=execution, classes=tuple(classes)
    )


class TestScheduling(unittest.TestCase):
    """
    Tests for scheduling.py module.
    """

    def test_next_execution_future_day(self):
        """
        If today is Wednesday 2024-01-10, then 'Friday 07:30:00' should be 2 days ahead (2024-01-12).
        """
        now = datetime(2024, 1, 10, 12, 0, 0, tzinfo=TZ)

        result = next_execution(WeeklyTime(FRIDAY, time(7, 30)), now)
        self.assertEqual(result, datetime(2024, 1, 12, 7, 30, 0, tzinfo=TZ))

    def test_next_execution_same_day_future_time(self):
        """
        If today is Monday 2024-01-08 at 10:00 and booking_execution is Monday 20:00,
        the next execution is that same day 20:00.
        """
        now = datetime(2024, 1, 8, 10, 0, 0, tzinfo=TZ)

        result = next_execution(WeeklyTime(MONDAY, time(20, 0)), now)
        self.assertEqual(result, datetime(2024, 1, 8, 20, 0, 0, tzinfo=TZ))

    def test_next_execution_same_day_past_time(self):
        """
        If today is Monday 2024-01-08 at 22:00 and booking_execution is Monday 20:00,
        the next execution is next Monday (7 days later).
        """
        now = datetime(2024, 1, 8, 22, 0, 0, tzinfo=TZ)

        result = next_execution(WeeklyTime(MONDAY, time(20, 0)), now)
        self.assertEqual(result, datetime(2024, 1, 15, 20, 0, 0, tzinfo=TZ))

    def test_next_execution_now(self):
        """
        If booking_execution is 'now', we simply return the current time.
        """
        now = datetime(2024, 1, 10, 22, 0, 0, tzinfo=TZ)

        self.assertEqual(next_execution(None, now), now)

    def test_next_class_date_future_day(self):
        """
        If today is Wednesday 2024-01-10, the next Monday is 2024-01-15 (5 days later).
        """
        now = datetime(2024, 1, 10, 12, 0, 0, tzinfo=TZ)

        self.assertEqual(next_class_date(MONDAY, now), date(2024, 1, 15))

    def test_next_class_date_always_next_week(self):
        """
        If today is Friday at 07:30 and class_day is Friday at 18:00,
        ensure the booking is for NEXT Friday, not today.
        """
        # Friday, Jan 5, 2024, 07:30
        now = datetime(2024, 1, 5, 7, 30, 0, tzinfo=TZ)

        # Expected: The NEXT Friday (2024-01-12), NOT today (2024-01-05)
        self.assertEqual(next_class_date(FRIDAY, now), date(2024, 1, 12))

    def test_next_class_date_midweek_execution(self):
        """
        If today is Wednesday and class_day is next Tuesday, ensure it selects the next week's Tuesday.
        """
        now = datetime(2024, 1, 10, 12, 0, 0, tzinfo=TZ)  # Wednesday

        self.assertEqual(next_class_date(TUESDAY, now), date(2024, 1, 16))


class TestBooking(unittest.TestCase):
    """
    Tests for booking.py module.
    """

    @patch("pysportbot.service.booking.datetime", wraps=datetime)
    @patch("pysportbot.service.booking.time")
    @patch("pysportbot.service.booking.logger")
    def test_schedule_bookings_future_execution_ensures_login(self, mock_logger, mock_time, mock_datetime):
        """
        Test schedule_bookings re-authenticates if needed when execution is scheduled for a future time.
        """
        # Mock current time to simulate a future execution
        mock_now = datetime(2024, 1, 8, 9, 0, 0, tzinfo=TZ)  # Monday, current time
        mock_execution_time = datetime(2024, 1, 8, 10, 0, 0, tzinfo=TZ)  # 1 hour later

        # Mock datetime.now() to return different values for each call
        mock_datetime.now.side_effect = [
            mock_now,  # First call - initial time check
            mock_execution_time,  # Second call - after re-authentication, time has "advanced"
        ]

        mock_bot = MagicMock()
        config = make_config([ClassSpec("Yoga", MONDAY, time(9, 0))], execution=WeeklyTime(MONDAY, time(10, 0)))

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
        remaining_time = 0  # Should be 0 since second datetime.now returns execution_time

        # Expected sleep calls in the correct order
        expected_sleep_calls = [
            call(reauth_sleep),  # Time until reauthentication
            call(remaining_time),  # Remaining time after re-auth
            call(10),  # Booking delay
        ]
        mock_time.sleep.assert_has_calls(expected_sleep_calls, any_order=False)

        # Assert the bot re-authenticated if needed, exactly once
        mock_bot.ensure_logged_in.assert_called_once_with()

        # The class is on the Monday after the execution, and the plan is logged with its date
        mock_bot.book.assert_called_once_with(activity="Yoga", start=datetime(2024, 1, 15, 9, 0, tzinfo=TZ))
        mock_logger.info.assert_any_call("Scheduled to book 'Yoga' on Monday 2024-01-15 at 09:00.")

    @patch("pysportbot.service.booking.datetime", wraps=datetime)
    @patch("pysportbot.service.booking.time")
    @patch("pysportbot.service.booking.logger")
    def test_schedule_bookings_reauthentication_exception(self, mock_logger, mock_time, mock_datetime):
        """
        Test schedule_bookings warns and continues when re-authentication throws an exception.
        """
        # Mock current time to simulate a future execution
        mock_now = datetime(2024, 1, 8, 9, 0, 0, tzinfo=TZ)  # Current time
        mock_execution_time = datetime(2024, 1, 8, 10, 0, 0, tzinfo=TZ)  # 1 hour later

        # Mock datetime.now() to return different values for each call
        mock_datetime.now.side_effect = [
            mock_now,  # First call - initial time check
            mock_execution_time,  # Second call - after exception, time has "advanced"
        ]

        mock_bot = MagicMock()

        # Mock the re-authentication to raise an exception
        mock_bot.ensure_logged_in.side_effect = Exception("Network error")

        config = make_config([ClassSpec("Yoga", MONDAY, time(9, 0))], execution=WeeklyTime(MONDAY, time(10, 0)))

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
        reauth_sleep = time_until_execution - 60
        remaining_time = 0  # Should be 0 since second datetime.now returns execution_time

        # Expected sleep calls in the correct order
        expected_sleep_calls = [
            call(reauth_sleep),
            call(remaining_time),
            call(10),
        ]
        mock_time.sleep.assert_has_calls(expected_sleep_calls, any_order=False)

        # Assert re-authentication was attempted
        mock_bot.ensure_logged_in.assert_called_once_with()

        # Assert warning was logged
        mock_logger.warning.assert_called_with("Re-authentication failed before booking execution with Network error.")

    @patch("pysportbot.service.booking.logger")
    def test_attempt_booking_success(self, mock_logger):
        """
        If matching_slots is found, attempt_booking should succeed on the first try.
        """
        mock_bot = MagicMock()
        start = datetime(2024, 1, 17, 18, 0, tzinfo=TZ)

        attempt_booking(bot=mock_bot, activity="Yoga", start=start, retry_attempts=3, retry_delay=1)

        # The bot is asked for the aware start time, exactly once
        mock_bot.book.assert_called_once_with(activity="Yoga", start=start)

    @patch("pysportbot.service.booking.logger")
    def test_attempt_booking_no_matching_slots(self, mock_logger):
        """
        If no matching slot is found, attempt_booking should call the bot.book()
        method, which will raise an exception internally, and log warnings on each attempt.
        """
        mock_bot = MagicMock()
        # Mock the bot.book method to simulate no matching slot
        error = SlotNotFoundError("Yoga", "2024-01-17 18:00:00")
        mock_bot.book.side_effect = error

        attempt_booking(
            bot=mock_bot,
            activity="Yoga",
            start=datetime(2024, 1, 17, 18, 0, tzinfo=TZ),
            retry_attempts=2,
            retry_delay=0,
        )

        # Check that book() was called twice (retry_attempts = 2)
        self.assertEqual(mock_bot.book.call_count, 2)

        # On the final attempt, ensure the correct error message was logged
        last_warning = mock_logger.warning.call_args_list[-1][0][0]
        self.assertIn(str(error), last_warning)
        mock_logger.error.assert_called_once_with(
            "Failed to book 'Yoga' on Wednesday 2024-01-17 at 18:00 after 2 attempts."
        )

    @patch("pysportbot.service.booking.logger")
    def test_attempt_booking_slot_already_booked(self, mock_logger):
        """
        If the slot is already booked, abort further retries.
        """
        mock_bot = MagicMock()
        # First attempt raises 'slot already booked', so we skip subsequent attempts
        mock_bot.book.side_effect = [SlotAlreadyBookedError("123", 5)]

        attempt_booking(
            bot=mock_bot,
            activity="Yoga",
            start=datetime(2024, 1, 17, 18, 0, tzinfo=TZ),
            retry_attempts=3,
            retry_delay=1,
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

        config = make_config(
            [
                ClassSpec("Yoga", MONDAY, time(9, 0)),
                ClassSpec("Boxing", TUESDAY, time(10, 0)),
            ]
        )

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
        self.assertEqual(mock_executor_instance.submit.call_count, len(config.classes))
        # as_completed was called with the dictionary of futures
        # but we only need to confirm it wasn't stuck
        self.assertTrue(mock_as_completed.called)


class TestServiceRun(unittest.TestCase):
    """
    Tests for the service.py 'run_service' function.
    """

    @patch("pysportbot.service.service.validate_activities")
    @patch("pysportbot.service.service.schedule_bookings")
    @patch("pysportbot.service.service.SportBot")
    def test_run_service_success(self, mock_sportbot_class, mock_schedule_bookings, mock_validate_activities):
        """
        If config is valid, run_service should do the full workflow:
        login, validate activities, schedule bookings, etc.
        """
        config = make_config([ClassSpec("Yoga", MONDAY, time(10, 0))])

        run_service(
            config,
            booking_delay=10,
            retry_attempts=2,
            retry_delay=1,
            time_zone="Europe/Madrid",
            log_level="DEBUG",
        )

        mock_sportbot_class.assert_called_once_with(log_level="DEBUG", time_zone="Europe/Madrid")

        bot_instance = mock_sportbot_class.return_value
        bot_instance.login.assert_called_once_with("test@example.com", "pass", "my-gim")
        mock_validate_activities.assert_called_once_with(bot_instance, config)
        # One thread per class when uncapped
        mock_schedule_bookings.assert_called_once_with(bot_instance, config, 10, 2, 1, "Europe/Madrid", 1)

    @patch("pysportbot.service.service.validate_activities")
    @patch("pysportbot.service.service.schedule_bookings")
    @patch("pysportbot.service.service.SportBot")
    def test_run_service_thread_count(self, mock_sportbot_class, mock_schedule_bookings, mock_validate_activities):
        """
        The pool has one thread per class, capped by max_threads.
        """
        config = make_config([ClassSpec(f"Class {i}", MONDAY, time(10, i)) for i in range(5)])

        for max_threads, expected in [(None, 5), (2, 2), (10, 5)]:
            with self.subTest(max_threads=max_threads):
                mock_schedule_bookings.reset_mock()
                run_service(config, max_threads=max_threads)
                self.assertEqual(mock_schedule_bookings.call_args.args[-1], expected)

    @patch("pysportbot.service.service.SportBot")
    def test_run_service_rejects_invalid_max_threads(self, mock_sportbot_class):
        config = make_config([ClassSpec("Yoga", MONDAY, time(10, 0))])

        for max_threads in (0, -1):
            with self.subTest(max_threads=max_threads), self.assertRaisesRegex(ValueError, "max_threads"):
                run_service(config, max_threads=max_threads)
        mock_sportbot_class.assert_not_called()

    @patch("pysportbot.service.service.schedule_bookings")
    @patch("pysportbot.service.service.SportBot")
    def test_run_service_unknown_activity(self, mock_sportbot_class, mock_schedule_bookings):
        """
        If an activity does not exist, run_service raises ConfigError before scheduling.
        """
        mock_sportbot_class.return_value.activities.return_value = [Activity(id=101, name="Yoga", category_id=10)]
        config = make_config([ClassSpec("CrossFit", MONDAY, time(18, 0))])

        with self.assertRaises(ConfigError) as ctx:
            run_service(config)

        self.assertIn("'CrossFit'", str(ctx.exception))
        self.assertIn("Yoga", str(ctx.exception))
        mock_schedule_bookings.assert_not_called()


if __name__ == "__main__":
    unittest.main()
