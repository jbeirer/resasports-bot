from requests import Session as RequestsSession

from .utils.logger import get_logger

logger = get_logger(__name__)


class Session:
    """Handles the session and headers for HTTP requests."""

    def __init__(self) -> None:
        """Initialize a new session and set default headers."""
        self.session: RequestsSession = RequestsSession()
        self.headers: dict[str, str] = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:133.0) Gecko/20100101 Firefox/133.0",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.5",
            "DNT": "1",
            "Sec-GPC": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "TE": "trailers",
        }
        logger.info("Session initialized.")

    def set_header(self, key: str, value: str) -> None:
        """
        Set or update a header in the session.

        Args:
            key (str): The header key to set or update.
            value (str): The header value to assign.
        """
        self.headers[key] = value
        logger.debug(f"Header updated: {key} = {value}")

    def get_session(self) -> RequestsSession:
        """
        Get the underlying Requests session object.

        Returns:
            RequestsSession: The Requests session instance.
        """
        return self.session
