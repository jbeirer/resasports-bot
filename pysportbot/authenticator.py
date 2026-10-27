import logging
import time
from typing import Any

import requests

from .client import ApiClient
from .endpoints import Endpoints
from .exceptions import APIError, AuthenticationError, CentreNotFoundError, SportBotError

logger = logging.getLogger(__name__)

# Seconds to wait before sending a login request again after a timeout, a connection error or HTTP 5xx. Login requests
# only read, so sending one again is safe; the Resasocial login has been seen to answer in over 10 s once in a while
RETRY_DELAYS = (1.0, 3.0)
# Read timeout of each login request; the login normally answers in about 2 s
LOGIN_READ_TIMEOUT = 15


class Authenticator:
    """
    Handles user authentication against Resasocial and Nubapp.

    Flow overview:

      1. POST /user/login on Resasocial -> Resasocial JWT and the account's (id_user, id_application) pairs.
      2. GET /application/{id_application} for each pair until one has the requested centre's slug.
      3. GET /secure/user/getSportUserToken with the Resasocial JWT -> Nubapp JWT for that centre.
      4. Make the Nubapp JWT the client's bearer token and POST getUser.php to confirm the user.
    """

    def __init__(self, client: ApiClient) -> None:
        self._client = client
        self.authenticated: bool = False
        # Filled by the Resasocial login and sent with every Nubapp request by Activities and Bookings
        self.id_user: str | None = None
        self.id_application: str | None = None
        # Nubapp user ID, confirmed by getUser.php
        self.user_id: str | None = None

    def login(self, email: str, password: str, centre: str) -> None:
        """
        Run the full login flow for the centre with slug `centre`.

        Raises:
            CentreNotFoundError: If the account is not registered at the centre.
            AuthenticationError: If any login step fails.
        """
        logger.info("Starting login process...")
        # Never send a stale Nubapp token along with the new login
        self.reset()
        try:
            resasocial_jwt, apps = self._resasocial_login(email, password)
            self._select_application(apps, centre)
            # Scoped to Nubapp, so the token never reaches Resasocial
            self._client.set_bearer_token(self._get_sport_user_token(resasocial_jwt), base_url=Endpoints.BASE_NUBAPP)
            self.user_id = self._fetch_user_id()
        except Exception as exc:
            self.reset()
            logger.error(f"Login process failed: {exc}")
            if isinstance(exc, (AuthenticationError, CentreNotFoundError)):
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
        """
        Send a login request, and send it again after each of RETRY_DELAYS if it fails in a way that may be temporary.

        Raises:
            AuthenticationError: If the response is bad, naming the step.
            requests.RequestException: If the last attempt fails to get a response.
        """
        for delay in RETRY_DELAYS:
            try:
                return self._request_once(step, method, url, **kwargs)
            except (AuthenticationError, requests.Timeout, requests.ConnectionError) as exc:
                if not _is_temporary(exc):
                    raise
                logger.warning(f"Login step '{step}' failed ({exc}); retrying in {delay:g} s.")
                time.sleep(delay)
        return self._request_once(step, method, url, **kwargs)

    def _request_once(self, step: str, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        """Send a login request, turning an APIError into an AuthenticationError that names the step."""
        # Keep the client's connect timeout, with a longer read timeout
        kwargs.setdefault("timeout", (self._client.timeout[0], LOGIN_READ_TIMEOUT))
        try:
            return self._client.request_json(method, url, **kwargs)
        except APIError as exc:
            status = exc.status_code
            detail = f"HTTP {status}" if status is not None and not 200 <= status < 300 else "an invalid response"
            raise AuthenticationError(f"{step} returned {detail}") from exc

    def _resasocial_login(self, email: str, password: str) -> tuple[str, list[tuple[str, str]]]:
        """Log in to Resasocial and return the Resasocial JWT and the account's (id_user, id_application) pairs."""
        data = self._request("login", "POST", Endpoints.USER_LOGIN, json={"username": email, "password": password})

        jwt, apps = data.get("jwt_token"), data.get("applications") or []
        if not apps:
            raise AuthenticationError("no applications in login response")
        if not jwt or not all(app.get("id_user") and app.get("id_application") for app in apps):
            raise AuthenticationError("login response is missing jwt_token, id_user or id_application")

        logger.info("Resasocial login successful.")
        return str(jwt), [(str(app["id_user"]), str(app["id_application"])) for app in apps]

    def _select_application(self, apps: list[tuple[str, str]], centre: str) -> None:
        """
        Store the id_user and id_application of the application whose slug is `centre`.

        Raises:
            CentreNotFoundError: If no application of the account has that slug.
        """
        slugs = []
        # The login response does not say which centre an application belongs to, so look each one up
        for id_user, id_application in apps:
            url = Endpoints.APPLICATION.format(id_application=id_application)
            slug = self._request("centre lookup", "GET", url).get("slug")
            if not slug:
                raise AuthenticationError("no slug in centre lookup response")
            if slug == centre:
                self.id_user, self.id_application = id_user, id_application
                logger.info(f"Selected centre {centre}. id_user={id_user}, id_application={id_application}")
                return
            slugs.append(str(slug))

        error = CentreNotFoundError(centre, slugs)
        logger.error(str(error))
        raise error

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


def _is_temporary(error: Exception) -> bool:
    """Whether a failed login request may work if sent again: a timeout, a connection error or HTTP 5xx."""
    if isinstance(error, AuthenticationError):
        cause = error.__cause__
        return isinstance(cause, APIError) and cause.status_code is not None and cause.status_code >= 500
    return isinstance(error, requests.Timeout | requests.ConnectionError)
