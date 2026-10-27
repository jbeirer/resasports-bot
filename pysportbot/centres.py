import json
import logging
from typing import Any

import requests

from .client import ApiClient
from .endpoints import Endpoints
from .exceptions import APIError, CentreNotFoundError
from .models import Centre

logger = logging.getLogger(__name__)

# The centres endpoint answers HTTP 500 when an area holds too many centres (a little over 200 in October 2026),
# so a failed area is split in half up to this many times, into at most 2**MAX_SPLITS areas
MAX_SPLITS = 4


class Centres:
    """
    Manages fetching and storing the list of available centres
    from the Resasports service.
    """

    def __init__(self, client: ApiClient) -> None:
        self.client = client
        # Bounding box of the whole world
        self.bounds: dict[str, float] = {"south": -90, "west": -180, "north": 90, "east": 180}
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
            applications = self._fetch_applications(self.bounds, MAX_SPLITS)
        except requests.RequestException as exc:
            logger.exception("Failed to fetch centres.")
            raise APIError("Failed to fetch centres", endpoint=Endpoints.CENTRE) from exc

        if not applications:
            logger.error("Failed to fetch centres: the response contains no centres.")
            raise APIError("Failed to fetch centres: the response contains no centres", endpoint=Endpoints.CENTRE)

        # A centre on the line between two halves is returned by both
        centres = list({c.slug: c for c in map(Centre.from_api, applications)}.values())
        logger.debug(f"Fetched {len(centres)} centres.")
        return centres

    def _fetch_applications(self, bounds: dict[str, float], splits: int) -> list[Any]:
        """
        Fetch the raw centre entries inside `bounds`, splitting it in half along its longer side on HTTP 500.

        Raises:
            APIError: If an area still fails after `splits` splits, or a response is malformed.
            requests.RequestException: If a request itself fails.
        """
        try:
            data = self.client.post_json(Endpoints.CENTRE, json={"bounds": bounds})
        except APIError as exc:
            if exc.status_code != 500 or splits == 0:
                raise
            logger.debug(f"Centres request for {bounds} returned HTTP 500; splitting the area in half.")
            return [app for half in _halves(bounds) for app in self._fetch_applications(half, splits - 1)]

        applications = data.get("applications", [])
        if not isinstance(applications, list):
            raise APIError(
                "Failed to fetch centres: the centres are not a list",
                endpoint=Endpoints.CENTRE,
                body=json.dumps(data),
            )
        return applications


def _halves(bounds: dict[str, float]) -> tuple[dict[str, float], dict[str, float]]:
    """Split a bounding box in half along its longer side."""
    if bounds["east"] - bounds["west"] >= bounds["north"] - bounds["south"]:
        middle = (bounds["west"] + bounds["east"]) / 2
        return {**bounds, "east": middle}, {**bounds, "west": middle}
    middle = (bounds["south"] + bounds["north"]) / 2
    return {**bounds, "north": middle}, {**bounds, "south": middle}
