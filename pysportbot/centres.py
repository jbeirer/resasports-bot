# centres.py

import logging

import pandas as pd
import requests
from pandas import DataFrame

from .endpoints import Endpoints
from .exceptions import APIError, CentreNotFoundError

logger = logging.getLogger(__name__)


class Centres:
    """
    Manages fetching and storing the list of available centres
    from the Resasports service.
    """

    def __init__(self, print_centres: bool = False) -> None:
        # Coordinates for the bounding box of the world
        # Set to the entire world by default
        self.bounds: dict = {
            "bounds": {
                "south": -90,
                "west": -180,
                "north": 90,
                "east": 180,
            }
        }
        self._df_centres = self.fetch_centres()

        # list of centre (slugs)
        self.centre_list = self._df_centres["slug"].tolist()

        if print_centres:
            self.print_centres()

    def check_centre(self, centre: str) -> None:
        """
        Set the user selected centre.

        Raises:
            CentreNotFoundError: If the centre is not in the list of available centres.
        """
        if centre not in self.centre_list:
            error = CentreNotFoundError(centre)
            logger.error(str(error))
            self.print_centres()
            raise error

    def fetch_centres(self) -> DataFrame:
        """
        Fetches the info of available centres from Resasports and returns a DataFrame.

        Raises:
            APIError: If the centres cannot be fetched or the response is malformed or empty.
        """
        response = None
        try:
            response = requests.post(
                Endpoints.CENTRE,
                json=self.bounds,
                timeout=10,
            )
            response.raise_for_status()

            # Flatten and extract the desired columns
            df = pd.json_normalize(response.json()["applications"])
            df = df[["slug", "name", "address.town", "address.country", "address.street_line"]]
            df.columns = ["slug", "name", "town", "country", "address"]
        except Exception as exc:
            logger.exception("Failed to fetch centres.")
            raise APIError(
                "Failed to fetch centres",
                endpoint=Endpoints.CENTRE,
                status_code=response.status_code if response is not None else None,
                body=response.text if response is not None else "",
            ) from exc

        if df.empty:
            logger.error("Failed to fetch centres: the response contains no centres.")
            raise APIError(
                "Failed to fetch centres: the response contains no centres",
                endpoint=Endpoints.CENTRE,
                status_code=response.status_code,
                body=response.text,
            )

        return df

    def print_centres(self, cols: int = 4, col_width: int = 40) -> None:
        """
        Prints the stored list of centres to the console.
        """
        lines = []
        for i, name in enumerate(self.centre_list):
            # Use ljust or rjust to format columns
            name_column = name[:col_width].ljust(col_width)
            # Insert a newline after every 'cols' items
            if (i + 1) % cols == 0:
                lines.append(name_column + "\n")
            else:
                lines.append(name_column)

        final_str = "".join(lines)
        logger.info(f"Available centres:\n{final_str}")

    @property
    def df_centres(self) -> DataFrame | None:
        """
        Returns the stored DataFrame of centres (or None if fetch_centres hasn't been called).
        """
        return self._df_centres
