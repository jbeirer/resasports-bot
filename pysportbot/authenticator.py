import ast
import json
from urllib.parse import parse_qs

from bs4 import BeautifulSoup

from .endpoints import Endpoints
from .session import Session
from .utils.errors import ErrorMessages
from .utils.logger import get_logger

logger = get_logger(__name__)


class Authenticator:
    """Handles user authentication and Nubapp login functionality."""

    def __init__(self, session: Session) -> None:
        """
        Initialize the Authenticator.

        Args:
            session (Session): An instance of the Session class.
        """
        self.session = session.session
        self.headers = session.headers

    def login(self, email: str, password: str) -> None:
        """
        Authenticate the user with email and password and log in to Nubapp.

        Args:
            email (str): The user's email address.
            password (str): The user's password.

        Raises:
            RuntimeError: If the login process fails at any stage.
        """
        logger.info("Starting login process...")

        # Step 1: Fetch CSRF token
        logger.debug(f"GET {Endpoints.USER_LOGIN.value} | Headers: {json.dumps(self.headers, indent=2)}")
        response = self.session.get(Endpoints.USER_LOGIN.value, headers=self.headers)
        if response.status_code != 200:
            logger.error(f"Failed to fetch login popup: {response.status_code}")
            raise RuntimeError(ErrorMessages.failed_fetch("login popup"))
        logger.debug("Login popup fetched successfully.")
        csrf_token = BeautifulSoup(response.text, "html.parser").find("input", {"name": "_csrf_token"})["value"]

        # Step 2: Perform login
        payload = {
            "_username": email,
            "_password": password,
            "_csrf_token": csrf_token,
            "_submit": "",
            "_force": "true",
        }
        self.headers.update({"Content-Type": "application/x-www-form-urlencoded"})
        logger.debug(
            f"POST {Endpoints.LOGIN_CHECK.value} | Headers: {json.dumps(self.headers, indent=2)} | "
            f"Payload: {json.dumps(payload, indent=2)}"
        )
        response = self.session.post(Endpoints.LOGIN_CHECK.value, data=payload, headers=self.headers)
        if response.status_code != 200:
            logger.error(f"Login failed: {response.status_code}, {response.text}")
            raise ValueError(ErrorMessages.failed_login())
        logger.info("Login successful!")

        # Step 3: Retrieve credentials for Nubapp
        logger.debug(f"GET {Endpoints.CRED_REQUEST.value} | Headers: {json.dumps(self.headers, indent=2)}")
        response = self.session.get(Endpoints.CRED_REQUEST.value, headers=self.headers)
        if response.status_code != 200:
            logger.error(f"Failed to retrieve Nubapp credentials: {response.status_code}")
            raise RuntimeError(ErrorMessages.failed_fetch("credentials"))
        nubapp_creds = ast.literal_eval(response.content.decode("utf-8"))["payload"]
        nubapp_creds = {k: v[0] for k, v in parse_qs(nubapp_creds).items()}
        nubapp_creds["platform"] = "resasocial"
        nubapp_creds["network"] = "resasports"
        logger.debug(f"Nubapp credentials retrieved: {json.dumps(nubapp_creds, indent=2)}")

        # Step 4: Log in to Nubapp
        logger.debug(
            f"GET {Endpoints.NUBAP_LOGIN.value} | Headers: {json.dumps(self.headers, indent=2)} | "
            f"Params: {json.dumps(nubapp_creds, indent=2)}"
        )
        response = self.session.get(Endpoints.NUBAP_LOGIN.value, headers=self.headers, params=nubapp_creds)
        if response.status_code != 200:
            logger.error(f"Login to Nubapp failed: {response.status_code}, {response.text}")
            raise ValueError(ErrorMessages.failed_login_nubapp())
        logger.info("Login to Nubapp successful!")
