import logging
from datetime import datetime
from typing import Any

from pysportbot import SportBot
from pysportbot.exceptions import ConfigError

logger = logging.getLogger(__name__)

DAY_MAP = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}
VALID_DAYS = "Monday, Tuesday, Wednesday, Thursday, Friday, Saturday, Sunday"


def validate_config(config: dict[str, Any]) -> None:
    """
    Validate the overall configuration structure and values.

    Args:
        config (Dict[str, Any]): Configuration dictionary.

    Raises:
        ConfigError: If the configuration is invalid.
    """

    def raise_invalid_booking_format_error() -> None:
        """Helper function to raise an error for invalid booking_execution format."""
        raise ConfigError("Invalid booking_execution format. Use 'now' or 'Day HH:MM:SS'.")

    required_keys = ["email", "password", "centre", "classes", "booking_execution"]
    for key in required_keys:
        if key not in config:
            raise ConfigError(f"Missing required key in config: {key}")

    # Validate global booking_execution
    if config["booking_execution"] != "now":
        try:
            day_and_time = config["booking_execution"].split()
            if len(day_and_time) != 2:
                raise_invalid_booking_format_error()

            exec_day, exec_time = day_and_time
            datetime.strptime(exec_time, "%H:%M:%S")
        except ValueError:
            raise_invalid_booking_format_error()

        _validate_day(exec_day)

    # Validate individual class definitions
    for cls in config["classes"]:
        if "activity" not in cls or "class_day" not in cls or "class_time" not in cls:
            raise ConfigError("Each class must include 'activity', 'class_day', 'class_time'")

        _validate_day(cls["class_day"])

        try:
            datetime.strptime(cls["class_time"], "%H:%M:%S")
        except (TypeError, ValueError) as err:
            raise ConfigError(
                f"Invalid class_time '{cls['class_time']}'. Use the 24-hour format 'HH:MM:SS', e.g. '18:00:00'."
            ) from err


def _validate_day(day: Any) -> None:
    """
    Validate a weekday name using the same normalization as the scheduler.

    Raises:
        ConfigError: If the day is not a valid weekday name.
    """
    if not isinstance(day, str) or day.lower().strip() not in DAY_MAP:
        raise ConfigError(f"Invalid day '{day}'. Valid days are: {VALID_DAYS} (case-insensitive).")


def validate_activities(bot: SportBot, config: dict[str, Any]) -> None:
    """
    Validate that all activities specified in the configuration exist.

    Args:
        bot (SportBot): The SportBot instance.
        config (Dict[str, Any]): Configuration dictionary.

    Raises:
        ConfigError: If an activity is not found.
    """
    logger.info("Fetching available activities for validation...")
    available_activities = bot.activities()
    available_activity_names = set(available_activities["name_activity"].tolist())

    logger.debug(f"Available activities: {available_activity_names}")

    for cls in config["classes"]:
        activity_name = cls["activity"]
        if activity_name not in available_activity_names:
            raise ConfigError(
                f"No activity found with the name '{activity_name}'. "
                f"Available activities are: {', '.join(sorted(available_activity_names))}."
            )

    logger.info("All activities in the configuration file have been validated.")
