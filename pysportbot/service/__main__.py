#!/usr/bin/env python3

import argparse
from typing import Any, Dict

from .config_loader import load_config
from .service import run_service


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the pysportbot as a service.")
    parser.add_argument("--config", type=str, required=True, help="Path to the JSON configuration file.")
    parser.add_argument("--booking-delay", type=int, default=5, help="Global booking delay in seconds before booking.")
    parser.add_argument("--retry-attempts", type=int, default=3, help="Number of retry attempts for weekly bookings.")
    parser.add_argument(
        "--retry-delay", type=int, default=30, help="Delay in seconds between retries for weekly bookings."
    )
    parser.add_argument("--time-zone", type=str, default="Europe/Madrid", help="Timezone for the service.")
    parser.add_argument("--log-level", type=str, default="INFO", help="Logging level for the service.")
    args = parser.parse_args()

    config: Dict[str, Any] = load_config(args.config)
    run_service(
        config,
        booking_delay=args.booking_delay,
        retry_attempts=args.retry_attempts,
        retry_delay=args.retry_delay,
        time_zone=args.time_zone,
        log_level=args.log_level,
    )


if __name__ == "__main__":
    main()
