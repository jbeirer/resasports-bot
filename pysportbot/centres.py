import json
import logging

import requests

from .client import ApiClient
from .endpoints import Endpoints
from .exceptions import APIError, CentreNotFoundError
from .models import Centre

logger = logging.getLogger(__name__)


class Centres:
    """
    Manages fetching and storing the list of available centres
    from the Resasports service.
    """

    def __init__(self, client: ApiClient) -> None:
        self.client = client
        # Coordinates for the bounding box of the world
        # Set to the entire world by default
        self.bounds: dict[str, dict[str, int]] = {
            "bounds": {
                "south": -90,
                "west": -180,
                "north": 90,
                "east": 180,
            }
        }
        # Fetched on first use, so creating a SportBot sends no request
        self._centres: list[Centre] | None = None

    def get(self) -> list[Centre]:
        """
        Return all centres, fetching them on the first call.

        Raises:
            APIError: If the centres cannot be fetched or the response is malformed or empty.
        """
        if self._centres is None:
            self._centres = self.fetch_centres()
        return self._centres

    def search(self, query: str | None = None) -> list[Centre]:
        """
        Return the centres whose slug, name or town contains `query`, ignoring case, or all centres without a query.

        Raises:
            APIError: If the centres cannot be fetched or the response is malformed or empty.
        """
        centres = self.get()
        if not query:
            return list(centres)
        needle = query.casefold()
        return [c for c in centres if any(needle in value.casefold() for value in (c.slug, c.name, c.town) if value)]

    def check_centre(self, centre: str) -> None:
        """
        Check that the user selected centre exists.

        Raises:
            CentreNotFoundError: If the centre is not in the list of available centres.
            APIError: If the centres cannot be fetched or the response is malformed or empty.
        """
        centres = self.get()
        if all(c.slug != centre for c in centres):
            error = CentreNotFoundError(centre)
            logger.error(str(error))
            logger.info(f"Available centres: {', '.join(c.slug for c in centres)}")
            raise error

    def fetch_centres(self) -> list[Centre]:
        """
        Fetches the info of available centres from Resasports.

        Raises:
            APIError: If the centres cannot be fetched or the response is malformed or empty.
        """
        try:
            data = self.client.post_json(Endpoints.CENTRE, json=self.bounds)
        except requests.RequestException as exc:
            logger.exception("Failed to fetch centres.")
            raise APIError("Failed to fetch centres", endpoint=Endpoints.CENTRE) from exc

        applications = data.get("applications")
        if not applications or not isinstance(applications, list):
            logger.error("Failed to fetch centres: the response contains no centres.")
            raise APIError(
                "Failed to fetch centres: the response contains no centres",
                endpoint=Endpoints.CENTRE,
                body=json.dumps(data),
            )

        centres = [Centre.from_api(application) for application in applications]
        logger.debug(f"Fetched {len(centres)} centres.")
        return centres
