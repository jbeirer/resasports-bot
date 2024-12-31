import json

from .endpoints import Endpoints
from .session import Session
from .utils.errors import ErrorMessages
from .utils.logger import get_logger

logger = get_logger(__name__)


class Bookings:
    """Handles booking and cancellation of activity slots."""

    def __init__(self, session: Session) -> None:
        """Initialize the Bookings class."""
        self.session = session.session
        self.headers = session.headers

    def book(self, slot_id: str) -> None:
        """
        Book a specific slot by its ID.

        Args:
            slot_id (str): The unique ID of the activity slot.

        Raises:
            ValueError: If the slot is already booked or unavailable.
            RuntimeError: If an unknown error occurs during booking.
        """
        logger.info(f"Attempting to book slot {slot_id}...")

        # Payload for booking
        payload = {
            "items[activities][0][id_activity_calendar]": slot_id,
            "items[activities][0][unit_price]": "0",
            "items[activities][0][n_guests]": "0",
            "items[activities][0][id_resource]": "false",
            "discount_code": "false",
            "form": "",
            "formIntoNotes": "",
        }

        # Send booking request
        response = self.session.post(Endpoints.BOOKING, data=payload, headers=self.headers)
        response_json = json.loads(response.content.decode("utf-8"))

        # Handle response
        if response_json["error"] == 0:
            logger.info(f"Successfully booked slot {slot_id}.")
        elif response_json["error"] == 5:
            logger.warning(f"Slot {slot_id} is already booked.")
            raise ValueError(ErrorMessages.slot_already_booked())
        elif response_json["error"] == 6:
            logger.warning(f"Slot {slot_id} is not available.")
            raise ValueError(ErrorMessages.slot_unavailable())
        elif response_json["error"] == 28:
            logger.warning(f"Slot {slot_id} is not bookable yet.")
            raise ValueError(ErrorMessages.slot_not_bookable_yet())
        else:
            logger.error(f"Booking failed with error code: {response_json['error']}")
            raise RuntimeError(ErrorMessages.unknown_error("booking"))

    def cancel(self, slot_id: str) -> None:
        """
        Cancel a specific slot by its ID.

        Args:
            slot_id (str): The unique ID of the activity slot.

        Raises:
            ValueError: If the cancellation fails.
        """
        logger.info(f"Attempting to cancel slot {slot_id}...")

        # Payload for cancellation
        payload = {"id_activity_calendar": slot_id}

        # Send cancellation request
        response = self.session.post(Endpoints.CANCELLATION, data=payload, headers=self.headers)
        response_json = json.loads(response.content.decode("utf-8"))

        # Handle response
        if response_json["success"]:
            logger.info(f"Successfully cancelled slot {slot_id}.")
        else:
            logger.warning(f"Slot {slot_id} was not booked.")
            raise ValueError(ErrorMessages.cancellation_failed())
