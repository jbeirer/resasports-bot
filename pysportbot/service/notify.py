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


@dataclass(frozen=True, slots=True)
class _Texts:
    """The words of a notification in one language. Error messages come from pysportbot and stay in English."""

    booked: str  # Title, e.g. "2/3 booked"
    bookable: str  # Title of a dry run, e.g. "3/3 bookable"
    run_failed: str  # Title of a run that failed before booking
    dry_run: str  # Title prefix of a dry run
    attempts: str  # e.g. "3 attempts", only shown for more than one
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
    return title, "\n".join(_describe(r, texts) for r in results)


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
        title, body = _title(texts.run_failed, texts, dry_run), str(error) or type(error).__name__
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
    logger.info("Notification sent.")


def _header(value: str) -> str:
    """Encode a non-ASCII header value as RFC 2047, as ntfy recommends: HTTP libraries send headers as Latin-1."""
    if value.isascii():
        return value
    return f"=?UTF-8?B?{base64.b64encode(value.encode('utf-8')).decode('ascii')}?="


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
    return f"{'✅' if result.ok else '❌'} {result.spec.activity} · {when} · {outcome}"
