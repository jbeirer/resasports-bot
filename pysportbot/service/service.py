import time
from typing import Any, Dict

import schedule

from pysportbot import SportBot
from pysportbot.utils.logger import get_logger

from .booking import schedule_bookings
from .config_validator import validate_config_and_activities

logger = get_logger(__name__)


def run_service(
    config: Dict[str, Any],
    offset_seconds: int,
    retry_attempts: int,
    retry_delay_minutes: int,
    time_zone: str = "Europe/Madrid",
) -> None:
    bot = SportBot()
    bot.login(config["email"], config["password"], config["centre"])

    validate_config_and_activities(config, bot)

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
