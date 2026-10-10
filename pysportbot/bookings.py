import logging
from typing import Any

from requests import Response

from .authenticator import Authenticator
from .endpoints import Endpoints
from .exceptions import (
    APIError,
    BookingError,
    CancellationError,
    SlotAlreadyBookedError,
    SlotNotBookableYetError,
    SlotUnavailableError,
)

logger = logging.getLogger(__name__)

# Booking API error codes with a dedicated exception; any other code raises a plain BookingError
_ERROR_CODES: dict[int, type[BookingError]] = {
    5: SlotAlreadyBookedError,
    6: SlotUnavailableError,
    28: SlotNotBookableYetError,
}


class Bookings:
    """Handles booking and cancellation of activity slots."""

    def __init__(self, authenticator: Authenticator) -> None:
        """Initialize the Bookings class."""
        # Session
        self.session = authenticator.session
        # Nubapp credentials
        self.creds = authenticator.creds
        # Headers for requests
        self.headers = authenticator.headers
        # (connect, read) timeout for requests
        self.timeout = authenticator.timeout

    @staticmethod
    def _parse_response(response: Response, action: str) -> dict[str, Any]:
        """
        Validate the HTTP status and body of a booking/cancellation response.

        Args:
            response (Response): The HTTP response.
            action (str): The action name used in error messages ("booking" or "cancellation").

        Returns:
            dict: The parsed JSON body, guaranteed to contain a "success" key.

        Raises:
            APIError: If the status is not 200 or the body is not a JSON object with a boolean "success".
        """
        if response.status_code != 200:
            logger.error(
                f"{action.capitalize()} request failed with status {response.status_code}: {response.text[:200]}"
            )
            raise APIError(
                f"{action.capitalize()} request failed",
                endpoint=response.url,
                status_code=response.status_code,
                body=response.text,
            )

        try:
            response_json: dict[str, Any] = response.json()
        except ValueError as err:
            logger.error(f"Invalid JSON in {action} response: {response.text[:200]}")
            raise APIError(
                f"Invalid JSON in {action} response",
                endpoint=response.url,
                status_code=response.status_code,
                body=response.text,
            ) from err

        success = response_json.get("success") if isinstance(response_json, dict) else None
        # Require a real boolean: a string like "false" would otherwise be truthy
        if success is not True and success is not False:
            logger.error(f"Unexpected {action} response: {response.text[:200]}")
            raise APIError(
                f"Unexpected {action} response",
                endpoint=response.url,
                status_code=response.status_code,
                body=response.text,
            )

        return response_json

    def book(self, slot_id: str) -> None:
        """
        Book a specific slot by its ID.

        Args:
            slot_id (str): The unique ID of the activity slot.

        Raises:
            SlotAlreadyBookedError: If the slot is already booked.
            SlotUnavailableError: If the slot is not available.
            SlotNotBookableYetError: If the slot is not bookable yet.
            BookingError: If the booking fails with any other or no error code.
            APIError: If the response is not a valid booking response.
        """
        logger.debug(f"Attempting to book slot {slot_id}...")

        # Payload for booking
        payload = {"id_user": self.creds["id_user"], "id_activity_calendar": slot_id}

        # Send booking request
        response = self.session.post(Endpoints.BOOKING, data=payload, headers=self.headers, timeout=self.timeout)
        response_json = self._parse_response(response, "booking")
        # Check success directly
        if response_json["success"]:
            logger.debug(f"Successfully booked slot {slot_id}.")
        else:
            # Handle error cases
            error_code = response_json.get("error")
            code = error_code if isinstance(error_code, int) else None
            error_class = _ERROR_CODES.get(code, BookingError) if code is not None else BookingError

            error = error_class(slot_id, code)
            if error_class is BookingError:
                logger.error(f"Booking failed with error code: {error_code}. Response: {response.text[:200]}")
            else:
                logger.warning(str(error))
            raise error

    def cancel(self, slot_id: str) -> None:
        """
        Cancel a specific slot by its ID.

        Args:
            slot_id (str): The unique ID of the activity slot.

        Raises:
            CancellationError: If the cancellation fails.
            APIError: If the response is not a valid cancellation response.
        """
        logger.debug(f"Attempting to cancel slot {slot_id}...")

        # Payload for cancellation
        payload = {"id_user": self.creds["id_user"], "id_activity_calendar": slot_id}

        # Send cancellation request
        response = self.session.post(Endpoints.CANCELLATION, data=payload, headers=self.headers, timeout=self.timeout)
        response_json = self._parse_response(response, "cancellation")

        # Handle response
        if response_json["success"]:
            logger.debug(f"Successfully cancelled slot {slot_id}.")
        else:
            logger.warning(f"Slot {slot_id} was not booked.")
            raise CancellationError(slot_id)
