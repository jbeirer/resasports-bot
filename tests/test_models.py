import dataclasses
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from pysportbot import Activity, APIError, Centre, Slot
from pysportbot.endpoints import Endpoints

MADRID = ZoneInfo("Europe/Madrid")


@pytest.fixture
def slot_data(payloads) -> dict:
    """The first entry of the activities calendar fixture: Yoga at 09:00, 5/15."""
    return payloads["activities_calendar"]["data"]["activities_calendar"][0]


@pytest.fixture
def centre_data(payloads) -> dict:
    return payloads["centres"]["applications"][0]


def _slot(**overrides) -> Slot:
    start = datetime(2030, 1, 4, 9, tzinfo=MADRID)
    fields = {
        "id": 1,
        "activity_id": 101,
        "activity_name": "Yoga",
        "category_id": 10,
        "start": start,
        "end": start.replace(hour=10),
        "capacity": 15,
        "inscribed": 5,
        "waiting_list": 0,
        "cancelled": False,
        "trainer": None,
        **overrides,
    }
    return Slot(**fields)


def test_centre_from_api(centre_data):
    assert Centre.from_api(centre_data) == Centre(
        slug="test-centre", name="Test Centre", town="Testville", country="Spain", address="Calle Falsa 123"
    )


@pytest.mark.parametrize("address", [pytest.param({}, id="empty"), pytest.param(None, id="null")])
def test_centre_without_address(centre_data, address):
    centre = Centre.from_api({**centre_data, "address": address})

    assert (centre.town, centre.country, centre.address) == (None, None, None)


@pytest.mark.parametrize("field", ["slug", "name"])
def test_centre_missing_required_field_raises(centre_data, field):
    del centre_data[field]

    with pytest.raises(APIError, match=f"'{field}'") as exc_info:
        Centre.from_api(centre_data)

    assert exc_info.value.endpoint == str(Endpoints.CENTRE)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param({"id_activity": 101, "id_category_activity": 10}, (101, 10), id="int"),
        pytest.param({"id_activity": "101", "id_category_activity": "10"}, (101, 10), id="str"),
    ],
)
def test_activity_coerces_ids(raw, expected):
    activity = Activity.from_api({"name_activity": "Yoga", **raw})

    assert activity == Activity(id=expected[0], name="Yoga", category_id=expected[1])


def test_slot_from_api(slot_data):
    slot = Slot.from_api(slot_data, "Europe/Madrid")

    assert slot == Slot(
        id=5001,
        activity_id=101,
        activity_name="Yoga",
        category_id=10,
        start=datetime(2030, 1, 4, 9, tzinfo=MADRID),
        end=datetime(2030, 1, 4, 10, tzinfo=MADRID),
        capacity=15,
        inscribed=5,
        waiting_list=0,
        cancelled=False,
        trainer="Trainer A",
    )


def test_slot_coerces_str_ids_and_counts(slot_data):
    keys = ["id_activity_calendar", "id_activity", "id_category_activity", "n_capacity", "n_inscribed"]
    slot = Slot.from_api({**slot_data, **{key: str(slot_data[key]) for key in keys}}, "Europe/Madrid")

    assert (slot.id, slot.activity_id, slot.category_id, slot.capacity, slot.inscribed) == (5001, 101, 10, 15, 5)


@pytest.mark.parametrize("time_zone", ["Europe/Madrid", "America/New_York"])
def test_slot_times_are_aware_in_given_time_zone(slot_data, time_zone):
    slot = Slot.from_api(slot_data, time_zone)

    assert slot.start.tzinfo == ZoneInfo(time_zone)
    assert slot.start.replace(tzinfo=None) == datetime(2030, 1, 4, 9)
    assert slot.end - slot.start == datetime(2030, 1, 4, 10) - datetime(2030, 1, 4, 9)


@pytest.mark.parametrize(
    ("cancelled", "expected"),
    [(0, False), (1, True), ("0", False), ("1", True), (False, False), (True, True)],
)
def test_slot_cancelled(slot_data, cancelled, expected):
    assert Slot.from_api({**slot_data, "cancelled": cancelled}, "Europe/Madrid").cancelled is expected


def test_slot_optional_fields_default(slot_data):
    for key in ["n_waiting_list", "cancelled", "trainer_name"]:
        del slot_data[key]

    slot = Slot.from_api(slot_data, "Europe/Madrid")

    assert (slot.waiting_list, slot.cancelled, slot.trainer) == (0, False, None)


@pytest.mark.parametrize(
    "field",
    [
        "id_activity_calendar",
        "id_activity",
        "name_activity",
        "id_category_activity",
        "start_timestamp",
        "end_timestamp",
        "n_capacity",
        "n_inscribed",
    ],
)
@pytest.mark.parametrize("missing", ["deleted", "null"])
def test_slot_missing_required_field_raises(slot_data, field, missing):
    if missing == "deleted":
        del slot_data[field]
    else:
        slot_data[field] = None

    with pytest.raises(APIError, match=f"Missing required field '{field}'") as exc_info:
        Slot.from_api(slot_data, "Europe/Madrid")

    assert exc_info.value.endpoint == str(Endpoints.SLOTS)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("id_activity_calendar", "abc"),
        ("n_capacity", [15]),
        ("start_timestamp", "2030-01-04T09:00:00"),
        ("end_timestamp", "tomorrow"),
        ("cancelled", "yes"),
    ],
)
def test_slot_malformed_field_raises(slot_data, field, value):
    with pytest.raises(APIError, match=f"'{field}'"):
        Slot.from_api({**slot_data, field: value}, "Europe/Madrid")


def test_from_api_rejects_non_object():
    with pytest.raises(APIError, match="Expected a JSON object"):
        Activity.from_api(["not", "an", "object"])  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("capacity", "inscribed", "is_full", "available"),
    [(15, 5, False, 10), (15, 14, False, 1), (15, 15, True, 0), (15, 16, True, 0), (0, 0, True, 0)],
)
def test_slot_is_full_and_available(capacity, inscribed, is_full, available):
    slot = _slot(capacity=capacity, inscribed=inscribed)

    assert slot.is_full is is_full
    assert slot.available == available


def test_models_are_frozen():
    slot = _slot()

    with pytest.raises(dataclasses.FrozenInstanceError):
        slot.inscribed = 0  # type: ignore[misc]
