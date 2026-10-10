import logging
from importlib.metadata import PackageNotFoundError, version

from .exceptions import (
    ActivityNotFoundError,
    APIError,
    AuthenticationError,
    BookingError,
    CancellationError,
    CentreNotFoundError,
    ConfigError,
    NotLoggedInError,
    SlotAlreadyBookedError,
    SlotFullError,
    SlotNotBookableYetError,
    SlotNotFoundError,
    SlotUnavailableError,
    SportBotError,
)
from .models import Activity, Centre, Slot
from .sportbot import SportBot

# Silence pysportbot by default; SportBot() or configure_logging() opt into output
logging.getLogger(__name__).addHandler(logging.NullHandler())

try:
    __version__ = version("pysportbot")
except PackageNotFoundError:  # pragma: no cover - only when run from a source tree that is not installed
    __version__ = "0+unknown"

__all__ = [
    "APIError",
    "Activity",
    "ActivityNotFoundError",
    "AuthenticationError",
    "BookingError",
    "CancellationError",
    "Centre",
    "CentreNotFoundError",
    "ConfigError",
    "NotLoggedInError",
    "Slot",
    "SlotAlreadyBookedError",
    "SlotFullError",
    "SlotNotBookableYetError",
    "SlotNotFoundError",
    "SlotUnavailableError",
    "SportBot",
    "SportBotError",
    "__version__",
]
