import logging
import threading
from datetime import datetime
from typing import ClassVar, Optional

import pytz

from .errors import ErrorMessages


class ColorFormatter(logging.Formatter):
    """Custom formatter to add color-coded log levels and thread information,
    while aligning log levels in the output as `[INFO]    message`.
    """

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

    # The longest built-in level is WARNING = 7 letters => "[WARNING]" is 0 characters
    # so let's set this to 9 to align them nicely.
    _MAX_BRACKET_LEN = 9

    def __init__(self, fmt: str, datefmt: str, tz: pytz.BaseTzInfo, include_threads: bool = False) -> None:
        """
        Initialize the formatter with a specific timezone and optional thread formatting.

        Args:
            fmt (str): The log message format.
            datefmt (str): The date format.
            tz (pytz.BaseTzInfo): The timezone for log timestamps.
            include_threads (bool): Whether to include thread info in logs.
        """
        super().__init__(fmt, datefmt)
        self.timezone = tz
        self.include_threads = include_threads
        self.thread_colors: dict[str, str] = {}  # Initialize empty dictionary

    def formatTime(self, record: logging.LogRecord, datefmt: Optional[str] = None) -> str:
        """
        Override to format the time in the desired timezone.
        """
        record_time = datetime.fromtimestamp(record.created, self.timezone)
        return record_time.strftime(datefmt or self.default_time_format)

    def format(self, record: logging.LogRecord) -> str:
        """
        Format the log record with color-coded (and bracketed) log levels, plus optional thread info.
        Example final output: "[INFO]    message".
        """
        raw_level_name = record.levelname

        # Build the bracketed level, e.g. "[INFO]"
        bracketed_level = f"[{raw_level_name}]"

        # Pad it to a fixed width (e.g. 10) so shorter levels also line up
        padded_bracketed_level = f"{bracketed_level:<{self._MAX_BRACKET_LEN}}"

        # Colorize the padded bracketed string
        color = self.COLORS.get(raw_level_name, self.COLORS["RESET"])
        colored_bracketed = f"{color}{padded_bracketed_level}{self.COLORS['RESET']}"

        # We'll store this in a custom attribute
        record.colored_bracketed_level = colored_bracketed

        # Handle the thread info if requested
        if self.include_threads:
            thread_name = threading.current_thread().name
            if thread_name == "MainThread":
                record.thread_info = ""
            else:
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
        timezone (str): The desired timezone for log timestamps (e.g., 'Europe/Madrid').
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(logging._nameToLevel[level.upper()])

    # Prevent adding multiple handlers if already set up
    if not root_logger.hasHandlers():
        handler = logging.StreamHandler()
        handler.setLevel(logging._nameToLevel[level.upper()])

        tz = pytz.timezone(timezone)

        # IMPORTANT: Note the %(colored_bracketed_level)s placeholder
        fmt = "[%(asctime)s] %(colored_bracketed_level)s %(thread_info)s%(message)s"

        formatter = ColorFormatter(fmt=fmt, datefmt="%Y-%m-%d %H:%M:%S", tz=tz, include_threads=True)
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
    """
    return logging.getLogger(name)
