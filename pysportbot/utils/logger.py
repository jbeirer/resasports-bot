import logging
from typing import ClassVar

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


def setup_logger(level: str = "INFO") -> None:
    """
    Configure the root logger with color-coded output.

    Args:
        level (str): The desired logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(logging._nameToLevel[level.upper()])

    if not root_logger.hasHandlers():  # Avoid duplicate handlers
        handler = logging.StreamHandler()
        handler.setLevel(logging._nameToLevel[level.upper()])
        formatter = ColorFormatter("[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
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
