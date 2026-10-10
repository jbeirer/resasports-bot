#!/usr/bin/env python3

import argparse
import logging
import sys
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pysportbot.exceptions import ConfigError

from .config import load_config
from .service import run_service


def _int(value: str) -> int:
    try:
        return int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid integer: '{value}'") from None


def _positive_int(value: str) -> int:
    n = _int(value)
    if n < 1:
        raise argparse.ArgumentTypeError(f"must be a positive integer, got {n}")
    return n


def _non_negative_int(value: str) -> int:
    n = _int(value)
    if n < 0:
        raise argparse.ArgumentTypeError(f"must not be negative, got {n}")
    return n


def _max_threads(value: str) -> int | None:
    """Parse --max-threads: a positive integer, or the legacy -1 for no limit."""
    return None if _int(value) == -1 else _positive_int(value)


def _time_zone(value: str) -> str:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        raise argparse.ArgumentTypeError(f"unknown time zone '{value}', e.g. 'Europe/Madrid'") from None
    return value


def _log_level(value: str) -> str:
    if value.upper() not in logging.getLevelNamesMapping():
        raise argparse.ArgumentTypeError(f"unknown log level '{value}', use DEBUG, INFO, WARNING, ERROR or CRITICAL")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the pysportbot as a service.",
        epilog="The SPORTBOT_EMAIL, SPORTBOT_PASSWORD and SPORTBOT_CENTRE env vars override the config file.",
    )
    parser.add_argument("--config", type=str, required=True, help="Path to the JSON or TOML configuration file.")
    parser.add_argument(
        "--booking-delay", type=_non_negative_int, default=0, help="Global booking delay in seconds before booking."
    )
    parser.add_argument("--retry-attempts", type=_positive_int, default=3, help="Number of booking attempts per class.")
    parser.add_argument(
        "--retry-delay", type=_non_negative_int, default=5, help="Delay in seconds between retries for bookings."
    )
    parser.add_argument("--time-zone", type=_time_zone, default="Europe/Madrid", help="Timezone for the service.")
    parser.add_argument("--log-level", type=_log_level, default="INFO", help="Logging level for the service.")
    parser.add_argument(
        "--max-threads",
        type=_max_threads,
        default=None,
        help="Maximum number of classes booked in parallel. By default, all classes are booked in parallel.",
    )
    args = parser.parse_args()

    try:
        config = load_config(args.config)
        run_service(
            config,
            booking_delay=args.booking_delay,
            retry_attempts=args.retry_attempts,
            retry_delay=args.retry_delay,
            time_zone=args.time_zone,
            log_level=args.log_level,
            max_threads=args.max_threads,
        )
    except ConfigError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
