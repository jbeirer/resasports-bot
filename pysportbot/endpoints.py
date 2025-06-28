from enum import Enum


class Endpoints(str, Enum):
    """
    API endpoints used throughout the application.

    This enum provides type-safe access to all API endpoints with clear organization
    and automatic string conversion for use in HTTP requests.
    """

    # === Base URLs ===
    BASE_SOCIAL = "https://social.resasports.com"
    BASE_NUBAPP = "https://sport.nubapp.com"

    # === URL Components ===
    NUBAPP_RESOURCES = "web/resources"
    NUBAPP_API = "api/v4"

    # === Centre Management ===
    CENTRE = f"{BASE_SOCIAL}/ajax/applications/bounds/"

    # === Authentication ===
    USER_LOGIN = f"{BASE_SOCIAL}/popup/login"
    LOGIN_CHECK = f"{BASE_SOCIAL}/popup/login_check"
    NUBAPP_LOGIN = f"{BASE_NUBAPP}/{NUBAPP_RESOURCES}/login_from_social.php"

    # === User Management ===
    USER = f"{BASE_NUBAPP}/{NUBAPP_API}/users/getUser.php"

    # === Activities & Scheduling ===
    ACTIVITIES = f"{BASE_NUBAPP}/{NUBAPP_API}/activities/getActivities.php"
    SLOTS = f"{BASE_NUBAPP}/{NUBAPP_API}/activities/getActivitiesCalendar.php"

    # === Booking Management ===
    BOOKING = f"{BASE_NUBAPP}/{NUBAPP_API}/activities/bookActivityCalendar.php"
    CANCELLATION = f"{BASE_NUBAPP}/{NUBAPP_API}/activities/leaveActivityCalendar.php"

    @classmethod
    def get_cred_endpoint(cls, centre_slug: str) -> str:
        """
        Generate the credentials endpoint for a specific centre.

        Args:
            centre_slug (str): The unique identifier for the sports centre

        Returns:
            str: Complete URL for fetching centre credentials

        Example:
            >>> Endpoints.get_cred_endpoint("kirolklub")
            "https://social.resasports.com/ajax/application/kirolklub/book/request"
        """
        return f"{cls.BASE_SOCIAL}/ajax/application/{centre_slug}/book/request"

    def __str__(self) -> str:
        """Return the URL string for direct use in HTTP requests."""
        return str(self.value)
