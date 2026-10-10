import json
import logging
from typing import Any

from .authenticator import Authenticator
from .client import ApiClient
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

    def __init__(self, client: ApiClient, auth: Authenticator) -> None:
        """Initialize the Bookings class."""
        self.client = client
        # Provides id_user for every request
        self.auth = auth

    def _post(self, endpoint: Endpoints, slot_id: str, action: str) -> dict[str, Any]:
        """
        Send a booking or cancellation request for a slot.

        Args:
            endpoint (Endpoints): The booking or cancellation endpoint.
            slot_id (str): The unique ID of the activity slot.
            action (str): The action name used in error messages ("booking" or "cancellation").

        Returns:
            dict: The parsed JSON body, guaranteed to contain a boolean "success" key.

        Raises:
            APIError: If the request fails or the body has no boolean "success".
        """
        payload = {"id_user": self.auth.id_user, "id_activity_calendar": slot_id}
        response_json = self.client.post_json(endpoint, data=payload)

        success = response_json.get("success")
        # Require a real boolean: a string like "false" would otherwise be truthy
        if success is not True and success is not False:
            body = json.dumps(response_json)
            logger.error(f"Unexpected {action} response: {body[:200]}")
            raise APIError(f"Unexpected {action} response", endpoint=endpoint, body=body)

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

        response_json = self._post(Endpoints.BOOKING, slot_id, "booking")
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
                logger.error(
                    f"Booking failed with error code: {error_code}. Response: {json.dumps(response_json)[:200]}"
                )
            else:
                # Expected outcomes, reported by the exception: the caller decides how loudly
                logger.debug(str(error))
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

        response_json = self._post(Endpoints.CANCELLATION, slot_id, "cancellation")

        # Handle response
        if response_json["success"]:
            logger.debug(f"Successfully cancelled slot {slot_id}.")
        else:
            logger.warning(f"Slot {slot_id} was not booked.")
            raise CancellationError(slot_id)
