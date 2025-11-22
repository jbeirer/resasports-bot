import json

from .endpoints import Endpoints
from .session import Session
from .utils.errors import ErrorMessages
from .utils.logger import get_logger

logger = get_logger(__name__)


class Authenticator:
    """
    Handles user authentication and Nubapp login functionality.

    Flow overview:

      1. Login to Resasocial (api.resasocial.com) via /user/login
         -> get Resasocial JWT + (id_user, id_application).

      2. Store (id_user, id_application) in self.creds for use by Activities.

      3. Call /secure/user/getSportUserToken with the Resasocial JWT
         -> get Nubapp (sport.nubapp.com) JWT.

      4. Store Nubapp JWT in self.headers["Authorization"].

      5. Use Nubapp JWT to call /api/v4/users/getUser.php and verify the user.
    """

    def __init__(self, session: Session, centre: str) -> None:
        self.session = session.session
        # Base headers; will be enriched with Nubapp JWT after login
        self.headers = session.headers
        # Centre is still passed in from the bot, but not used in the new flow
        self.centre = centre
        self.timeout = (5, 10)

        # Authentication state
        self.authenticated: bool = False
        self.user_id: str | None = None

        # Minimal "credentials" object used by Activities
        # (id_application, id_user) are filled after /user/login.
        self.creds: dict[str, str] = {}

        # Resasocial (resasports) JWT state
        self.resasocial_jwt: str | None = None
        self.resasocial_refresh: str | None = None
        self.id_user: str | None = None
        self.id_application: str | None = None

        # Nubapp JWT tokens used for authenticated sport.nubapp.com requests
        self.sport_jwt: str | None = None
        self.sport_refresh: str | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def login(self, email: str, password: str) -> None:
        """
        Full login flow:

          1. Resasocial JSON login (/user/login)
          2. Fill self.creds with (id_application, id_user) for Activities
          3. /secure/user/getSportUserToken -> Nubapp JWT
          4. Store Nubapp JWT in headers and fetch user info to confirm identity
        """
        logger.info("Starting login process...")

        try:
            self._resasocial_jwt_login(email, password)

            # Expose IDs in the same structure Activities expects
            self.creds = {
                "id_application": str(self.id_application),
                "id_user": str(self.id_user),
            }

            self._get_sport_user_token()
            self._authenticate_with_bearer_token(self.sport_jwt)
            self._fetch_user_information()

            self.authenticated = True
            logger.info("Login process completed successfully!")

        except Exception as exc:
            self.authenticated = False
            self.user_id = None
            logger.error(f"Login process failed: {exc}")
            # Normalize to a consistent login error for callers/tests
            raise ValueError(ErrorMessages.failed_login()) from exc

    def is_session_valid(self) -> bool:
        """
        Check whether the current Nubapp JWT is still valid by probing USER.
        """
        if not self.sport_jwt:
            return False

        try:
            # At this point self.headers already contains Nubapp Authorization
            response = self.session.post(
                Endpoints.USER,
                headers=self.headers,
                timeout=self.timeout,
            )

            if response.status_code != 200:
                return False

            data = response.json()
            return bool(data.get("data", {}).get("user"))

        except Exception as exc:
            logger.debug(f"Session validation failed: {exc}")
            return False

    # ------------------------------------------------------------------
    # Step 1: Resasocial JWT login
    # ------------------------------------------------------------------

    def _resasocial_jwt_login(self, email: str, password: str) -> None:
        """Perform login via the /user/login JSON endpoint on api.resasocial.com."""
        logger.debug("Logging in via Resasocial /user/login (JWT flow)")

        payload = {"username": email, "password": password}
        # Use a copy of the base headers: no Authorization here.
        headers = self.headers.copy()

        response = self.session.post(
            Endpoints.USER_LOGIN,
            json=payload,
            headers=headers,
            timeout=self.timeout,
        )

        if response.status_code != 200:
            logger.error(
                "JWT login failed with status %s. Body (truncated): %r",
                response.status_code,
                response.text[:200],
            )
            raise ValueError(ErrorMessages.failed_login())

        try:
            data = response.json()
        except Exception as exc:
            logger.error(
                "JWT login returned non-JSON response. Body (truncated): %r",
                response.text[:200],
            )
            raise ValueError(ErrorMessages.failed_login()) from exc

        logger.debug(
            "/user/login response keys: %s; applications count=%d",
            list(data.keys()),
            len(data.get("applications") or []),
        )

        self.resasocial_jwt = data.get("jwt_token")
        self.resasocial_refresh = data.get("refresh_token")

        apps = data.get("applications") or []
        if not apps:
            logger.error("No applications returned in /user/login response")
            raise ValueError(ErrorMessages.failed_login())

        first_app = apps[0]
        self.id_application = first_app.get("id_application")
        self.id_user = first_app.get("id_user")

        if not self.resasocial_jwt or not self.id_user or not self.id_application:
            logger.error(
                "Missing required fields in /user/login response: "
                f"jwt_token={self.resasocial_jwt}, id_user={self.id_user}, "
                f"id_application={self.id_application}"
            )
            raise ValueError(ErrorMessages.failed_login())

        logger.info(
            "JWT login successful. id_user=%s, id_application=%s",
            self.id_user,
            self.id_application,
        )

    # ------------------------------------------------------------------
    # Step 3: getSportUserToken -> Nubapp JWT
    # ------------------------------------------------------------------

    def _get_sport_user_token(self) -> None:
        """
        Request the Nubapp JWT token using the Resasocial JWT.
        This replaces the old login_from_social.php redirect method.
        """
        logger.debug("Fetching Nubapp JWT via getSportUserToken")

        if not self.resasocial_jwt or not self.id_user or not self.id_application:
            logger.error("Cannot fetch sport user token without resasocial_jwt, id_user, id_application")
            raise ValueError(ErrorMessages.failed_login())

        # Local headers specific to this Resasocial-authenticated call
        social_auth_headers = self.headers.copy()
        social_auth_headers["Authorization"] = f"Bearer {self.resasocial_jwt}"

        params = {
            "id_user": self.id_user,
            "id_application": self.id_application,
        }

        response = self.session.get(
            Endpoints.SPORT_USER_TOKEN,
            params=params,
            headers=social_auth_headers,
            timeout=self.timeout,
        )

        if response.status_code != 200:
            logger.error(
                "getSportUserToken failed with status %s. Body (truncated): %r",
                response.status_code,
                response.text[:200],
            )
            raise ValueError(ErrorMessages.failed_login())

        try:
            data = response.json()
        except Exception as exc:
            logger.error(
                "getSportUserToken returned non-JSON response. Body (truncated): %r",
                response.text[:200],
            )
            raise ValueError(ErrorMessages.failed_login()) from exc

        logger.debug("response keys: %s", list(data.keys()))

        self.sport_jwt = data.get("jwt_token")
        self.sport_refresh = data.get("refresh_token")

        if not self.sport_jwt:
            logger.error("No jwt_token found in getSportUserToken response")
            raise ValueError(ErrorMessages.failed_login())

        logger.info("Nubapp JWT obtained successfully.")

    # ------------------------------------------------------------------
    # Step 4: Set Authorization header for Nubapp
    # ------------------------------------------------------------------

    def _authenticate_with_bearer_token(self, token: str | None) -> None:
        """
        Store the Nubapp JWT in self.headers so that all subsequent
        Nubapp API calls (including Activities) share the same auth.
        """
        if not token:
            raise ValueError(ErrorMessages.failed_login())

        logger.debug("Setting Nubapp Authorization header")
        self.headers["Authorization"] = f"Bearer {token}"

    # ------------------------------------------------------------------
    # Step 5: Nubapp User info
    # ------------------------------------------------------------------

    def _fetch_user_information(self) -> None:
        """
        Fetch and validate user information from Nubapp.

        No extra payload — we just rely on the Nubapp JWT already set in self.headers.
        """
        logger.debug("Fetching user info from Nubapp")

        if not self.sport_jwt:
            raise ValueError(ErrorMessages.failed_login())

        response = self.session.post(
            Endpoints.USER,
            headers=self.headers,
            timeout=self.timeout,
        )

        if response.status_code != 200:
            logger.error(
                "Fetching user info failed with status %s. Body (truncated): %r",
                response.status_code,
                response.text[:200],
            )
            raise ValueError(ErrorMessages.failed_login())

        try:
            data = response.json()
        except (json.JSONDecodeError, ValueError) as exc:
            raise ValueError(f"Failed to parse user information: {exc}") from exc

        user_data = data.get("data", {}).get("user")
        if not user_data:
            raise ValueError("No user data found in response")

        user_id = user_data.get("id_user")
        if not user_id:
            raise ValueError("No user ID found in response")

        self.user_id = str(user_id)
        logger.info("Authentication successful. User ID: %s", self.user_id)
