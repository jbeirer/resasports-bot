# centres.py

import json
import logging

import pandas as pd
import requests
from pandas import DataFrame

from pysportbot.utils.logger import get_logger

from .endpoints import Endpoints
from .utils.errors import ErrorMessages

logger = get_logger(__name__)


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
        """
        if centre not in self.centre_list:
            logger.error(ErrorMessages.centre_not_found(centre))
            self.print_centres()
            raise ValueError(ErrorMessages.centre_not_found(centre))

    def fetch_centres(self) -> DataFrame:
        """
        Fetches the info of available centres from Resasports and returns a DataFrame.
        """
        try:
            response = requests.post(
                Endpoints.CENTRE,
                json=self.bounds,
                timeout=10,
            )
            response.raise_for_status()

            # Parse the JSON content
            response_json = json.loads(response.content.decode("utf-8"))
            # Flatten and extract the desired columns
            df = pd.json_normalize(response_json["applications"])
            df = df[["slug", "name", "address.town", "address.country", "address.street_line"]]
            df.columns = ["slug", "name", "town", "country", "address"]

            if df is None or df.empty:
                logging.error("Failed to fetch centres.")
                self._raise_fetch_error()  # Fix for TRY301: abstract raise
            else:
                return df

        except Exception:
            logging.exception("Failed to fetch centres")
            return pd.DataFrame()

    def _raise_fetch_error(self) -> None:
        """
        Helper function to raise a ValueError for failed centre fetches.
        """
        raise ValueError("Failed to fetch centres.")

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
