from typing import Any

from requests import Response

from .authenticator import Authenticator
from .endpoints import Endpoints
from .utils.errors import ErrorMessages
from .utils.logger import get_logger

logger = get_logger(__name__)


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
            RuntimeError: If the status is not 200 or the body is not a JSON object with "success".
        """
        if response.status_code != 200:
            logger.error(
                f"{action.capitalize()} request failed with status {response.status_code}: {response.text[:200]}"
            )
            raise RuntimeError(ErrorMessages.unknown_error(action))

        try:
            response_json = response.json()
        except ValueError as err:
            logger.error(f"Invalid JSON in {action} response: {response.text[:200]}")
            raise RuntimeError(ErrorMessages.unknown_error(action)) from err

        if not isinstance(response_json, dict) or "success" not in response_json:
            logger.error(f"Unexpected {action} response: {response.text[:200]}")
            raise RuntimeError(ErrorMessages.unknown_error(action))

        return response_json

    def book(self, slot_id: str) -> None:
        """
        Book a specific slot by its ID.

        Args:
            slot_id (str): The unique ID of the activity slot.

        Raises:
            ValueError: If the slot is already booked or unavailable.
            RuntimeError: If an unknown error occurs during booking.
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
            error_code = response_json["error"]  # Now we know it exists when success=False

            if error_code == 5:
                logger.warning(f"Slot {slot_id} is already booked.")
                raise ValueError(ErrorMessages.slot_already_booked())
            elif error_code == 6:
                logger.warning(f"Slot {slot_id} is not available.")
                raise ValueError(ErrorMessages.slot_unavailable())
            elif error_code == 28:
                logger.warning(f"Slot {slot_id} is not bookable yet.")
                raise ValueError(ErrorMessages.slot_not_bookable_yet())
            else:
                logger.error(f"Booking failed with error code: {error_code}")
                raise RuntimeError(ErrorMessages.unknown_error("booking"))

    def cancel(self, slot_id: str) -> None:
        """
        Cancel a specific slot by its ID.

        Args:
            slot_id (str): The unique ID of the activity slot.

        Raises:
            ValueError: If the cancellation fails.
            RuntimeError: If the response is not a valid cancellation response.
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
            raise ValueError(ErrorMessages.cancellation_failed())
