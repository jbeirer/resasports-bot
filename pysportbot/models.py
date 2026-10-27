import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Self
from zoneinfo import ZoneInfo

from .endpoints import Endpoints
from .exceptions import APIError

# Format of start_timestamp and end_timestamp in the activities calendar, in the centre's local time
TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"


class _Fields:
    """Reads and coerces the fields of one API record. A missing or malformed field raises APIError naming it."""

    def __init__(self, data: Any, endpoint: str) -> None:
        self._data = data
        self._endpoint = endpoint
        if not isinstance(data, Mapping):
            raise self._error(f"Expected a JSON object, got {type(data).__name__}")

    def _error(self, reason: str) -> APIError:
        return APIError(reason, endpoint=self._endpoint, body=json.dumps(self._data, default=str))

    def _required(self, key: str) -> Any:
        value = self._data.get(key)
        if value is None:
            raise self._error(f"Missing required field '{key}'")
        return value

    def _to_int(self, key: str, value: Any) -> int:
        # Accept only whole numbers: int() would truncate 5001.9 to another slot ID and read True as 1
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        if isinstance(value, float) and value.is_integer():
            return int(value)
        if isinstance(value, str):
            try:
                return int(value)
            except ValueError:
                pass
        raise self._error(f"Field '{key}' is not an integer: {value!r}")

    def nested(self, key: str) -> "_Fields":
        """The fields of a nested object; a missing one reads as empty."""
        value = self._data.get(key)
        return _Fields({} if value is None else value, self._endpoint)

    def text(self, key: str) -> str:
        return str(self._required(key))

    def optional_text(self, key: str) -> str | None:
        value = self._data.get(key)
        return None if value is None else str(value)

    def integer(self, key: str) -> int:
        # The API sends ids and counts as numbers or as numeric strings
        return self._to_int(key, self._required(key))

    def optional_integer(self, key: str, default: int = 0) -> int:
        value = self._data.get(key)
        return default if value is None else self._to_int(key, value)

    def flag(self, key: str) -> bool:
        """An optional boolean, sent as true/false or as 0/1."""
        value = self._data.get(key)
        if value is None or isinstance(value, bool):
            return bool(value)
        return bool(self._to_int(key, value))

    def timestamp(self, key: str, tz: ZoneInfo) -> datetime:
        value = self._required(key)
        try:
            return datetime.strptime(str(value), TIMESTAMP_FORMAT).replace(tzinfo=tz)
        except ValueError as err:
            raise self._error(f"Field '{key}' is not a '{TIMESTAMP_FORMAT}' timestamp: {value!r}") from err


@dataclass(frozen=True, slots=True)
class Centre:
    """
    A sports centre that uses Resasports.

    Attributes:
        slug: The identifier to pass to `SportBot.login()`.
        name: The display name.
        town: The town, if listed.
        country: The country, if listed.
        address: The street address, if listed.
    """

    slug: str
    name: str
    town: str | None
    country: str | None
    address: str | None

    @classmethod
    def from_api(cls, data: Mapping[str, Any]) -> Self:
        """
        Build a centre from one entry of the centres response.

        Raises:
            APIError: If `slug` or `name` is missing.
        """
        fields = _Fields(data, Endpoints.CENTRE)
        address = fields.nested("address")
        return cls(
            slug=fields.text("slug"),
            name=fields.text("name"),
            town=address.optional_text("town"),
            country=address.optional_text("country"),
            address=address.optional_text("street_line"),
        )


@dataclass(frozen=True, slots=True)
class Activity:
    """
    An activity offered by the centre, such as a class.

    Attributes:
        id: The activity ID.
        name: The name to pass to `SportBot.daily_slots()`, `SportBot.book()` and `SportBot.cancel()`.
        category_id: The ID of the activity's category.
    """

    id: int
    name: str
    category_id: int

    @classmethod
    def from_api(cls, data: Mapping[str, Any]) -> Self:
        """
        Build an activity from one entry of the activities calendar. Spaces around the name are removed: some
        centres name activities e.g. "Ciclo Indoor ".

        Raises:
            APIError: If a field is missing or not an integer where one is expected.
        """
        fields = _Fields(data, Endpoints.SLOTS)
        return cls(
            id=fields.integer("id_activity"),
            name=fields.text("name_activity").strip(),
            category_id=fields.integer("id_category_activity"),
        )

    @classmethod
    def from_listing(cls, data: Mapping[str, Any]) -> Self | None:
        """
        Build an activity from one entry of the activities list, or return None if it cannot be booked: archived,
        a course, or not bookable online.

        Raises:
            APIError: If a field is missing or not an integer where one is expected.
        """
        fields = _Fields(data, Endpoints.ACTIVITIES)
        if fields.flag("is_archived") or fields.flag("is_course") or not fields.flag("bookable_online"):
            return None
        return cls(
            id=fields.integer("id_activity"),
            name=fields.text("name_activity").strip(),
            # The same ID as id_category_activity in the activities calendar
            category_id=fields.integer("id_category"),
        )


@dataclass(frozen=True, slots=True)
class Slot:
    """
    One scheduled session of an activity.

    Attributes:
        id: The slot ID, which booking and cancelling send to the API.
        activity_id: The ID of the activity.
        activity_name: The name of the activity.
        category_id: The ID of the activity's category.
        start: The start time, time zone aware, in the bot's time zone. The API sends local times without a UTC
            offset, so a time in the hour skipped or repeated by a DST change gets the offset in effect before it.
        end: The end time, time zone aware, in the bot's time zone.
        capacity: The total number of places.
        inscribed: The number of places already taken.
        waiting_list: The number of people on the waiting list.
        cancelled: Whether the session is cancelled.
        trainer: The trainer's name, if listed.
    """

    id: int
    activity_id: int
    activity_name: str
    category_id: int
    start: datetime
    end: datetime
    capacity: int
    inscribed: int
    waiting_list: int
    cancelled: bool
    trainer: str | None

    @property
    def is_full(self) -> bool:
        """Whether no places are left."""
        return self.inscribed >= self.capacity

    @property
    def available(self) -> int:
        """The number of places left."""
        return max(self.capacity - self.inscribed, 0)

    @classmethod
    def from_api(cls, data: Mapping[str, Any], time_zone: str) -> Self:
        """
        Build a slot from one entry of the activities calendar.

        Args:
            data: The calendar entry.
            time_zone: The time zone of the centre, attached to the start and end times.

        Raises:
            APIError: If a required field is missing or malformed.
        """
        fields = _Fields(data, Endpoints.SLOTS)
        tz = ZoneInfo(time_zone)
        return cls(
            id=fields.integer("id_activity_calendar"),
            activity_id=fields.integer("id_activity"),
            activity_name=fields.text("name_activity").strip(),
            category_id=fields.integer("id_category_activity"),
            start=fields.timestamp("start_timestamp", tz),
            end=fields.timestamp("end_timestamp", tz),
            capacity=fields.integer("n_capacity"),
            inscribed=fields.integer("n_inscribed"),
            waiting_list=fields.optional_integer("n_waiting_list"),
            cancelled=fields.flag("cancelled"),
            trainer=fields.optional_text("trainer_name"),
        )
