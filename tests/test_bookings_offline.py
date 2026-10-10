from unittest.mock import patch
from urllib.parse import parse_qs

import pytest
import responses

from pysportbot.authenticator import Authenticator
from pysportbot.bookings import Bookings
from pysportbot.client import ApiClient
from pysportbot.endpoints import Endpoints
from pysportbot.exceptions import (
    APIError,
    BookingError,
    CancellationError,
    SlotAlreadyBookedError,
    SlotNotBookableYetError,
    SlotUnavailableError,
)

SLOT_ID = "5001"


@pytest.fixture
def bookings(mocked_api) -> Bookings:
    client = ApiClient()
    auth = Authenticator(client)
    auth.login("user@example.com", "password")
    return Bookings(client, auth)


def _calls_to(mocked_api, endpoint):
    return [c for c in mocked_api.calls if c.request.url == str(endpoint)]


def test_book_success(bookings, mocked_api):
    bookings.book(SLOT_ID)

    assert len(_calls_to(mocked_api, Endpoints.BOOKING)) == 1


def test_book_sends_user_and_slot(bookings, mocked_api, payloads):
    bookings.book(SLOT_ID)

    [call] = _calls_to(mocked_api, Endpoints.BOOKING)
    assert parse_qs(call.request.body) == {
        "id_user": [str(payloads["user_login"]["applications"][0]["id_user"])],
        "id_activity_calendar": [SLOT_ID],
    }


@pytest.mark.parametrize(
    ("error_code", "error_class"),
    [
        (5, SlotAlreadyBookedError),
        (6, SlotUnavailableError),
        (28, SlotNotBookableYetError),
    ],
)
def test_book_known_error_raises_specific_error(bookings, mocked_api, error_code, error_class):
    mocked_api.replace(responses.POST, str(Endpoints.BOOKING), json={"success": False, "error": error_code})

    with pytest.raises(error_class) as exc_info:
        bookings.book(SLOT_ID)

    assert exc_info.value.slot_id == SLOT_ID
    assert exc_info.value.code == error_code


@pytest.mark.parametrize(
    ("body", "expected_code"),
    [
        pytest.param({"success": False, "error": 99}, 99, id="unknown-code"),
        pytest.param({"success": False}, None, id="missing-code"),
        pytest.param({"success": False, "error": "5"}, None, id="non-int-code"),
    ],
)
def test_book_other_error_raises_booking_error(bookings, mocked_api, body, expected_code):
    mocked_api.replace(responses.POST, str(Endpoints.BOOKING), json=body)

    with pytest.raises(BookingError) as exc_info:
        bookings.book(SLOT_ID)

    assert type(exc_info.value) is BookingError
    assert exc_info.value.slot_id == SLOT_ID
    assert exc_info.value.code == expected_code


def test_cancel_success(bookings, mocked_api):
    bookings.cancel(SLOT_ID)

    assert len(_calls_to(mocked_api, Endpoints.CANCELLATION)) == 1


def test_cancel_failure_raises(bookings, mocked_api):
    mocked_api.replace(responses.POST, str(Endpoints.CANCELLATION), json={"success": False})

    with pytest.raises(CancellationError) as exc_info:
        bookings.cancel(SLOT_ID)

    assert exc_info.value.slot_id == SLOT_ID


@pytest.mark.parametrize("method", ["book", "cancel"])
def test_requests_use_client_timeout(bookings, method):
    with patch.object(bookings.client.session, "request", wraps=bookings.client.session.request) as post:
        getattr(bookings, method)(SLOT_ID)

    assert post.call_args.kwargs["timeout"] == (5, 10)


@pytest.mark.parametrize(
    ("method", "endpoint"),
    [
        pytest.param("book", Endpoints.BOOKING, id="book"),
        pytest.param("cancel", Endpoints.CANCELLATION, id="cancel"),
    ],
)
# Content errors found after a 2xx response carry no status code
@pytest.mark.parametrize(
    ("response_kwargs", "status_code"),
    [
        pytest.param({"status": 500, "body": "<html>Internal Server Error</html>"}, 500, id="non-200"),
        pytest.param({"body": "not json"}, 200, id="invalid-json"),
        pytest.param({"json": [{"success": True}]}, 200, id="non-object"),
        pytest.param({"json": {"error": 5}}, None, id="missing-success"),
        pytest.param({"json": {"success": "false"}}, None, id="string-success"),
        pytest.param({"json": {"success": 1}}, None, id="int-success"),
    ],
)
def test_bad_response_raises_api_error(bookings, mocked_api, method, endpoint, response_kwargs, status_code):
    mocked_api.replace(responses.POST, str(endpoint), **response_kwargs)

    with pytest.raises(APIError) as exc_info:
        getattr(bookings, method)(SLOT_ID)

    assert exc_info.value.endpoint == str(endpoint)
    assert exc_info.value.status_code == status_code
