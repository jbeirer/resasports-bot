import ast
import json
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup

from .endpoints import Endpoints
from .session import Session
from .utils.errors import ErrorMessages
from .utils.logger import get_logger

logger = get_logger(__name__)


class Authenticator:
    """Handles user authentication and Nubapp login functionality."""

    def __init__(self, session: Session, centre: str) -> None:
        """
        Initialize the Authenticator.

        Args:
            session (Session): An instance of the Session class.
            centre (str): The centre selected by the user.
        """
        self.session = session.session
        self.headers = session.headers
        self.creds: dict[str, str] = {}
        self.centre = centre
        self.timeout = (5, 10)

        # Authentication state
        self.authenticated = False
        self.user_id: str | None = None

    def is_session_valid(self) -> bool:
        """
        Check if the current session is still valid.

        Returns:
            bool: True if session is valid, False otherwise.
        """
        try:
            response = self.session.post(Endpoints.USER, headers=self.headers, timeout=self.timeout)
            if response.status_code == 200:
                response_dict = json.loads(response.content.decode("utf-8"))
                return bool(response_dict.get("user"))

        except Exception as e:
            logger.debug(f"Session validation failed with exception: {e}")
            return False
        else:
            logger.debug(f"Session validation failed with status code: {response.status_code}")
            return False

    def login(self, email: str, password: str) -> None:
        """
        Authenticate the user with email and password and log in to Nubapp.

        Args:
            email (str): The user's email address.
            password (str): The user's password.

        Raises:
            ValueError: If login credentials are invalid or authentication fails.
            RuntimeError: If the login process fails due to system errors.
        """
        logger.info("Starting login process...")

        try:
            # Fetch the CSRF token and perform login
            csrf_token = self._fetch_csrf_token()
            # Resasport login with CSRF token
            self._resasports_login(email, password, csrf_token)
            # Retrieve Nubapp credentials
            self._retrieve_nubapp_credentials()
            bearer_token = self._login_to_nubapp()
            # Authenticate with the bearer token
            self._authenticate_with_bearer_token(bearer_token)
            # Fetch user information to complete the login process
            self._fetch_user_information()

            logger.info("Login process completed successfully!")

        except Exception as e:
            self.authenticated = False
            self.user_id = None
            logger.error(f"Login process failed: {e}")
            raise

    def _fetch_csrf_token(self) -> str:
        """Fetch CSRF token from the login page."""
        logger.debug(f"Fetching CSRF token from {Endpoints.USER_LOGIN}")

        response = self.session.get(Endpoints.USER_LOGIN, headers=self.headers, timeout=self.timeout)
        if response.status_code != 200:
            raise RuntimeError(ErrorMessages.failed_fetch("login popup"))

        soup = BeautifulSoup(response.text, "html.parser")
        csrf_tag = soup.find("input", {"name": "_csrf_token"})
        if csrf_tag is None:
            raise ValueError("CSRF token input not found on the page")

        csrf_token = str(csrf_tag["value"])  # type: ignore[index]
        logger.debug("CSRF token fetched successfully")
        return csrf_token

    def _resasports_login(self, email: str, password: str, csrf_token: str) -> None:
        """Perform login to the main site."""
        logger.debug("Performing site login")

        payload = {
            "_username": email,
            "_password": password,
            "_csrf_token": csrf_token,
            "_submit": "",
            "_force": "true",
        }

        headers = self.headers.copy()
        headers.update({"Content-Type": "application/x-www-form-urlencoded"})

        response = self.session.post(Endpoints.LOGIN_CHECK, data=payload, headers=headers, timeout=self.timeout)

        if response.status_code != 200:
            logger.error(f"Site login failed: {response.status_code}")
            raise ValueError(ErrorMessages.failed_login())

        logger.info("Site login successful!")

    def _retrieve_nubapp_credentials(self) -> None:
        """Retrieve Nubapp credentials from the centre endpoint."""
        logger.debug("Retrieving Nubapp credentials")

        cred_endpoint = Endpoints.get_cred_endpoint(self.centre)
        response = self.session.get(cred_endpoint, headers=self.headers, timeout=self.timeout)

        if response.status_code != 200:
            raise RuntimeError(ErrorMessages.failed_fetch("credentials"))

        try:
            creds_payload = ast.literal_eval(response.content.decode("utf-8"))["payload"]
            creds = {k: v[0] for k, v in parse_qs(creds_payload).items()}
            creds.update({"platform": "resasocial", "network": "resasports"})

            self.creds = creds
            logger.debug("Nubapp credentials retrieved successfully")

        except (ValueError, KeyError, SyntaxError) as e:
            raise RuntimeError(f"Failed to parse credentials: {e}") from e

    def _login_to_nubapp(self) -> str:
        """Login to Nubapp and extract bearer token."""
        logger.debug("Logging in to Nubapp")

        response = self.session.get(
            Endpoints.NUBAP_LOGIN,
            headers=self.headers,
            params=self.creds,
            timeout=self.timeout,
            allow_redirects=False,
        )

        if response.status_code != 302:
            logger.error(f"Nubapp login failed: {response.status_code}")
            raise ValueError(ErrorMessages.failed_login())

        # Extract bearer token from redirect URL
        redirect_url = response.headers.get("Location", "")
        if not redirect_url:
            raise ValueError(ErrorMessages.failed_login())

        parsed_url = urlparse(redirect_url)
        token = parse_qs(parsed_url.query).get("token", [None])[0]

        if not token:
            raise ValueError(ErrorMessages.failed_login())

        logger.info("Nubapp login successful!")
        return token

    def _authenticate_with_bearer_token(self, token: str) -> None:
        """Add bearer token to headers for authentication."""
        logger.debug("Setting up bearer token authentication")
        self.headers["Authorization"] = f"Bearer {token}"

    def _fetch_user_information(self) -> None:
        """Fetch and validate user information."""
        logger.debug("Fetching user information")

        payload = {
            "id_application": self.creds["id_application"],
            "id_user": self.creds["id_user"],
        }

        response = self.session.post(Endpoints.USER, headers=self.headers, data=payload, timeout=self.timeout)

        if response.status_code != 200:
            raise ValueError(ErrorMessages.failed_login())

        try:
            response_dict = json.loads(response.content.decode("utf-8"))
            user_data = response_dict.get("data", {}).get("user")

            if not user_data:
                raise ValueError("No user data found in response")

            user_id = user_data.get("id_user")
            if not user_id:
                raise ValueError("No user ID found in response")

            self.user_id = str(user_id)
            self.authenticated = True
            logger.info(f"Authentication successful. User ID: {self.user_id}")

        except (json.JSONDecodeError, KeyError) as e:
            raise ValueError(f"Failed to parse user information: {e}") from e
