import time
from typing import Any, Dict

import schedule

from pysportbot import SportBot
from pysportbot.utils.logger import get_logger

from .booking import schedule_bookings
from .config_validator import validate_activities, validate_config


def run_service(
    config: Dict[str, Any],
    offset_seconds: int,
    retry_attempts: int,
    retry_delay_minutes: int,
    time_zone: str = "Europe/Madrid",
    log_level: str = "INFO",
) -> None:
    # Initialize service logger
    logger = get_logger(__name__)
    logger.setLevel(log_level)

    # Validate the configuration file
    validate_config(config)
    # Initialize the SportBot instance
    bot = SportBot(log_level=log_level, time_zone=time_zone)
    bot.login(config["email"], config["password"], config["centre"])

    # Validate the activities in the configuration file
    validate_activities(bot, config)

    for cls in config["classes"]:
        schedule_bookings(
            bot,
            config,
            cls,
            offset_seconds,
            retry_attempts,
            retry_delay_minutes,
            time_zone,
        )

    if schedule.jobs:
        logger.info("Weekly bookings scheduled. Running the scheduler...")
        while True:
            schedule.run_pending()
            time.sleep(1)
