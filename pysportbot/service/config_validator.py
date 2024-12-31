from datetime import datetime
from typing import Any, Dict

from pysportbot import SportBot
from pysportbot.utils.errors import ErrorMessages
from pysportbot.utils.logger import get_logger

logger = get_logger(__name__)

DAY_MAP = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}


def validate_config(config: Dict[str, Any]) -> None:
    required_keys = ["email", "password", "centre", "classes"]
    for key in required_keys:
        if key not in config:
            raise ValueError(ErrorMessages.missing_required_key(key))

    for cls in config["classes"]:
        if (
            "activity" not in cls
            or "class_day" not in cls
            or "class_time" not in cls
            or "booking_execution" not in cls
            or "weekly" not in cls
        ):
            raise ValueError(ErrorMessages.invalid_class_definition())

        if cls["weekly"] and cls["booking_execution"] == "now":
            raise ValueError(ErrorMessages.invalid_weekly_now())

        if cls["booking_execution"] != "now":
            day_and_time = cls["booking_execution"].split()
            if len(day_and_time) != 2:
                raise ValueError(ErrorMessages.invalid_booking_execution_format())
            _, exec_time = day_and_time
            try:
                datetime.strptime(exec_time, "%H:%M:%S")
            except ValueError as err:
                raise ValueError(ErrorMessages.invalid_booking_execution_format()) from err


def validate_activities(bot: SportBot, config: Dict[str, Any]) -> None:
    logger.info("Fetching available activities for validation...")
    available_activities = bot.activities()
    available_activity_names = set(available_activities["name_activity"].tolist())

    logger.debug(f"Available activities: {available_activity_names}")

    for cls in config["classes"]:
        activity_name = cls["activity"]
        if activity_name not in available_activity_names:
            raise ValueError(ErrorMessages.activity_not_found(activity_name, list(available_activity_names)))
    logger.info("All activities in the configuration file have been validated.")
