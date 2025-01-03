import logging
import threading
from datetime import datetime
from typing import ClassVar, Optional

import pytz

from .errors import ErrorMessages


class ColorFormatter(logging.Formatter):
    """Custom formatter to add color-coded log levels and thread information."""

    COLORS: ClassVar[dict[str, str]] = {
        "DEBUG": "\033[94m",  # Blue
        "INFO": "\033[92m",  # Green
        "WARNING": "\033[93m",  # Yellow
        "ERROR": "\033[91m",  # Red
        "RESET": "\033[0m",  # Reset
    }

    THREAD_COLORS: ClassVar[list[str]] = [
        "\033[95m",  # Magenta
        "\033[96m",  # Cyan
        "\033[93m",  # Yellow
        "\033[92m",  # Green
        "\033[94m",  # Blue
        "\033[90m",  # Gray
        "\033[37m",  # White
        "\033[33m",  # Orange
        "\033[35m",  # Purple
    ]

    thread_colors: dict[str, str]

    def __init__(self, fmt: str, datefmt: str, tz: pytz.BaseTzInfo, include_threads: bool = False) -> None:
        """
        Initialize the formatter with a specific timezone and optional thread formatting.

        Args:
            fmt (str): The log message format.
            datefmt (str): The date format.
            tz (pytz.BaseTzInfo): The timezone for log timestamps.
            include_threads (bool): Whether to include thread information in logs.
        """
        super().__init__(fmt, datefmt)
        self.timezone = tz
        self.include_threads = include_threads
        self.thread_colors = {}  # Initialize as an empty dictionary

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
        Format the log record with color-coded log levels and optional thread information.

        Args:
            record (logging.LogRecord): The log record to format.

        Returns:
            str: The formatted log record as a string.
        """
        color = self.COLORS.get(record.levelname, self.COLORS["RESET"])
        record.levelname = f"{color}{record.levelname}{self.COLORS['RESET']}"

        if self.include_threads:
            thread_name = threading.current_thread().name
            if thread_name == "MainThread":
                # Skip adding thread info for the main thread
                record.thread_info = ""
            else:
                # Map thread names to simplified format (Thread 0, Thread 1, etc.)
                if thread_name not in self.thread_colors:
                    color_index = len(self.thread_colors) % len(self.THREAD_COLORS)
                    self.thread_colors[thread_name] = self.THREAD_COLORS[color_index]

                thread_color = self.thread_colors[thread_name]
                simplified_thread_name = thread_name.split("_")[-1]
                record.thread_info = f"[{thread_color}Thread {simplified_thread_name}{self.COLORS['RESET']}] "
        else:
            record.thread_info = ""

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

        # Default formatter for the main thread
        thread_formatter = ColorFormatter(
            "[%(asctime)s] [%(levelname)s] %(thread_info)s%(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            tz=tz,
            include_threads=True,
        )

        handler.setFormatter(thread_formatter)
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
