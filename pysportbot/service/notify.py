"""Optional ntfy notifications about a run of the booking service, see https://docs.ntfy.sh/publish/."""

import base64
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import requests

from .config import NotifyLanguage, NotifySettings
from .results import BookingResult, BookingStatus, format_time

logger = logging.getLogger(__name__)

TIMEOUT = 10  # seconds
# ntfy delivers a longer message as an attachment, which the notification does not show
MAX_MESSAGE_BYTES = 4096
# So that a long error message cannot crowd out the other classes
MAX_LINE_BYTES = 1024
# Room for the line that counts the classes left out
_MORE_LINE_BYTES = 64


@dataclass(frozen=True, slots=True)
class _Texts:
    """The words of a notification in one language. Error messages come from pysportbot and stay in English."""

    booked: str  # Title, e.g. "2/3 booked"
    bookable: str  # Title of a dry run, e.g. "3/3 bookable"
    run_failed: str  # Title of a run that failed before booking
    dry_run: str  # Title prefix of a dry run
    attempts: str  # e.g. "3 attempts", only shown for more than one
    more: str  # Last line of a message too long for ntfy, e.g. "… and 3 more"
    weekdays: tuple[str, ...]  # Abbreviations, Monday first
    date_format: str
    statuses: Mapping[BookingStatus, str]


TEXTS: dict[NotifyLanguage, _Texts] = {
    "en": _Texts(
        booked="booked",
        bookable="bookable",
        run_failed="run failed",
        dry_run="dry run",
        attempts="{n} attempts",
        more="… and {n} more",
        weekdays=("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"),
        date_format="%Y-%m-%d",
        statuses={status: str(status) for status in BookingStatus},
    ),
    "de": _Texts(
        booked="gebucht",
        bookable="buchbar",
        run_failed="Lauf fehlgeschlagen",
        dry_run="Testlauf",
        attempts="{n} Versuche",
        more="… und {n} weitere",
        weekdays=("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"),
        date_format="%d.%m.%Y",
        statuses={
            BookingStatus.BOOKED: "gebucht",
            BookingStatus.ALREADY_BOOKED: "bereits gebucht",
            BookingStatus.FULL: "ausgebucht",
            BookingStatus.NOT_FOUND: "nicht gefunden",
            BookingStatus.FAILED: "fehlgeschlagen",
            BookingStatus.DRY_RUN: "Testlauf",
        },
    ),
    "es": _Texts(
        booked="reservadas",
        bookable="reservables",
        run_failed="ejecución fallida",
        dry_run="simulación",
        attempts="{n} intentos",
        more="… y {n} más",
        weekdays=("lun", "mar", "mié", "jue", "vie", "sáb", "dom"),
        date_format="%d/%m/%Y",
        statuses={
            BookingStatus.BOOKED: "reservada",
            BookingStatus.ALREADY_BOOKED: "ya reservada",
            BookingStatus.FULL: "completa",
            BookingStatus.NOT_FOUND: "no encontrada",
            BookingStatus.FAILED: "fallida",
            BookingStatus.DRY_RUN: "simulación",
        },
    ),
    "fr": _Texts(
        booked="réservés",
        bookable="réservables",
        run_failed="échec de l'exécution",
        dry_run="simulation",
        attempts="{n} tentatives",
        more="… et {n} autres",
        weekdays=("lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."),
        date_format="%d/%m/%Y",
        statuses={
            BookingStatus.BOOKED: "réservé",
            BookingStatus.ALREADY_BOOKED: "déjà réservé",
            BookingStatus.FULL: "complet",
            BookingStatus.NOT_FOUND: "introuvable",
            BookingStatus.FAILED: "échec",
            BookingStatus.DRY_RUN: "simulation",
        },
    ),
    "it": _Texts(
        booked="prenotate",
        bookable="prenotabili",
        run_failed="esecuzione non riuscita",
        dry_run="simulazione",
        attempts="{n} tentativi",
        more="… e altre {n}",
        weekdays=("lun", "mar", "mer", "gio", "ven", "sab", "dom"),
        date_format="%d/%m/%Y",
        statuses={
            BookingStatus.BOOKED: "prenotata",
            BookingStatus.ALREADY_BOOKED: "già prenotata",
            BookingStatus.FULL: "al completo",
            BookingStatus.NOT_FOUND: "non trovata",
            BookingStatus.FAILED: "non riuscita",
            BookingStatus.DRY_RUN: "simulazione",
        },
    ),
}


def format_summary(
    results: Sequence[BookingResult], *, dry_run: bool = False, language: NotifyLanguage = "en"
) -> tuple[str, str]:
    """
    Summarize the results as a notification title and body.

    The title counts the classes that are ok, e.g. "pysportbot: 2/3 booked". The body has one line per class, e.g.
    "✅ Yoga · Mon 2026-01-12 18:00 · booked (3 attempts)".

    Returns:
        tuple[str, str]: The title and the body.
    """
    texts = TEXTS[language]
    ok = sum(r.ok for r in results)
    title = _title(f"{ok}/{len(results)} {texts.bookable if dry_run else texts.booked}", texts, dry_run)
    return title, _join([(r.ok, _describe(r, texts)) for r in results], texts)


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
        texts = TEXTS[settings.language]
        title = _title(texts.run_failed, texts, dry_run)
        body = _truncate(str(error) or type(error).__name__, MAX_MESSAGE_BYTES)
    else:
        title, body = format_summary(results or (), dry_run=dry_run, language=settings.language)

    headers = {
        "Title": _header(title),
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
    # E.g. a proxy's login page: still a warning, so a wrong URL does not look like a sent notification
    if not _is_ntfy_response(response):
        logger.warning(
            f"The notification URL answered HTTP {response.status_code}, but not like an ntfy server. Check that it "
            "is the URL of an ntfy topic."
        )
        return
    logger.info("Notification sent.")


def _is_ntfy_response(response: requests.Response) -> bool:
    """Whether the response is ntfy's JSON description of the published message, which has its ID."""
    try:
        data = response.json()
    except ValueError:
        return False
    return isinstance(data, dict) and "id" in data


def _header(value: str) -> str:
    """Encode a non-ASCII header value as RFC 2047, as ntfy recommends: HTTP libraries send headers as Latin-1."""
    if value.isascii():
        return value
    return f"=?UTF-8?B?{base64.b64encode(value.encode('utf-8')).decode('ascii')}?="


def _truncate(text: str, max_bytes: int) -> str:
    """Shorten the text to at most `max_bytes` UTF-8 bytes, ending with "…" if shortened."""
    data = text.encode("utf-8")
    if len(data) <= max_bytes:
        return text
    return data[: max_bytes - len("…".encode())].decode("utf-8", errors="ignore") + "…"


def _join(lines: Sequence[tuple[bool, str]], texts: _Texts) -> str:
    """Join the (ok, line) pairs, keeping the failures and as many other lines as fit into one ntfy message."""
    body = "\n".join(line for _, line in lines)
    if len(body.encode("utf-8")) <= MAX_MESSAGE_BYTES:
        return body

    kept: list[str] = []
    size = _MORE_LINE_BYTES
    # Failures first, otherwise in order: they are what the notification is for
    for _, line in sorted(lines, key=lambda pair: pair[0]):
        size += len(line.encode("utf-8")) + 1
        if size > MAX_MESSAGE_BYTES:
            break
        kept.append(line)
    return "\n".join([*kept, texts.more.format(n=len(lines) - len(kept))])


def _title(text: str, texts: _Texts, dry_run: bool) -> str:
    return f"{f'[{texts.dry_run}] ' if dry_run else ''}pysportbot: {text}"


def _describe(result: BookingResult, texts: _Texts) -> str:
    start = result.start
    when = f"{texts.weekdays[start.weekday()]} {start.strftime(texts.date_format)} {format_time(start)}"
    outcome = texts.statuses[result.status]
    if result.attempts > 1:
        outcome += f" ({texts.attempts.format(n=result.attempts)})"
    if result.status is BookingStatus.FAILED and result.error:
        outcome += f": {result.error}"
    return _truncate(f"{'✅' if result.ok else '❌'} {result.spec.activity} · {when} · {outcome}", MAX_LINE_BYTES)
