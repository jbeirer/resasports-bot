# test_centres.py

import logging  # Import logging to set log levels
from unittest.mock import patch

import pandas as pd
import pytest
import requests
import responses

from pysportbot import SportBot
from pysportbot.centres import Centres
from pysportbot.client import ApiClient
from pysportbot.endpoints import Endpoints
from pysportbot.exceptions import APIError, CentreNotFoundError


@pytest.mark.parametrize(
    "print_centres, expected_contains",
    [
        (True, ["centre1", "centre2"]),
        (False, []),
    ],
)
def test_print_centres_behavior(print_centres, expected_contains, pysportbot_caplog):
    """
    Parametrized test to verify the behavior of the `print_centres` parameter.

    - When `print_centres=True`, ensure that centres are logged.
    - When `print_centres=False`, ensure that centres are not logged.
    """
    # Create a mock DataFrame of centres
    mock_df = pd.DataFrame(
        {
            "slug": ["centre1", "centre2"],
            "name": ["My Centre 1", "My Centre 2"],
            "address.town": ["Town A", "Town B"],
            "address.country": ["Country A", "Country B"],
            "address.street_line": ["Street A", "Street B"],
        }
    )

    # Patch the `fetch_centres` method to return the mock DataFrame
    with patch("pysportbot.centres.Centres.fetch_centres", return_value=mock_df):
        # Set the log level to INFO to capture info logs
        pysportbot_caplog.set_level(logging.INFO)

        # Initialize SportBot with the specified `print_centres` parameter
        SportBot(print_centres=print_centres)

    # Access the captured logs
    logs = pysportbot_caplog.text.lower()

    if print_centres:
        # Assert that each expected centre slug is present in the logs
        for centre_slug in expected_contains:
            assert centre_slug in logs, f"Expected '{centre_slug}' to be logged, but it wasn't."
    else:
        # Assert that none of the centre slugs are present in the logs
        for centre_slug in ["centre1", "centre2"]:
            assert centre_slug not in logs, f"Did not expect '{centre_slug}' to be logged, but it was."


def test_print_centres_outputs_non_empty_list(pysportbot_caplog):
    """
    Test that initializing SportBot with `print_centres=True` logs a non-empty list of centres.
    """
    # Create a mock DataFrame with centres
    mock_df = pd.DataFrame(
        {
            "slug": ["centre1", "centre2"],
            "name": ["My Centre 1", "My Centre 2"],
            "address.town": ["Town A", "Town B"],
            "address.country": ["Country A", "Country B"],
            "address.street_line": ["Street A", "Street B"],
        }
    )

    # Patch the `fetch_centres` method to return the mock DataFrame
    with patch("pysportbot.centres.Centres.fetch_centres", return_value=mock_df):
        # Set the log level to INFO to capture info logs
        pysportbot_caplog.set_level(logging.INFO)

        # Initialize SportBot with print_centres=True
        SportBot(print_centres=True)

    # Access the captured logs
    logs = pysportbot_caplog.text.lower()

    # Verify that each centre slug is present in the logs
    assert "centre1" in logs, "Expected 'centre1' to be logged, but it wasn't."
    assert "centre2" in logs, "Expected 'centre2' to be logged, but it wasn't."


def test_print_centres_does_not_output_when_disabled(pysportbot_caplog):
    """
    Test that initializing SportBot with `print_centres=False` does not log the list of centres.
    """
    # Create a mock DataFrame with centres
    mock_df = pd.DataFrame(
        {
            "slug": ["centre1", "centre2"],
            "name": ["My Centre 1", "My Centre 2"],
            "address.town": ["Town A", "Town B"],
            "address.country": ["Country A", "Country B"],
            "address.street_line": ["Street A", "Street B"],
        }
    )

    # Patch the `fetch_centres` method to return the mock DataFrame
    with patch("pysportbot.centres.Centres.fetch_centres", return_value=mock_df):
        # Set the log level to INFO to capture info logs
        pysportbot_caplog.set_level(logging.INFO)

        # Initialize SportBot with print_centres=False
        SportBot(print_centres=False)

    # Access the captured logs
    logs = pysportbot_caplog.text.lower()

    # Verify that centre slugs are not present in the logs
    assert "centre1" not in logs, "Did not expect 'centre1' to be logged, but it was."
    assert "centre2" not in logs, "Did not expect 'centre2' to be logged, but it was."


def test_check_centre_unknown_raises(mocked_api):
    """`check_centre` rejects a slug that is not in the fetched centre list."""
    centres = Centres(ApiClient())

    with pytest.raises(CentreNotFoundError) as exc_info:
        centres.check_centre("unknown")

    assert exc_info.value.centre == "unknown"


def test_check_centre_valid_slug_passes(mocked_api, centre_slug):
    """`check_centre` accepts a slug returned by the centres endpoint."""
    centres = Centres(ApiClient())

    centres.check_centre(centre_slug)


# Content errors found after a 2xx response carry no status code
@pytest.mark.parametrize(
    ("response_kwargs", "status_code"),
    [
        pytest.param({"status": 500}, 500, id="non-200"),
        pytest.param({"body": "not json"}, 200, id="invalid-json"),
        pytest.param({"json": {}}, None, id="missing-applications"),
        pytest.param({"json": {"applications": []}}, None, id="empty"),
        pytest.param({"json": {"applications": [{"slug": "no-address"}]}}, None, id="missing-columns"),
        pytest.param({"body": requests.ConnectionError("connection refused")}, None, id="connection-error"),
    ],
)
def test_fetch_centres_failure_raises_api_error(mocked_api, response_kwargs, status_code):
    """A failed centre fetch raises a clear APIError instead of `KeyError: 'slug'`."""
    mocked_api.replace(responses.POST, str(Endpoints.CENTRE), **response_kwargs)

    with pytest.raises(APIError) as exc_info:
        SportBot()

    assert exc_info.value.endpoint == str(Endpoints.CENTRE)
    assert exc_info.value.status_code == status_code
