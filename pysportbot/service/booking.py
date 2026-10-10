import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

from pysportbot import SportBot
from pysportbot.exceptions import SlotAlreadyBookedError, SlotFullError, SlotNotFoundError, SportBotError
from pysportbot.models import Slot

from .config import ClassSpec, ServiceConfig
from .results import BookingResult, BookingStatus, describe
from .retry import RetryPolicy, classify
from .scheduling import Clock, Sleep, next_class_date, next_execution, sleep_until, to_monotonic, wait_until

logger = logging.getLogger(__name__)

# Seconds before the execution time to re-authenticate and look up the slots
PREPARATION_LEAD = 60.0


class _SlotCancelledError(SportBotError):
    """A dry run found the slot cancelled. A real booking sends the request anyway, and lets the API decide."""

    def __init__(self, slot_id: int) -> None:
        super().__init__(f"Slot {slot_id} is cancelled, so booking it would fail.")


def attempt_booking(
    bot: SportBot,
    spec: ClassSpec,
    start: datetime,
    policy: RetryPolicy | None = None,
    *,
    slot: Slot | None = None,
    poll_until: float | None = None,
    dry_run: bool = False,
    clock: Clock | None = None,
    sleep: Sleep | None = None,
) -> BookingResult:
    """
    Book one class, and try again as `policy` and `classify()` decide. Never raises.

    Args:
        bot: A logged-in bot.
        spec: The class to book.
        start: The time zone aware start time of the class.
        policy: When to try again [default: RetryPolicy()].
        slot: The slot, if found ahead of time. Each attempt is then a single booking request; otherwise each attempt
            looks the slot up first.
        poll_until: The `clock` time when polling ends [default: `policy.poll_window` seconds from now].
        dry_run: Find the slot and check that it is open, but send no booking request.
        clock: The monotonic clock in seconds [default: time.monotonic].
        sleep: The sleep function [default: time.sleep].
    """
    policy = policy or RetryPolicy()
    clock = clock or time.monotonic
    sleep = sleep or time.sleep
    if poll_until is None:
        poll_until = clock() + policy.poll_window
    what = describe(spec.activity, start)

    attempts = failures = polls = 0
    network_error = False
    while True:
        attempts += 1
        try:
            booked = _book_once(bot, spec.activity, start, slot, dry_run=dry_run)
        except Exception as error:
            action = classify(error)
            if action == "poll" and clock() < poll_until:
                polls += 1
                if polls == 1:
                    logger.info(
                        f"{error} Trying {what} again every {policy.poll_interval:g} s "
                        f"for up to {poll_until - clock():.0f} s."
                    )
                else:
                    logger.debug(f"Attempt {attempts} to book {what} failed: {error}")
                sleep(min(policy.poll_interval, poll_until - clock()))
                continue
            if action == "retry":
                failures += 1
                # A booking request that timed out may still have gone through
                network_error = network_error or isinstance(error, requests.RequestException)
                if failures < policy.retry_attempts:
                    logger.warning(
                        f"Attempt {attempts} to book {what} failed: {error} Retrying in {policy.retry_delay:g} s."
                    )
                    sleep(policy.retry_delay)
                    continue
            return _give_up(spec, start, slot, attempts, error, network_error=network_error)

        status = BookingStatus.DRY_RUN if dry_run else BookingStatus.BOOKED
        if not dry_run:
            logger.info(f"Booked {what} after {attempts} attempt(s).")
        return BookingResult(spec, start, status, attempts, booked)


def _book_once(bot: SportBot, activity: str, start: datetime, slot: Slot | None, *, dry_run: bool) -> Slot:
    if dry_run:
        return _dry_run_booking(bot, activity, start, slot)
    if slot is None:
        return bot.book(activity=activity, start=start)
    return bot.book_slot(slot)


def _give_up(
    spec: ClassSpec,
    start: datetime,
    slot: Slot | None,
    attempts: int,
    error: Exception,
    *,
    network_error: bool,
) -> BookingResult:
    what = describe(spec.activity, start)
    message = str(error)
    if isinstance(error, SlotAlreadyBookedError):
        status = BookingStatus.ALREADY_BOOKED
        if network_error:
            logger.info(
                f"{what} is already booked: an earlier attempt that failed with a network error probably worked."
            )
        else:
            logger.info(f"{what} is already booked.")
        return BookingResult(spec, start, status, attempts, slot)

    if isinstance(error, SlotFullError):
        status = BookingStatus.FULL
    elif isinstance(error, SlotNotFoundError):
        status = BookingStatus.NOT_FOUND
    else:
        status = BookingStatus.FAILED
    if classify(error) == "poll":
        message += " The poll window ended."

    if isinstance(error, SportBotError | requests.RequestException):
        logger.error(f"Failed to book {what} after {attempts} attempt(s): {message}")
    else:
        logger.exception(f"Failed to book {what} after {attempts} attempt(s) with an unexpected error.")
    return BookingResult(spec, start, status, attempts, slot, message)


def _dry_run_booking(bot: SportBot, activity: str, start: datetime, slot: Slot | None) -> Slot:
    """
    Check that the slot exists and is open, and log what booking would do, without sending a booking request.

    Raises:
        _SlotCancelledError: If the slot is cancelled, so booking it would fail.
        SlotFullError: If the slot has no places left, as `SportBot.book()` would.
        SportBotError: If the slot cannot be found, see `SportBot.find_slot()`.
    """
    if slot is None:
        slot = bot.find_slot(activity=activity, start=start)
    if slot.cancelled:
        raise _SlotCancelledError(slot.id)
    if slot.is_full:
        raise SlotFullError(str(slot.id))
    else:
        logger.info(
            f"DRY RUN: would book {describe(activity, start)} "
            f"(slot {slot.id}, {slot.inscribed}/{slot.capacity} places taken)."
        )
    return slot


def _relogin(bot: SportBot, policy: RetryPolicy, *, deadline: float, clock: Clock, sleep: Sleep) -> None:
    """
    Log in again if the session has expired. Retry failures as for a booking, but not past `deadline`.

    A failed re-login leaves the bot logged out, so that every booking would fail.
    """
    for attempt in range(1, policy.retry_attempts + 1):
        try:
            bot.ensure_logged_in()
        except Exception as e:
            message = f"Re-authentication failed before booking execution with {e}."
            if attempt == policy.retry_attempts or clock() + policy.retry_delay >= deadline:
                logger.warning(message)
                return
            logger.warning(f"{message} Retrying in {policy.retry_delay:g} s.")
            sleep(policy.retry_delay)
        else:
            return


def _look_up(bot: SportBot, spec: ClassSpec, start: datetime) -> Slot | None:
    """Find the slot ahead of time, so that booking it costs one request. None if it cannot be found yet."""
    try:
        return bot.find_slot(spec.activity, start)
    except (SportBotError, requests.RequestException) as e:
        # E.g. the calendar is not published yet
        what = describe(spec.activity, start)
        logger.info(f"Could not look up {what} ahead of time, so it will be looked up when booking: {e}")
        return None


def _book_class(
    bot: SportBot,
    spec: ClassSpec,
    start: datetime,
    policy: RetryPolicy,
    *,
    look_up: bool,
    booking_start: float,
    dry_run: bool,
    clock: Clock,
    sleep: Sleep,
) -> BookingResult:
    """Look up the slot first if `look_up`, wait until `booking_start` on the `clock` scale, then book."""
    # Each class looks up its own slot, so that a slow lookup cannot delay the booking of the other classes
    slot = _look_up(bot, spec, start) if look_up else None
    sleep_until(booking_start, clock=clock, sleep=sleep)
    return attempt_booking(
        bot,
        spec,
        start,
        policy,
        slot=slot,
        poll_until=booking_start + policy.poll_window,
        dry_run=dry_run,
        clock=clock,
        sleep=sleep,
    )


def schedule_bookings(
    bot: SportBot,
    config: ServiceConfig,
    policy: RetryPolicy,
    *,
    booking_delay: float = 0,
    time_zone: str = "Europe/Madrid",
    max_threads: int = 1,
    dry_run: bool = False,
    clock: Clock | None = None,
    sleep: Sleep | None = None,
) -> list[BookingResult]:
    """
    Wait until the execution time, then book all classes in parallel.

    60 seconds before the execution time, re-authenticate and look up the slots, so that booking a slot at the
    execution time is a single request. A slot that cannot be found yet is looked up again when booking.

    Args:
        bot: A logged-in bot.
        config: The service configuration.
        policy: When to try booking a class again. The poll window starts when booking starts.
        booking_delay: Seconds to wait after the execution time before booking.
        time_zone: The time zone of the execution and class times.
        max_threads: The maximum number of classes booked in parallel.
        dry_run: Find the slots, but send no booking requests.
        clock: The monotonic clock in seconds [default: time.monotonic].
        sleep: The sleep function [default: time.sleep].

    Returns:
        One result per class, in the order of the configuration.
    """
    clock = clock or time.monotonic
    sleep = sleep or time.sleep
    tz = ZoneInfo(time_zone)
    now = datetime.now(tz)

    # Exact time when booking will be executed (modulo global booking delay)
    execution_time = next_execution(config.execution, now)

    # Classes are booked for the week following the execution
    bookings = [
        (cls, datetime.combine(next_class_date(cls.weekday, execution_time), cls.time, tzinfo=tz))
        for cls in config.classes
    ]
    for cls, start in bookings:
        logger.info(f"Scheduled to book {describe(cls.activity, start)}.")

    # Compare instants: subtracting datetimes that share a ZoneInfo gives the wall-clock difference, which is off by
    # an hour across a DST change
    time_until_execution = execution_time.timestamp() - now.timestamp()
    prepare = time_until_execution > 0
    if prepare:
        logger.info(
            f"Waiting {time_until_execution:.2f} seconds until global execution time: "
            f"{execution_time.strftime('%Y-%m-%d %H:%M:%S %z')}."
        )
        wait_until(datetime.fromtimestamp(execution_time.timestamp() - PREPARATION_LEAD, tz), clock=clock, sleep=sleep)

    # All threads book at this same instant on purpose: the first requests have the best chance
    booking_start = to_monotonic(execution_time, clock) + booking_delay
    if booking_delay > 0:
        logger.info(f"Booking {booking_delay:g} seconds after the execution time.")
    if prepare:
        _relogin(bot, policy, deadline=booking_start, clock=clock, sleep=sleep)

    with ThreadPoolExecutor(max_workers=max_threads) as executor:
        futures = [
            executor.submit(
                _book_class,
                bot,
                cls,
                start,
                policy,
                look_up=prepare,
                booking_start=booking_start,
                dry_run=dry_run,
                clock=clock,
                sleep=sleep,
            )
            for cls, start in bookings
        ]
    return [future.result() for future in futures]
