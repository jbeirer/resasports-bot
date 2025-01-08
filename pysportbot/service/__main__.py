#!/usr/bin/env python3

import argparse
from typing import Any, Dict

from .config_loader import load_config
from .service import run_service


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the pysportbot as a service.")
    parser.add_argument("--config", type=str, required=True, help="Path to the JSON configuration file.")
    parser.add_argument("--booking-delay", type=int, default=0, help="Global booking delay in seconds before booking.")
    parser.add_argument("--retry-attempts", type=int, default=3, help="Number of retry attempts for bookings.")
    parser.add_argument("--retry-delay", type=int, default=5, help="Delay in seconds between retries for bookings.")
    parser.add_argument("--time-zone", type=str, default="Europe/Madrid", help="Timezone for the service.")
    parser.add_argument("--log-level", type=str, default="INFO", help="Logging level for the service.")
    parser.add_argument(
        "--max-threads",
        type=int,
        default=-1,
        help="Maxium number of threads to use for booking. -1 defaults to all available cores.",
    )
    args = parser.parse_args()

    config: Dict[str, Any] = load_config(args.config)
    run_service(
        config,
        booking_delay=args.booking_delay,
        retry_attempts=args.retry_attempts,
        retry_delay=args.retry_delay,
        time_zone=args.time_zone,
        log_level=args.log_level,
        max_threads=args.max_threads,
    )


if __name__ == "__main__":
    main()
