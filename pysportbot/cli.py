"""The `pysportbot` command-line interface."""

import argparse
import getpass
import json
import logging
import math
import os
import sys
from collections.abc import Sequence
from dataclasses import asdict, replace
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests

from . import __version__
from .exceptions import ConfigError, SportBotError
from .logging_utils import PACKAGE_LOGGER, _find_handler, configure_logging
from .models import Slot
from .service import notify
from .service.config import (
    ENV_VARS,
    NOTIFY_ENV_VARS,
    NOTIFY_ON,
    WEEKDAYS,
    NotifySettings,
    load_config,
    notify_settings_from_env,
)
from .service.service import run_service
from .sportbot import SportBot, _parse_start

logger = logging.getLogger(__name__)

DEFAULT_TIME_ZONE = "Europe/Madrid"

EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_USAGE = 2
EXIT_INTERRUPTED = 130


class _UsageError(Exception):
    """Bad input found after parsing, e.g. missing credentials. Exits with code 2."""


class _HideExpectedTracebacks(logging.Filter):
    """Drop the traceback from log records about expected errors; the CLI reports those in one line."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.exc_info and isinstance(record.exc_info[1], SportBotError | requests.RequestException):
            record.exc_info = None
            record.exc_text = None
        return True


_HIDE_EXPECTED_TRACEBACKS = _HideExpectedTracebacks()


# Argument types


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


def _seconds(value: str) -> float:
    try:
        seconds = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid number of seconds: '{value}'") from None
    if not math.isfinite(seconds) or seconds < 0:
        raise argparse.ArgumentTypeError(f"must be a non-negative number of seconds, got {value}")
    return seconds


def _positive_seconds(value: str) -> float:
    seconds = _seconds(value)
    if seconds == 0:
        raise argparse.ArgumentTypeError(f"must be a positive number of seconds, got {value}")
    return seconds


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
    return value.upper()


def _start(value: str) -> datetime:
    try:
        return _parse_start(value)
    except ValueError as e:
        raise argparse.ArgumentTypeError(str(e)) from None


def parse_day(value: str, today: date) -> date:
    """
    Parse a day given as 'YYYY-MM-DD', 'today', 'tomorrow' or an English weekday name.

    A weekday name, such as 'monday' or 'mon', means its next occurrence, where today counts.

    Raises:
        ValueError: If the day is in none of these forms.
    """
    key = value.strip().lower()
    if key == "today":
        return today
    if key == "tomorrow":
        return today + timedelta(days=1)
    if key in WEEKDAYS:
        return today + timedelta(days=(WEEKDAYS[key] - today.weekday()) % 7)
    try:
        return datetime.strptime(key, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError(
            f"invalid day '{value}'. Use 'YYYY-MM-DD', 'today', 'tomorrow' or a weekday name such as 'monday'."
        ) from None


def _today(time_zone: str) -> date:
    return datetime.now(ZoneInfo(time_zone)).date()


# Output


def _format_time(when: datetime, with_date: bool = True) -> str:
    time_format = "%H:%M:%S" if when.second else "%H:%M"
    return when.strftime(f"%Y-%m-%d {time_format}" if with_date else time_format)


def _print_table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> None:
    widths = [max([len(header), *(len(row[i]) for row in rows)]) for i, header in enumerate(headers)]
    for line in (headers, *rows):
        print("  ".join(cell.ljust(width) for cell, width in zip(line, widths, strict=True)).rstrip())


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _print_json(items: Sequence[Any]) -> None:
    print(json.dumps([asdict(item) for item in items], indent=2, ensure_ascii=False, default=_json_default))


def _slot_status(slot: Slot) -> str:
    if slot.cancelled:
        return "cancelled"
    return "full" if slot.is_full else ""


# Commands


def _credentials(args: argparse.Namespace) -> tuple[str, str, str]:
    """
    Read the email and centre from the flags or the env, and the password from the env or an interactive prompt.

    Raises:
        _UsageError: Listing every missing credential.
    """
    # Empty env vars count as unset, as in the service config
    email: str = args.email or os.environ.get(ENV_VARS["email"], "")
    centre: str = args.centre or os.environ.get(ENV_VARS["centre"], "")
    password = os.environ.get(ENV_VARS["password"], "")
    can_prompt = sys.stdin is not None and sys.stdin.isatty()

    missing = []
    if not email:
        missing.append(f"email: pass --email or set {ENV_VARS['email']}.")
    if not centre:
        missing.append(f"centre: pass --centre or set {ENV_VARS['centre']}. Find it with 'pysportbot centres'.")
    if not password and not can_prompt:
        missing.append(f"password: set {ENV_VARS['password']}, or run in a terminal to be prompted for it.")
    if missing:
        raise _UsageError("missing credentials:\n" + "\n".join(f"  - {item}" for item in missing))

    if not password:
        try:
            password = getpass.getpass(f"Password for {email}: ")
        except EOFError:
            password = ""
        if not password:
            raise _UsageError("missing credentials: no password entered.")
    return email, password, centre


def _login(args: argparse.Namespace) -> SportBot:
    email, password, centre = _credentials(args)
    bot = SportBot(log_level=None, time_zone=args.time_zone)
    bot.login(email, password, centre)
    return bot


def _cmd_centres(args: argparse.Namespace) -> int:
    centres = SportBot(log_level=None, time_zone=args.time_zone).centres(args.search)
    if args.json:
        _print_json(centres)
    elif not centres:
        print(f"No centres match '{args.search}'." if args.search else "No centres found.")
    else:
        _print_table(
            ("SLUG", "NAME", "TOWN", "COUNTRY"),
            [(c.slug, c.name, c.town or "", c.country or "") for c in centres],
        )
    return EXIT_OK


def _cmd_activities(args: argparse.Namespace) -> int:
    activities = _login(args).activities()
    if args.json:
        _print_json(activities)
    elif not activities:
        print("No activities found.")
    else:
        _print_table(("NAME", "ID", "CATEGORY"), [(a.name, str(a.id), str(a.category_id)) for a in activities])
    return EXIT_OK


def _cmd_slots(args: argparse.Namespace) -> int:
    # Parse the day before logging in, so a typo fails fast
    try:
        day = parse_day(args.day, _today(args.time_zone))
    except ValueError as e:
        raise _UsageError(f"argument DAY: {e}") from None

    slots = _login(args).daily_slots(args.activity, day)
    if args.json:
        _print_json(slots)
    elif not slots:
        print(f"No slots of '{args.activity}' on {day:%A %Y-%m-%d}.")
    else:
        _print_table(
            ("START", "END", "TAKEN", "WAITING", "TRAINER", "STATUS"),
            [
                (
                    _format_time(s.start),
                    _format_time(s.end, with_date=False),
                    f"{s.inscribed}/{s.capacity}",
                    str(s.waiting_list),
                    s.trainer or "",
                    _slot_status(s),
                )
                for s in slots
            ],
        )
    return EXIT_OK


def _cmd_book(args: argparse.Namespace) -> int:
    slot = _login(args).book(args.activity, args.start)
    # No places count: the slot is as listed before the booking, so its counts are already stale
    print(f"Booked '{slot.activity_name}' on {_format_time(slot.start)}")
    return EXIT_OK


def _cmd_cancel(args: argparse.Namespace) -> int:
    slot = _login(args).cancel(args.activity, args.start)
    print(f"Cancelled '{slot.activity_name}' on {_format_time(slot.start)}")
    return EXIT_OK


def _with_notify_on(settings: NotifySettings | None, args: argparse.Namespace) -> NotifySettings | None:
    if settings is None or args.notify_on is None:
        return settings
    return replace(settings, on=args.notify_on)


def _cmd_run(args: argparse.Namespace) -> int:
    try:
        config = load_config(args.config)
    except ConfigError as e:
        # Without a config, only the env can say where to send the notification
        settings_from_env = _with_notify_on(notify_settings_from_env(), args)
        if settings_from_env is not None:
            notify.send(settings_from_env, error=e, dry_run=args.dry_run)
        raise
    if args.notify_on is not None and config.notify is None:
        logger.warning(f"--notify-on has no effect: set {NOTIFY_ENV_VARS['notify_url']} to get notifications.")
    notify_settings = _with_notify_on(config.notify, args)

    try:
        results = run_service(
            config,
            booking_delay=args.booking_delay,
            retry_attempts=args.retry_attempts,
            retry_delay=args.retry_delay,
            poll_interval=args.poll_interval,
            poll_window=args.poll_window,
            time_zone=args.time_zone,
            log_level=args.log_level,
            max_threads=args.max_threads,
            dry_run=args.dry_run,
        )
    except Exception as e:
        # E.g. a failed login: notify, then let main() report the error as usual
        if notify_settings is not None:
            notify.send(notify_settings, error=e, dry_run=args.dry_run)
        raise
    if notify_settings is not None:
        notify.send(notify_settings, results, dry_run=args.dry_run)
    # Fail if any class was not booked, so that e.g. a scheduled GitHub Actions run shows up as failed
    return EXIT_OK if all(r.ok for r in results) else EXIT_FAILURE


# Parser


def build_parser() -> argparse.ArgumentParser:
    """Build the parser of the `pysportbot` command."""
    parser = argparse.ArgumentParser(
        prog="pysportbot",
        description="Book classes at sports centres that use Resasports.",
        epilog=(
            "Commands that log in read the credentials from --email and --centre, or the SPORTBOT_EMAIL and "
            "SPORTBOT_CENTRE env vars. The password comes from SPORTBOT_PASSWORD, or a prompt in a terminal."
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    log_level_help = "Log level: DEBUG, INFO, WARNING, ERROR or CRITICAL [default: INFO for run, otherwise WARNING]."
    time_zone_help = f"Time zone of the centre [default: {DEFAULT_TIME_ZONE}]."
    parser.add_argument("--log-level", type=_log_level, default=None, metavar="LEVEL", help=log_level_help)
    parser.add_argument("--time-zone", type=_time_zone, default=DEFAULT_TIME_ZONE, metavar="TZ", help=time_zone_help)

    # The global options are accepted after the command too, e.g. `pysportbot run --config c.json --log-level DEBUG`.
    # SUPPRESS keeps a value given before the command when the option is not repeated after it
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--log-level", type=_log_level, default=argparse.SUPPRESS, metavar="LEVEL", help=log_level_help)
    common.add_argument("--time-zone", type=_time_zone, default=argparse.SUPPRESS, metavar="TZ", help=time_zone_help)

    credentials = argparse.ArgumentParser(add_help=False)
    credentials.add_argument("--email", help="Account email [default: $SPORTBOT_EMAIL].")
    credentials.add_argument("--centre", help="Centre slug, see 'pysportbot centres' [default: $SPORTBOT_CENTRE].")

    output = argparse.ArgumentParser(add_help=False)
    output.add_argument("--json", action="store_true", help="Print a JSON array instead of a table.")

    commands = parser.add_subparsers(dest="command", required=True, metavar="<command>")

    centres = commands.add_parser(
        "centres", parents=[common, output], help="List the centres and their slugs; needs no login."
    )
    centres.add_argument("--search", help="Only list centres whose slug, name or town contains TEXT.", metavar="TEXT")
    centres.set_defaults(handler=_cmd_centres)

    activities = commands.add_parser(
        "activities", parents=[common, credentials, output], help="List the activities of the centre."
    )
    activities.set_defaults(handler=_cmd_activities)

    slots = commands.add_parser("slots", parents=[common, credentials, output], help="List the slots of an activity.")
    slots.add_argument("activity", metavar="ACTIVITY", help="Activity name, see 'pysportbot activities'.")
    slots.add_argument(
        "day",
        metavar="DAY",
        help="YYYY-MM-DD, today, tomorrow, or a weekday name such as monday for its next occurrence (today counts).",
    )
    slots.set_defaults(handler=_cmd_slots)

    start_help = "Start time of the slot, 'YYYY-MM-DD HH:MM[:SS]'."
    book = commands.add_parser("book", parents=[common, credentials], help="Book a slot.")
    book.add_argument("activity", metavar="ACTIVITY", help="Activity name, see 'pysportbot activities'.")
    book.add_argument("start", metavar="START", type=_start, help=start_help)
    book.set_defaults(handler=_cmd_book)

    cancel = commands.add_parser("cancel", parents=[common, credentials], help="Cancel a booking.")
    cancel.add_argument("activity", metavar="ACTIVITY", help="Activity name, see 'pysportbot activities'.")
    cancel.add_argument("start", metavar="START", type=_start, help=start_help)
    cancel.set_defaults(handler=_cmd_cancel)

    run = commands.add_parser(
        "run",
        parents=[common],
        help="Run the booking service with a config file.",
        description="Run the booking service with a JSON or TOML config file.",
        epilog=(
            "The SPORTBOT_EMAIL, SPORTBOT_PASSWORD, SPORTBOT_CENTRE, SPORTBOT_NOTIFY_URL, SPORTBOT_NOTIFY_ON and "
            "SPORTBOT_NOTIFY_LANGUAGE env vars override the config file."
        ),
    )
    run.add_argument("--config", required=True, help="Path to the JSON or TOML configuration file.")
    run.add_argument(
        "--booking-delay",
        type=_seconds,
        default=0.0,
        metavar="SECONDS",
        help="Global delay in seconds after the execution time before booking [default: 0].",
    )
    run.add_argument(
        "--retry-attempts",
        type=_positive_int,
        default=3,
        metavar="N",
        help=(
            "Maximum number of attempts per class that fail with an error that may be temporary, such as a network "
            "error [default: 3]."
        ),
    )
    run.add_argument(
        "--retry-delay",
        type=_seconds,
        default=5.0,
        metavar="SECONDS",
        help="Delay in seconds after such an error [default: 5].",
    )
    run.add_argument(
        "--poll-interval",
        type=_positive_seconds,
        default=0.5,
        metavar="SECONDS",
        help="Delay in seconds between attempts while a slot is not bookable yet or not found [default: 0.5].",
    )
    run.add_argument(
        "--poll-window",
        type=_seconds,
        default=60.0,
        metavar="SECONDS",
        help="How long to keep polling, in seconds after booking starts [default: 60].",
    )
    run.add_argument(
        "--max-threads",
        type=_max_threads,
        default=None,
        help="Maximum number of classes booked in parallel [default: all classes in parallel].",
    )
    run.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Do everything, including waiting and checking that the slots exist and are open, but send no booking "
            "request. The real booking can still fail, e.g. if the slot fills up first."
        ),
    )
    run.add_argument(
        "--notify-on",
        choices=NOTIFY_ON,
        default=None,
        help=(
            "When to send a notification to the ntfy topic URL in SPORTBOT_NOTIFY_URL or notify_url: after every run, "
            "or only if a class was not booked or the run failed [default: $SPORTBOT_NOTIFY_ON, notify_on, or always]."
        ),
    )
    run.set_defaults(handler=_cmd_run)

    return parser


def _hide_expected_tracebacks(enabled: bool) -> None:
    handler = _find_handler(logging.getLogger(PACKAGE_LOGGER))
    if handler is None:
        return
    if enabled:
        handler.addFilter(_HIDE_EXPECTED_TRACEBACKS)
    else:
        handler.removeFilter(_HIDE_EXPECTED_TRACEBACKS)


def main(argv: list[str] | None = None) -> int:
    """
    Run the `pysportbot` command.

    Args:
        argv: The arguments, without the program name. None reads them from `sys.argv`.

    Returns:
        The exit code: 0 on success, 1 if the operation failed (for `run`: if any class was not booked), 2 for a
        usage, config or credential error, and 130 if interrupted.
    """
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as e:
        # --help, --version or a usage error, already printed by argparse
        return e.code if isinstance(e.code, int) else EXIT_OK

    args.log_level = args.log_level or ("INFO" if args.command == "run" else "WARNING")
    configure_logging(args.log_level, timezone=args.time_zone)
    # Only while the command runs, so callers of main() keep their library tracebacks afterwards
    _hide_expected_tracebacks(args.log_level != "DEBUG")
    try:
        exit_code: int = args.handler(args)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return EXIT_INTERRUPTED
    except (_UsageError, ConfigError) as e:
        print(f"pysportbot: error: {e}", file=sys.stderr)
        return EXIT_USAGE
    except (SportBotError, requests.RequestException) as e:
        logger.debug("The operation failed.", exc_info=True)
        print(f"pysportbot: error: {e}", file=sys.stderr)
        return EXIT_FAILURE
    finally:
        _hide_expected_tracebacks(False)
    return exit_code
