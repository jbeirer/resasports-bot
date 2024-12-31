import logging
from datetime import datetime
from typing import ClassVar, Optional

import pytz

from .errors import ErrorMessages


class ColorFormatter(logging.Formatter):
    """Custom formatter to add color-coded log levels."""

    COLORS: ClassVar[dict[str, str]] = {
        "DEBUG": "\033[94m",  # Blue
        "INFO": "\033[92m",  # Green
        "WARNING": "\033[93m",  # Yellow
        "ERROR": "\033[91m",  # Red
        "RESET": "\033[0m",  # Reset
    }

    def __init__(self, fmt: str, datefmt: str, tz: pytz.BaseTzInfo) -> None:
        """
        Initialize the formatter with a specific timezone.

        Args:
            fmt (str): The log message format.
            datefmt (str): The date format.
            tz (pytz.BaseTzInfo): The timezone for log timestamps.
        """
        super().__init__(fmt, datefmt)
        self.timezone = tz

    def formatTime(self, record: logging.LogRecord, datefmt: Optional[str] = None) -> str:
        """
        Override to format the time in the desired timezone.

        Args:
            record (logging.LogRecord): The log record.
            datefmt (Optional[str]): The date format.

        Returns:
            str: The formatted timestamp.
        """
        record_time = datetime.fromtimestamp(record.created, self.timezone)
        return record_time.strftime(datefmt or self.default_time_format)

    def format(self, record: logging.LogRecord) -> str:
        """
        Format the log record with color-coded log levels.

        Args:
            record (logging.LogRecord): The log record to format.

        Returns:
            str: The formatted log record as a string.
        """
        color = self.COLORS.get(record.levelname, self.COLORS["RESET"])
        record.levelname = f"{color}{record.levelname}{self.COLORS['RESET']}"
        return super().format(record)


def setup_logger(level: str = "INFO", timezone: str = "Europe/Madrid") -> None:
    """
    Configure the root logger with color-coded output in the specified timezone.

    Args:
        level (str): The desired logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        timezone (str): The desired timezone for log timestamps (e.g., Europe/Madrid).
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(logging._nameToLevel[level.upper()])

    if not root_logger.hasHandlers():  # Avoid duplicate handlers
        handler = logging.StreamHandler()
        handler.setLevel(logging._nameToLevel[level.upper()])
        tz = pytz.timezone(timezone)
        formatter = ColorFormatter(
            "[%(asctime)s] [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            tz=tz,
        )
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)


def set_log_level(level: str) -> None:
    """
    Change the logging level of the root logger.

    Args:
        level (str): The desired logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).

    Raises:
        ValueError: If the provided logging level is invalid.
    """
    level = level.upper()
    if level not in logging._nameToLevel:
        raise ErrorMessages.invalid_log_level(level)
    logging.getLogger().setLevel(logging._nameToLevel[level])
    logging.info(f"Log level changed to {level}.")


def get_logger(name: str) -> logging.Logger:
    """
    Retrieve a logger by name.

    Args:
        name (str): The name of the logger.

    Returns:
        logging.Logger: The logger instance.
    """
    return logging.getLogger(name)
