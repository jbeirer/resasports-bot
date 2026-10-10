import unittest
from datetime import date, datetime, time
from unittest.mock import patch
from zoneinfo import ZoneInfo

from pysportbot import Activity
from pysportbot.exceptions import ConfigError
from pysportbot.service.config import ClassSpec, ServiceConfig, WeeklyTime
from pysportbot.service.retry import RetryPolicy
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

        results = run_service(
            config,
            booking_delay=10,
            retry_attempts=2,
            retry_delay=1,
            poll_interval=0.25,
            poll_window=30,
            time_zone="Europe/Madrid",
            log_level="DEBUG",
        )

        mock_sportbot_class.assert_called_once_with(log_level="DEBUG", time_zone="Europe/Madrid")

        bot_instance = mock_sportbot_class.return_value
        bot_instance.login.assert_called_once_with("test@example.com", "pass", "my-gim")
        mock_validate_activities.assert_called_once_with(bot_instance, config)
        # One thread per class when uncapped
        mock_schedule_bookings.assert_called_once_with(
            bot_instance,
            config,
            RetryPolicy(retry_attempts=2, retry_delay=1, poll_interval=0.25, poll_window=30),
            booking_delay=10,
            time_zone="Europe/Madrid",
            max_threads=1,
            dry_run=False,
        )
        self.assertIs(results, mock_schedule_bookings.return_value)

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
                self.assertEqual(mock_schedule_bookings.call_args.kwargs["max_threads"], expected)

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
