import logging
from typing import Any

import requests

from .client import ApiClient
from .endpoints import Endpoints
from .exceptions import APIError, AuthenticationError, SportBotError

logger = logging.getLogger(__name__)


class Authenticator:
    """
    Handles user authentication against Resasocial and Nubapp.

    Flow overview:

      1. POST /user/login on Resasocial -> Resasocial JWT, id_user and id_application.
      2. GET /secure/user/getSportUserToken with the Resasocial JWT -> Nubapp JWT.
      3. Make the Nubapp JWT the client's bearer token and POST getUser.php to confirm the user.
    """

    def __init__(self, client: ApiClient) -> None:
        self._client = client
        self.authenticated: bool = False
        # Filled by the Resasocial login and sent with every Nubapp request by Activities and Bookings
        self.id_user: str | None = None
        self.id_application: str | None = None
        # Nubapp user ID, confirmed by getUser.php
        self.user_id: str | None = None

    def login(self, email: str, password: str) -> None:
        """
        Run the full login flow.

        Raises:
            AuthenticationError: If any login step fails.
        """
        logger.info("Starting login process...")
        # Never send a stale Nubapp token along with the new login
        self.reset()
        try:
            resasocial_jwt = self._resasocial_login(email, password)
            # Scoped to Nubapp, so the token never reaches Resasocial
            self._client.set_bearer_token(self._get_sport_user_token(resasocial_jwt), base_url=Endpoints.BASE_NUBAPP)
            self.user_id = self._fetch_user_id()
        except Exception as exc:
            self.reset()
            logger.error(f"Login process failed: {exc}")
            if isinstance(exc, AuthenticationError):
                raise
            # Normalize unexpected errors to a consistent login error for callers
            raise AuthenticationError(f"unexpected error ({exc})") from exc

        self.authenticated = True
        logger.info("Login process completed successfully!")

    def is_session_valid(self) -> bool:
        """Check whether the current Nubapp JWT is still accepted, by probing the user endpoint."""
        if not self.authenticated:
            return False
        try:
            data = self._client.post_json(Endpoints.USER).get("data")
        except (SportBotError, requests.RequestException) as exc:
            logger.debug(f"Session validation failed: {exc}")
            return False
        return isinstance(data, dict) and bool(data.get("user"))

    def reset(self) -> None:
        """Forget the login state and stop sending the Nubapp token."""
        self.authenticated = False
        self.id_user = self.id_application = self.user_id = None
        self._client.clear_bearer_token()

    def _request(self, step: str, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        """Send a login request, turning an APIError into an AuthenticationError that names the step."""
        try:
            return self._client.request_json(method, url, **kwargs)
        except APIError as exc:
            status = exc.status_code
            detail = f"HTTP {status}" if status is not None and not 200 <= status < 300 else "an invalid response"
            raise AuthenticationError(f"{step} returned {detail}") from exc

    def _resasocial_login(self, email: str, password: str) -> str:
        """Log in to Resasocial, store id_user and id_application, and return the Resasocial JWT."""
        data = self._request("login", "POST", Endpoints.USER_LOGIN, json={"username": email, "password": password})

        apps = data.get("applications") or []
        if not apps:
            raise AuthenticationError("no applications in login response")
        # The login response does not show which centre an application belongs to, so take the first one
        if len(apps) > 1:
            ids = [app.get("id_application") for app in apps]
            logger.warning(f"Account belongs to {len(apps)} applications {ids}; using the first one.")

        jwt, id_user, id_application = data.get("jwt_token"), apps[0].get("id_user"), apps[0].get("id_application")
        if not jwt or not id_user or not id_application:
            raise AuthenticationError("login response is missing jwt_token, id_user or id_application")

        self.id_user, self.id_application = str(id_user), str(id_application)
        logger.info(f"Resasocial login successful. id_user={self.id_user}, id_application={self.id_application}")
        return str(jwt)

    def _get_sport_user_token(self, resasocial_jwt: str) -> str:
        """Exchange the Resasocial JWT for a Nubapp JWT."""
        params = {"id_user": self.id_user, "id_application": self.id_application}
        # Per-request headers merge over the session headers, so only Authorization is added here
        headers = {"Authorization": f"Bearer {resasocial_jwt}"}
        data = self._request("getSportUserToken", "GET", Endpoints.SPORT_USER_TOKEN, params=params, headers=headers)

        if not data.get("jwt_token"):
            raise AuthenticationError("no jwt_token in getSportUserToken response")
        logger.info("Nubapp JWT obtained successfully.")
        return str(data["jwt_token"])

    def _fetch_user_id(self) -> str:
        """Confirm the Nubapp JWT by fetching the user, and return the Nubapp user ID."""
        data = self._request("user information request", "POST", Endpoints.USER)

        user = data.get("data", {}).get("user")
        if not user:
            raise AuthenticationError("no user data in user information response")
        if not user.get("id_user"):
            raise AuthenticationError("no user ID in user information response")

        logger.info(f"Authentication successful. User ID: {user['id_user']}")
        return str(user["id_user"])
