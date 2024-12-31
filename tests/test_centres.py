# test_centres.py

import logging  # Import logging to set log levels
from unittest.mock import patch

import pandas as pd
import pytest

from pysportbot import SportBot


@pytest.mark.parametrize(
    "print_centres, expected_contains",
    [
        (True, ["centre1", "centre2"]),
        (False, []),
    ],
)
def test_print_centres_behavior(print_centres, expected_contains, caplog):
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
        caplog.set_level(logging.INFO)

        # Initialize SportBot with the specified `print_centres` parameter
        SportBot(print_centres=print_centres)

    # Access the captured logs
    logs = caplog.text.lower()

    if print_centres:
        # Assert that each expected centre slug is present in the logs
        for centre_slug in expected_contains:
            assert centre_slug in logs, f"Expected '{centre_slug}' to be logged, but it wasn't."
    else:
        # Assert that none of the centre slugs are present in the logs
        for centre_slug in ["centre1", "centre2"]:
            assert centre_slug not in logs, f"Did not expect '{centre_slug}' to be logged, but it was."


def test_print_centres_outputs_non_empty_list(caplog):
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
        caplog.set_level(logging.INFO)

        # Initialize SportBot with print_centres=True
        SportBot(print_centres=True)

    # Access the captured logs
    logs = caplog.text.lower()

    # Verify that each centre slug is present in the logs
    assert "centre1" in logs, "Expected 'centre1' to be logged, but it wasn't."
    assert "centre2" in logs, "Expected 'centre2' to be logged, but it wasn't."


def test_print_centres_does_not_output_when_disabled(caplog):
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
        caplog.set_level(logging.INFO)

        # Initialize SportBot with print_centres=False
        SportBot(print_centres=False)

    # Access the captured logs
    logs = caplog.text.lower()

    # Verify that centre slugs are not present in the logs
    assert "centre1" not in logs, "Did not expect 'centre1' to be logged, but it was."
    assert "centre2" not in logs, "Did not expect 'centre2' to be logged, but it was."
