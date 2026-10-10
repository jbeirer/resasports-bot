import inspect

import pytest

import pysportbot
from pysportbot import exceptions
from pysportbot.exceptions import (
    ActivityNotFoundError,
    APIError,
    AuthenticationError,
    BookingError,
    CancellationError,
    CentreNotFoundError,
    SlotAlreadyBookedError,
    SlotFullError,
    SlotNotBookableYetError,
    SlotNotFoundError,
    SlotUnavailableError,
    SportBotError,
)

EXCEPTION_CLASSES = [
    obj
    for obj in vars(exceptions).values()
    if inspect.isclass(obj) and issubclass(obj, Exception) and obj.__module__ == exceptions.__name__
]

BOOKING_ERROR_CLASSES = [
    BookingError,
    SlotAlreadyBookedError,
    SlotUnavailableError,
    SlotNotBookableYetError,
    SlotFullError,
]


@pytest.mark.parametrize("error_class", EXCEPTION_CLASSES, ids=lambda c: c.__name__)
def test_every_exception_subclasses_sportbot_error(error_class):
    assert issubclass(error_class, SportBotError)
    assert error_class.__doc__


@pytest.mark.parametrize("error_class", EXCEPTION_CLASSES, ids=lambda c: c.__name__)
def test_every_exception_is_exported(error_class):
    assert getattr(pysportbot, error_class.__name__) is error_class
    assert error_class.__name__ in pysportbot.__all__


@pytest.mark.parametrize("error_class", BOOKING_ERROR_CLASSES, ids=lambda c: c.__name__)
def test_booking_errors_carry_slot_id_and_code(error_class):
    error = error_class("5001", 42)

    assert isinstance(error, BookingError)
    assert error.slot_id == "5001"
    assert error.code == 42
    assert "5001" in str(error)
    assert "42" in str(error)


def test_booking_error_code_is_optional():
    error = SlotFullError("5001")

    assert error.code is None
    assert str(error) == "Slot 5001 is full and cannot be booked."


@pytest.mark.parametrize(
    ("error", "expected_parts"),
    [
        pytest.param(
            APIError("Failed to fetch slots", endpoint="https://example.com/slots", status_code=500, body="oops"),
            ["Failed to fetch slots", "https://example.com/slots", "500"],
            id="APIError",
        ),
        pytest.param(AuthenticationError("login returned HTTP 401"), ["login returned HTTP 401"], id="Authentication"),
        pytest.param(CentreNotFoundError("my-gym"), ["my-gym"], id="CentreNotFound"),
        pytest.param(ActivityNotFoundError("Zumba", ["Yoga", "Pilates"]), ["Zumba", "Yoga, Pilates"], id="Activity"),
        pytest.param(SlotNotFoundError("Yoga", "2030-01-04 10:00:00"), ["Yoga", "2030-01-04 10:00:00"], id="Slot"),
        pytest.param(CancellationError("5001"), ["5001"], id="Cancellation"),
    ],
)
def test_message_includes_attributes(error, expected_parts):
    for part in expected_parts:
        assert part in str(error)


def test_api_error_truncates_body():
    error = APIError("Unexpected response", endpoint="https://example.com", body="x" * 500)

    assert error.body == "x" * 200
    assert error.status_code is None


def test_import_from_package_root():
    from pysportbot import SlotNotBookableYetError as Exported

    assert Exported is SlotNotBookableYetError
