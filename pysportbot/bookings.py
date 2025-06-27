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
        logger.debug(f"Attempting to book slot {slot_id}...")

        # Payload for booking
        payload = {
            "id_user": self.session.nubapp_creds["id_user"],
            "id_activity_calendar": slot_id
        }

        # Send booking request
        response = self.session.post(
            Endpoints.BOOKING, data=payload, headers=self.headers)
        response_json = json.loads(response.content.decode("utf-8"))
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
        """
        logger.debug(f"Attempting to cancel slot {slot_id}...")

        # Payload for cancellation
        payload = {
            "id_user": self.session.nubapp_creds["id_user"],
            "id_activity_calendar": slot_id
        }

        # Send cancellation request
        response = self.session.post(
            Endpoints.CANCELLATION, data=payload, headers=self.headers)
        response_json = json.loads(response.content.decode("utf-8"))

        # Handle response
        if response_json["success"]:
            logger.debug(f"Successfully cancelled slot {slot_id}.")
        else:
            logger.warning(f"Slot {slot_id} was not booked.")
            raise ValueError(ErrorMessages.cancellation_failed())
