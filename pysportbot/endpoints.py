from enum import Enum


class Endpoints(str, Enum):
    """
    Enum class for API endpoints used in the application.
    Each member is a string, so you can use them directly.
    """

    # Base URLs
    BASE_SOCIAL = "https://social.resasports.com"
    BASE_NUBAPP = "https://sport.nubapp.com/web"

    # Centre list
    CENTRE = f"{BASE_SOCIAL}/ajax/applications/bounds/"

    # Authentication Endpoints
    USER_LOGIN = f"{BASE_SOCIAL}/popup/login"
    LOGIN_CHECK = f"{BASE_SOCIAL}/popup/login_check"
    NUBAP_LOGIN = f"{BASE_NUBAPP}/resources/login_from_social.php"

    # User, activities, and slots
    USER = f"{BASE_NUBAPP}/ajax/users/getUser.php"
    ACTIVITIES = f"{BASE_NUBAPP}/ajax/application/getActivities.php"
    SLOTS = f"{BASE_NUBAPP}/ajax/activities/getActivitiesCalendar.php"

    # Booking and Cancellation
    BOOKING = f"{BASE_NUBAPP}/ajax/bookings/bookBookings.php"
    CANCELLATION = f"{BASE_NUBAPP}/ajax/activities/leaveActivityCalendar.php"

    @classmethod
    def get_cred_endpoint(cls, centre_slug: str) -> str:
        """
        Build the booking request URL for a given centre slug.
        """
        return f"{cls.BASE_SOCIAL}/ajax/application/{centre_slug}/book/request"

    def __str__(self) -> str:
        """Return the underlying string value instead of the member name."""
        return str(self.value)
