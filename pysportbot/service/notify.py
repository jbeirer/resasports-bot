"""Optional ntfy notifications about a run of the booking service, see https://docs.ntfy.sh/publish/."""

import logging
from collections.abc import Sequence

import requests

from .config import WEEKDAY_NAMES, NotifySettings
from .results import BookingResult, BookingStatus, format_time

logger = logging.getLogger(__name__)

TIMEOUT = 10  # seconds


def format_summary(results: Sequence[BookingResult], *, dry_run: bool = False) -> tuple[str, str]:
    """
    Summarize the results as a notification title and body.

    The title counts the classes that are ok, e.g. "pysportbot: 2/3 booked". The body has one line per class, e.g.
    "✅ Yoga · Mon 2026-01-12 18:00 · booked (3 attempts)".

    Returns:
        tuple[str, str]: The title and the body.
    """
    ok = sum(r.ok for r in results)
    title = _title(f"{ok}/{len(results)} {'bookable' if dry_run else 'booked'}", dry_run)
    return title, "\n".join(_describe(r) for r in results)


def send(
    settings: NotifySettings,
    results: Sequence[BookingResult] | None = None,
    *,
    error: Exception | None = None,
    dry_run: bool = False,
) -> None:
    """
    Send a notification with the results of a run, or with the error that stopped the run before it had results.

    Does nothing if `settings.on` is "failure" and every class is ok. Never raises: a failure to send is logged as a
    warning, without the URL, which works like a password.
    """
    failed = error is not None or not all(r.ok for r in results or ())
    if settings.on == "failure" and not failed:
        return
    if error is not None:
        title, body = _title("run failed", dry_run), str(error) or type(error).__name__
    else:
        title, body = format_summary(results or (), dry_run=dry_run)

    headers = {
        "Title": title,
        "Tags": "warning" if failed else "white_check_mark",
        "Priority": "high" if failed else "default",
        "Content-Type": "text/plain; charset=utf-8",
    }
    try:
        response = requests.post(settings.url, data=body.encode("utf-8"), headers=headers, timeout=TIMEOUT)
    # Whatever goes wrong, the notification must not change the outcome of the run
    except Exception as e:
        logger.warning(f"Could not send the notification: {type(e).__name__}.")
        return
    if not response.ok:
        logger.warning(f"Could not send the notification: HTTP {response.status_code}.")
        return
    logger.info("Notification sent.")


def _title(text: str, dry_run: bool) -> str:
    return f"{'[dry run] ' if dry_run else ''}pysportbot: {text}"


def _describe(result: BookingResult) -> str:
    start = result.start
    when = f"{WEEKDAY_NAMES[start.weekday()][:3]} {start:%Y-%m-%d} {format_time(start)}"
    outcome = str(result.status)
    if result.attempts > 1:
        outcome += f" ({result.attempts} attempts)"
    if result.status is BookingStatus.FAILED and result.error:
        outcome += f": {result.error}"
    return f"{'✅' if result.ok else '❌'} {result.spec.activity} · {when} · {outcome}"
