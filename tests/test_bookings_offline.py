import re
from unittest.mock import patch
from urllib.parse import parse_qs

import pytest
import responses

from pysportbot.authenticator import Authenticator
from pysportbot.bookings import Bookings
from pysportbot.endpoints import Endpoints
from pysportbot.session import Session
from pysportbot.utils.errors import ErrorMessages

SLOT_ID = "5001"


@pytest.fixture
def bookings(mocked_api) -> Bookings:
    auth = Authenticator(Session(), "test-centre")
    auth.login("user@example.com", "password")
    return Bookings(auth)


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
    ("error_code", "message"),
    [
        (5, ErrorMessages.slot_already_booked()),
        (6, ErrorMessages.slot_unavailable()),
        (28, ErrorMessages.slot_not_bookable_yet()),
    ],
)
def test_book_known_error_raises_value_error(bookings, mocked_api, error_code, message):
    mocked_api.replace(responses.POST, str(Endpoints.BOOKING), json={"success": False, "error": error_code})

    with pytest.raises(ValueError, match=re.escape(message)):
        bookings.book(SLOT_ID)


def test_book_unknown_error_raises_runtime_error(bookings, mocked_api):
    mocked_api.replace(responses.POST, str(Endpoints.BOOKING), json={"success": False, "error": 99})

    with pytest.raises(RuntimeError, match=re.escape(ErrorMessages.unknown_error("booking"))):
        bookings.book(SLOT_ID)


def test_book_failure_without_error_code_raises_runtime_error(bookings, mocked_api):
    mocked_api.replace(responses.POST, str(Endpoints.BOOKING), json={"success": False})

    with pytest.raises(RuntimeError, match=re.escape(ErrorMessages.unknown_error("booking"))):
        bookings.book(SLOT_ID)


def test_cancel_success(bookings, mocked_api):
    bookings.cancel(SLOT_ID)

    assert len(_calls_to(mocked_api, Endpoints.CANCELLATION)) == 1


def test_cancel_failure_raises(bookings, mocked_api):
    mocked_api.replace(responses.POST, str(Endpoints.CANCELLATION), json={"success": False})

    with pytest.raises(ValueError, match=re.escape(ErrorMessages.cancellation_failed())):
        bookings.cancel(SLOT_ID)


@pytest.mark.parametrize("method", ["book", "cancel"])
def test_requests_use_authenticator_timeout(bookings, method):
    with patch.object(bookings.session, "post", wraps=bookings.session.post) as post:
        getattr(bookings, method)(SLOT_ID)

    assert post.call_args.kwargs["timeout"] == (5, 10)


@pytest.mark.parametrize(
    ("method", "endpoint", "action"),
    [
        pytest.param("book", Endpoints.BOOKING, "booking", id="book"),
        pytest.param("cancel", Endpoints.CANCELLATION, "cancellation", id="cancel"),
    ],
)
@pytest.mark.parametrize(
    "response_kwargs",
    [
        pytest.param({"status": 500, "body": "<html>Internal Server Error</html>"}, id="non-200"),
        pytest.param({"body": "not json"}, id="invalid-json"),
        pytest.param({"json": {"error": 5}}, id="missing-success"),
        pytest.param({"json": {"success": "false"}}, id="string-success"),
        pytest.param({"json": {"success": 1}}, id="int-success"),
        pytest.param({"json": [{"success": True}]}, id="non-object"),
    ],
)
def test_bad_response_raises_runtime_error(bookings, mocked_api, method, endpoint, action, response_kwargs):
    mocked_api.replace(responses.POST, str(endpoint), **response_kwargs)

    with pytest.raises(RuntimeError, match=re.escape(ErrorMessages.unknown_error(action))):
        getattr(bookings, method)(SLOT_ID)
