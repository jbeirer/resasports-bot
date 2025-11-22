from enum import Enum


class Endpoints(str, Enum):
    """
    Centralized collection of API endpoints used by the bot.

    This enum provides type-safe access to all URLs with clear structure.
    """

    # ============================================================
    # Base URLs
    # ============================================================

    # Resasocial / Resasports API (used for login, centre data, etc.)
    BASE_SOCIAL = "https://api.resasocial.com"

    # Nubapp API (used for bookings, user data, etc.)
    BASE_NUBAPP = "https://sport.nubapp.com"

    # Path used for all Nubapp JSON API endpoints
    NUBAPP_API = "api/v4"

    # ============================================================
    # Centre Management
    # ============================================================

    # Returns the list of centres with their bounds / metadata.
    # Used by Centres.fetch_centres() to populate the centre list (slug, name, etc).
    CENTRE = f"{BASE_SOCIAL}/ajax/applications/bounds/"

    # ============================================================
    # Authentication
    # ============================================================

    # Resasports login endpoint
    USER_LOGIN = f"{BASE_SOCIAL}/user/login"

    # Nubapp authentification via JWT token
    SPORT_USER_TOKEN = f"{BASE_SOCIAL}/secure/user/getSportUserToken"

    # ============================================================
    # Nubapp User & Application
    # ============================================================

    # User information endpoint (requires Nubapp JWT)
    USER = f"{BASE_NUBAPP}/{NUBAPP_API}/users/getUser.php"

    # ============================================================
    # Activities & Scheduling
    # ============================================================

    ACTIVITIES = f"{BASE_NUBAPP}/{NUBAPP_API}/activities/getActivities.php"
    SLOTS = f"{BASE_NUBAPP}/{NUBAPP_API}/activities/getActivitiesCalendar.php"

    # ============================================================
    # Booking
    # ============================================================

    BOOKING = f"{BASE_NUBAPP}/{NUBAPP_API}/activities/bookActivityCalendar.php"
    CANCELLATION = f"{BASE_NUBAPP}/{NUBAPP_API}/activities/leaveActivityCalendar.php"

    # ============================================================
    # Utility
    # ============================================================

    def __str__(self) -> str:
        """Return URL string for direct HTTP usage."""
        return str(self.value)
