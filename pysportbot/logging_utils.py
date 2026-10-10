import logging
import os
from datetime import datetime
from typing import ClassVar, TextIO
from zoneinfo import ZoneInfo

# Every module logs through a child of this logger, via logging.getLogger(__name__)
PACKAGE_LOGGER = "pysportbot"

LOG_FORMAT = "[%(asctime)s] %(colored_bracketed_level)s %(thread_info)s%(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Marks the handler installed by configure_logging, so repeated calls update it instead of adding another
_HANDLER_TAG = "_pysportbot_handler"


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

    def __init__(
        self, fmt: str, datefmt: str, tz: ZoneInfo, include_threads: bool = False, use_color: bool = True
    ) -> None:
        """
        Initialize the formatter with a specific timezone and optional thread formatting.

        Args:
            fmt (str): The log message format.
            datefmt (str): The date format.
            tz (ZoneInfo): The timezone for log timestamps.
            include_threads (bool): Whether to include thread info in logs.
            use_color (bool): Whether to wrap levels and thread names in ANSI color codes.
        """
        super().__init__(fmt, datefmt)
        self.timezone = tz
        self.include_threads = include_threads
        self.use_color = use_color
        self.thread_colors: dict[str, str] = {}  # Initialize empty dictionary

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        """
        Override to format the time in the desired timezone.
        """
        record_time = datetime.fromtimestamp(record.created, self.timezone)
        return record_time.strftime(datefmt or self.default_time_format)

    def _colorize(self, text: str, color: str) -> str:
        return f"{color}{text}{self.COLORS['RESET']}" if self.use_color else text

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

        # Colorize the padded bracketed string and store it in a custom attribute
        color = self.COLORS.get(raw_level_name, self.COLORS["RESET"])
        record.colored_bracketed_level = self._colorize(padded_bracketed_level, color)

        # Handle the thread info if requested
        thread_name = record.threadName
        if not self.include_threads or thread_name is None or thread_name == "MainThread":
            record.thread_info = ""
        else:
            if thread_name not in self.thread_colors:
                color_index = len(self.thread_colors) % len(self.THREAD_COLORS)
                self.thread_colors[thread_name] = self.THREAD_COLORS[color_index]

            simplified_thread_name = thread_name.split("_")[-1]
            thread_label = self._colorize(f"Thread {simplified_thread_name}", self.thread_colors[thread_name])
            record.thread_info = f"[{thread_label}] "

        return super().format(record)


def _use_color(stream: TextIO) -> bool:
    """
    Decide whether to emit ANSI colors on `stream`.

    A non-empty `NO_COLOR` always disables colors (https://no-color.org). Otherwise a non-empty `FORCE_COLOR`
    enables them, e.g. in CI logs that render ANSI codes. Otherwise colors are used only on a TTY.
    """
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    isatty = getattr(stream, "isatty", None)
    return bool(isatty and isatty())


def _to_level(level: str) -> int:
    """
    Convert a level name such as "info" to its numeric value.

    Raises:
        ValueError: If the level name is unknown.
    """
    levels = logging.getLevelNamesMapping()
    try:
        return levels[level.upper()]
    except KeyError:
        raise ValueError(f"Invalid logging level: {level}. Valid levels are {', '.join(levels)}.") from None


def _find_handler(logger: logging.Logger) -> logging.StreamHandler | None:
    """Return the handler previously installed by configure_logging, if any."""
    for handler in logger.handlers:
        if getattr(handler, _HANDLER_TAG, False) and isinstance(handler, logging.StreamHandler):
            return handler
    return None


def configure_logging(level: str = "INFO", timezone: str = "Europe/Madrid") -> None:
    """
    Send pysportbot's logs to stderr with color-coded output in the specified timezone.

    Only the "pysportbot" logger is configured; the root logger is left alone. Calling this again updates the
    existing handler instead of adding a second one. The "pysportbot" logger stops propagating to the root logger,
    so messages are not printed twice if the application configures logging as well.

    Args:
        level (str): The desired logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        timezone (str): The desired timezone for log timestamps (e.g., 'Europe/Madrid').

    Raises:
        ValueError: If the provided logging level is invalid.
    """
    numeric_level = _to_level(level)
    tz = ZoneInfo(timezone)

    logger = logging.getLogger(PACKAGE_LOGGER)
    handler = _find_handler(logger)
    if handler is None:
        handler = logging.StreamHandler()
        setattr(handler, _HANDLER_TAG, True)
        logger.addHandler(handler)

    formatter = ColorFormatter(
        fmt=LOG_FORMAT, datefmt=DATE_FORMAT, tz=tz, include_threads=True, use_color=_use_color(handler.stream)
    )
    handler.setFormatter(formatter)

    logger.setLevel(numeric_level)
    logger.propagate = False


def set_log_level(level: str) -> None:
    """
    Change the logging level of the "pysportbot" logger.

    Args:
        level (str): The desired logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).

    Raises:
        ValueError: If the provided logging level is invalid.
    """
    logging.getLogger(PACKAGE_LOGGER).setLevel(_to_level(level))
