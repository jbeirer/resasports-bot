import datetime as dt
import difflib
import json
import logging
import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, cast
from urllib.parse import urlsplit

from pysportbot import SportBot
from pysportbot.exceptions import ConfigError

logger = logging.getLogger(__name__)

# Defined literally because `calendar.day_name` and `calendar.day_abbr` follow the current locale
WEEKDAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
WEEKDAYS = {
    **{name.lower(): index for index, name in enumerate(WEEKDAY_NAMES)},
    **{name[:3].lower(): index for index, name in enumerate(WEEKDAY_NAMES)},
}

# Credentials that env vars override, keyed by config key
ENV_VARS = {"email": "SPORTBOT_EMAIL", "password": "SPORTBOT_PASSWORD", "centre": "SPORTBOT_CENTRE"}

# Notification settings that env vars override, keyed by config key
NOTIFY_ENV_VARS = {"notify_url": "SPORTBOT_NOTIFY_URL", "notify_on": "SPORTBOT_NOTIFY_ON"}
NOTIFY_ON = ("always", "failure")

TOP_LEVEL_KEYS = (*ENV_VARS, "booking_execution", "classes", *NOTIFY_ENV_VARS)
CLASS_KEYS = ("activity", "class_day", "class_time")
TIME_FORMATS = ("%H:%M:%S", "%H:%M")
LOCALHOST_NAMES = ("localhost", "127.0.0.1", "::1")


@dataclass(frozen=True, slots=True)
class WeeklyTime:
    """A weekday and time of day, e.g. "Friday 07:30:00"."""

    weekday: int  # 0=Monday
    time: dt.time

    def __str__(self) -> str:
        return f"{WEEKDAY_NAMES[self.weekday]} {self.time:%H:%M:%S}"


@dataclass(frozen=True, slots=True)
class ClassSpec:
    """A weekly class to book."""

    activity: str
    weekday: int  # 0=Monday
    time: dt.time


@dataclass(frozen=True, slots=True)
class NotifySettings:
    """Where and when to send the ntfy notification about a run."""

    # The ntfy topic URL works like a password, so keep it out of the repr
    url: str = field(repr=False)
    on: Literal["always", "failure"] = "always"


@dataclass(frozen=True, slots=True)
class ServiceConfig:
    """The parsed and validated service configuration."""

    email: str
    password: str = field(repr=False)
    centre: str
    execution: WeeklyTime | None  # None means "now"
    classes: tuple[ClassSpec, ...]
    notify: NotifySettings | None = None  # None means no notifications

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any], env: Mapping[str, str] = os.environ) -> "ServiceConfig":
        """
        Parse a config mapping, with the SPORTBOT_EMAIL, SPORTBOT_PASSWORD, SPORTBOT_CENTRE, SPORTBOT_NOTIFY_URL and
        SPORTBOT_NOTIFY_ON env vars overriding the corresponding keys.

        Raises:
            ConfigError: Listing every problem found.
        """
        errors: list[str] = []

        for key in data:
            if key not in TOP_LEVEL_KEYS:
                errors.append(_unknown_key(key, TOP_LEVEL_KEYS))

        credentials = {key: _credential(data, env, key, errors) for key in ENV_VARS}
        execution = _execution(data.get("booking_execution", "now"), errors)
        classes = _classes(data.get("classes"), errors)
        notify = _notify(data, env, errors)

        if errors:
            raise ConfigError("Invalid configuration:\n" + "\n".join(f"  - {error}" for error in errors))

        return cls(
            email=credentials["email"],
            password=credentials["password"],
            centre=credentials["centre"],
            execution=execution,
            classes=classes,
            notify=notify,
        )


def load_config(path: str | Path, env: Mapping[str, str] = os.environ) -> ServiceConfig:
    """
    Load a .json or .toml config file, chosen by suffix, and parse it.

    Raises:
        ConfigError: If the file cannot be read or the configuration is invalid.
    """
    path = Path(path)
    suffix = path.suffix.lower()
    try:
        if suffix == ".json":
            with path.open(encoding="utf-8") as f:
                data = json.load(f)
        elif suffix == ".toml":
            with path.open("rb") as f:
                data = tomllib.load(f)
        else:
            raise ConfigError(f"Unsupported config file type '{path.suffix}' for {path}. Use .json or .toml.")
    except OSError as e:
        raise ConfigError(f"Cannot read config file {path}: {e.strerror or e}.") from e
    except (json.JSONDecodeError, tomllib.TOMLDecodeError, UnicodeDecodeError) as e:
        raise ConfigError(f"Cannot parse config file {path}: {e}") from e

    if not isinstance(data, Mapping):
        raise ConfigError(f"Config file {path} must contain an object at the top level.")
    return ServiceConfig.from_mapping(data, env)


def validate_activities(bot: SportBot, config: ServiceConfig) -> None:
    """
    Validate that all activities in the configuration exist.

    Raises:
        ConfigError: If an activity is not found.
    """
    logger.info("Fetching available activities for validation...")
    available_activity_names = {a.name for a in bot.activities()}

    logger.debug(f"Available activities: {available_activity_names}")

    for cls in config.classes:
        if cls.activity not in available_activity_names:
            raise ConfigError(
                f"No activity found with the name '{cls.activity}'. "
                f"Available activities are: {', '.join(sorted(available_activity_names))}."
            )

    logger.info("All activities in the configuration file have been validated.")


def _unknown_key(key: Any, valid: tuple[str, ...], where: str = "") -> str:
    message = f"{where}unknown key '{key}'"
    matches = difflib.get_close_matches(str(key), valid, n=1)
    if matches:
        return f"{message}, did you mean '{matches[0]}'?"
    return f"{message}. Valid keys are: {', '.join(valid)}."


def _credential(data: Mapping[str, Any], env: Mapping[str, str], key: str, errors: list[str]) -> str:
    env_var = ENV_VARS[key]
    # Empty env vars count as unset: GitHub Actions expands a missing secret to ""
    value = env.get(env_var) or data.get(key)
    if value is None:
        errors.append(f"{key}: missing. Set it in the config file or via the {env_var} env var.")
        return ""
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{key}: must be a non-empty string.")
        return ""
    return value


def _notify(data: Mapping[str, Any], env: Mapping[str, str], errors: list[str]) -> NotifySettings | None:
    # Empty env vars count as unset, as for the credentials
    url = env.get(NOTIFY_ENV_VARS["notify_url"]) or data.get("notify_url")
    on = env.get(NOTIFY_ENV_VARS["notify_on"]) or data.get("notify_on", "always")

    if on not in NOTIFY_ON:
        errors.append(f"notify_on: invalid value {on!r}. Use one of: {', '.join(NOTIFY_ON)}.")
    if url is None:
        return None
    # Never echo the URL: an ntfy topic URL works like a password
    if not isinstance(url, str) or not _is_notify_url(url.strip()):
        errors.append("notify_url: must be an https:// URL, or http:// for localhost, e.g. 'https://ntfy.sh/<topic>'.")
        return None
    return NotifySettings(url=url.strip(), on=cast(Literal["always", "failure"], on))


def _is_notify_url(url: str) -> bool:
    try:
        parts = urlsplit(url)
        host = parts.hostname
    except ValueError:
        return False
    if not host:
        return False
    return parts.scheme == "https" or (parts.scheme == "http" and host in LOCALHOST_NAMES)


def _weekday(value: Any, where: str, errors: list[str]) -> int:
    if isinstance(value, str) and value.strip().lower() in WEEKDAYS:
        return WEEKDAYS[value.strip().lower()]
    errors.append(
        f"{where}: invalid day {value!r}. Use an English weekday name such as 'Monday' or 'Mon' (case-insensitive)."
    )
    return 0


def _time(value: Any, where: str, errors: list[str]) -> dt.time:
    # TOML parses an unquoted local time such as `class_time = 18:00:00` into a time
    if isinstance(value, dt.time) and value.tzinfo is None:
        return value
    if isinstance(value, str):
        for fmt in TIME_FORMATS:
            try:
                return dt.datetime.strptime(value.strip(), fmt).time()
            except ValueError:
                continue
    errors.append(f"{where}: invalid time {value!r}. Use the 24-hour format 'HH:MM' or 'HH:MM:SS', e.g. '18:00'.")
    return dt.time()


def _execution(value: Any, errors: list[str]) -> WeeklyTime | None:
    if isinstance(value, str) and value.strip().lower() == "now":
        return None
    parts = value.split() if isinstance(value, str) else []
    if len(parts) != 2:
        errors.append(
            f"booking_execution: invalid value {value!r}. Use 'now' or '<weekday> <time>', e.g. 'Friday 07:30'."
        )
        return None
    return WeeklyTime(
        weekday=_weekday(parts[0], "booking_execution", errors),
        time=_time(parts[1], "booking_execution", errors),
    )


def _classes(value: Any, errors: list[str]) -> tuple[ClassSpec, ...]:
    if value is None:
        errors.append("classes: missing. Add at least one class to book.")
        return ()
    if not isinstance(value, list) or not value:
        errors.append("classes: must be a non-empty list of classes.")
        return ()

    classes = []
    for i, entry in enumerate(value):
        where = f"classes[{i}]"
        if not isinstance(entry, Mapping):
            errors.append(f"{where}: must be an object with the keys {', '.join(CLASS_KEYS)}.")
            continue
        for key in entry:
            if key not in CLASS_KEYS:
                errors.append(_unknown_key(key, CLASS_KEYS, f"{where}: "))
        missing = [key for key in CLASS_KEYS if key not in entry]
        if missing:
            errors.append(f"{where}: missing {', '.join(missing)}.")
            continue

        activity = entry["activity"]
        if not isinstance(activity, str) or not activity.strip():
            errors.append(f"{where}.activity: must be a non-empty string.")
        classes.append(
            ClassSpec(
                activity=activity,
                weekday=_weekday(entry["class_day"], f"{where}.class_day", errors),
                time=_time(entry["class_time"], f"{where}.class_time", errors),
            )
        )
    return tuple(classes)
