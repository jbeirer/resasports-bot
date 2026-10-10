#!/usr/bin/env python3

import argparse
import sys

from pysportbot.exceptions import ConfigError

from .config import load_config
from .service import run_service


def _max_threads(value: str) -> int | None:
    """Parse --max-threads: a positive integer, or the legacy -1 for no limit."""
    try:
        n = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid integer: '{value}'") from None
    if n == -1:
        return None
    if n < 1:
        raise argparse.ArgumentTypeError(f"must be a positive integer, got {n}")
    return n


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the pysportbot as a service.",
        epilog="The SPORTBOT_EMAIL, SPORTBOT_PASSWORD and SPORTBOT_CENTRE env vars override the config file.",
    )
    parser.add_argument("--config", type=str, required=True, help="Path to the JSON or TOML configuration file.")
    parser.add_argument("--booking-delay", type=int, default=0, help="Global booking delay in seconds before booking.")
    parser.add_argument("--retry-attempts", type=int, default=3, help="Number of retry attempts for bookings.")
    parser.add_argument("--retry-delay", type=int, default=5, help="Delay in seconds between retries for bookings.")
    parser.add_argument("--time-zone", type=str, default="Europe/Madrid", help="Timezone for the service.")
    parser.add_argument("--log-level", type=str, default="INFO", help="Logging level for the service.")
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
