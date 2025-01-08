import logging
import unittest
from datetime import datetime
from io import StringIO
from unittest.mock import patch

import pytz

# Import the logger setup functions and classes
from pysportbot.utils.logger import ColorFormatter, get_logger, set_log_level, setup_logger


class TestLogger(unittest.TestCase):
    def setUp(self):
        """Set up a test logging configuration using the root logger."""
        self.log_stream = StringIO()  # Capture logging output
        self.initial_timezone = pytz.timezone("Europe/Madrid")

        # Configure a test handler with ColorFormatter.
        self.handler = logging.StreamHandler(self.log_stream)
        self.formatter = ColorFormatter(
            "[%(asctime)s] %(colored_bracketed_level)s %(thread_info)s%(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            tz=self.initial_timezone,
            include_threads=True,
        )
        self.handler.setFormatter(self.formatter)
        self.handler.setLevel(logging.NOTSET)  # Let the logger handle the level

        # Get the root logger and configure it
        self.root_logger = logging.getLogger()
        self.root_logger.setLevel(logging.INFO)
        # Remove existing handlers to prevent duplicate logs
        self.root_logger.handlers = []
        self.root_logger.addHandler(self.handler)

    def tearDown(self):
        """Clean up by removing the handler."""
        self.root_logger.removeHandler(self.handler)
        self.log_stream.close()

    def test_default_timezone(self):
        """Test the logger defaults to Europe/Madrid time zone."""
        setup_logger(level="INFO", timezone="Europe/Madrid")
        self.root_logger.info("Test default time zone.")

        self.handler.flush()
        log_output = self.log_stream.getvalue().strip()
        timestamp_str = log_output.split("]")[0].strip("[]")
        log_time = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")

        # Convert log time to Europe/Madrid time zone
        log_time_with_tz = self.initial_timezone.localize(log_time)
        now_madrid = datetime.now(self.initial_timezone)

        # Assert timestamps are almost equal
        self.assertAlmostEqual(log_time_with_tz.timestamp(), now_madrid.timestamp(), delta=2)

    def test_log_levels(self):
        """Test logs are filtered correctly by level."""
        setup_logger(level="WARNING", timezone="Europe/Madrid")
        self.root_logger.debug("This should not appear.")
        self.root_logger.info("This should not appear.")
        self.root_logger.warning("This is a warning.")
        self.root_logger.error("This is an error.")

        self.handler.flush()
        log_output = self.log_stream.getvalue().strip()

        # Assert only WARNING and ERROR levels are logged
        self.assertIn("This is a warning.", log_output)
        self.assertIn("This is an error.", log_output)
        self.assertNotIn("This should not appear.", log_output)

    def test_color_formatting(self):
        """
        Test log levels include correct color codes, matching the actual padding:
          - [INFO]   => 3 trailing spaces
          - [WARNING] => 0 trailing spaces
          - [ERROR]  => 2 trailing spaces
        """
        setup_logger(level="INFO", timezone="Europe/Madrid")
        self.root_logger.info("Info message")
        self.root_logger.warning("Warning message")
        self.root_logger.error("Error message")

        self.handler.flush()
        log_output = self.log_stream.getvalue()

        # Verify the bracketed level strings exactly:
        self.assertIn("\033[92m[INFO]   \033[0m", log_output)  # Green for [INFO]
        self.assertIn("\033[93m[WARNING]\033[0m", log_output)  # Yellow for [WARNING]
        self.assertIn("\033[91m[ERROR]  \033[0m", log_output)  # Red for [ERROR]

    def test_invalid_log_level(self):
        """Test that invalid log levels raise a ValueError."""
        with self.assertRaises(ValueError):
            set_log_level("INVALID_LEVEL")

    def test_no_duplicate_handlers(self):
        """Test multiple calls to setup_logger do not add duplicate handlers."""
        setup_logger(level="INFO", timezone="Europe/Madrid")
        setup_logger(level="INFO", timezone="Europe/Madrid")  # Call again

        self.root_logger.info("Test for duplicate handlers.")

        self.handler.flush()
        log_output = self.log_stream.getvalue()

        # Assert message appears only once
        self.assertEqual(log_output.count("Test for duplicate handlers."), 1)

    @patch("pysportbot.utils.logger.datetime")
    def test_custom_timezone(self, mock_datetime):
        """Test the logger outputs timestamps in a custom time zone."""
        # Define a fixed current time
        fixed_time_naive = datetime(2024, 12, 31, 14, 12, 23)
        timezone_ny = pytz.timezone("America/New_York")
        fixed_time = timezone_ny.localize(fixed_time_naive)

        # Mock datetime.now() to return the fixed_time
        mock_datetime.now.return_value = fixed_time
        # Mock datetime.fromtimestamp() to return the fixed_time
        mock_datetime.fromtimestamp.return_value = fixed_time
        # Allow datetime.strptime() to work normally
        mock_datetime.strptime.side_effect = datetime.strptime

        # Set up logger with America/New_York timezone
        setup_logger(level="INFO", timezone="America/New_York")
        # Update the formatter's timezone
        self.formatter.tz = timezone_ny
        self.root_logger.info("Test custom time zone.")

        self.handler.flush()
        log_output = self.log_stream.getvalue().strip()
        timestamp_str = log_output.split("]")[0].strip("[]")
        log_time = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")

        # Assign timezone to log_time
        log_time_with_tz = timezone_ny.localize(log_time)
        now_ny = fixed_time

        # Calculate the absolute difference in seconds
        time_difference = abs((now_ny - log_time_with_tz).total_seconds())

        # Assert that the log_time matches the fixed_time exactly
        self.assertEqual(time_difference, 0, f"Time difference is not zero: {time_difference} seconds")

    def test_named_logger(self):
        """Test that a named logger is correctly retrieved."""
        setup_logger(level="INFO", timezone="Europe/Madrid")
        logger = get_logger("test_named_logger")
        logger.setLevel(logging.INFO)
        logger.addHandler(self.handler)
        logger.info("Test named logger.")

        self.handler.flush()
        log_output = self.log_stream.getvalue()

        # The logger also pads "[INFO]" to 9 chars => "[INFO]   "
        self.assertIn("\033[92m[INFO]   \033[0m Test named logger.", log_output)


if __name__ == "__main__":
    unittest.main()
