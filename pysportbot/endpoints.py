from enum import Enum

from .utils.errors import ErrorMessages


class Endpoints(Enum):
    """Enum class for API endpoints used in the application."""

    # Base URLs
    BASE_SOCIAL = "https://social.resasports.com"
    BASE_NUBAPP = "https://sport.nubapp.com/web"

    # Authentication Endpoints
    USER_LOGIN = f"{BASE_SOCIAL}/popup/login"
    LOGIN_CHECK = f"{BASE_SOCIAL}/popup/login_check"
    NUBAP_LOGIN = f"{BASE_NUBAPP}/resources/login_from_social.php"

    # User, activities and slots
    USER = f"{BASE_NUBAPP}/ajax/users/getUser.php"
    ACTIVITIES = f"{BASE_NUBAPP}/ajax/application/getActivities.php"
    SLOTS = f"{BASE_NUBAPP}/ajax/activities/getActivitiesCalendar.php"

    # Booking and Cancellation
    BOOKING = f"{BASE_NUBAPP}/ajax/bookings/bookBookings.php"
    CANCELLATION = f"{BASE_NUBAPP}/ajax/activities/leaveActivityCalendar.php"
    CRED_REQUEST = f"{BASE_SOCIAL}/ajax/application/piscina-municipal-benissa/book/request"

    @classmethod
    def get_endpoint(cls, name: str) -> str:
        """
        Retrieve an endpoint URL by its name.

        Args:
            name (str): The name of the endpoint.

        Returns:
            str: The endpoint URL.

        Raises:
            ValueError: If the endpoint does not exist.
        """
        try:
            return cls[name].value
        except KeyError as err:
            raise ErrorMessages.endpoint_not_found(name) from err
