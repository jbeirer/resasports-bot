from datetime import datetime, time

import pytz


def get_unix_day_bounds(date_string: str, fmt: str = "%Y-%m-%d", tz: str = "UTC") -> tuple[int, int]:
    """
    Get the Unix timestamp bounds for a given day.

    Args:
        date_string (str): The date in 'YYYY-MM-DD' format.
        fmt (str): The format of the input date string.
        tz (str): The timezone name.

    Returns:
        tuple[int, int]: The start and end Unix timestamps for the day.
    """
    tzinfo = pytz.timezone(tz)
    date = datetime.strptime(date_string, fmt).replace(tzinfo=tzinfo)
    return (
        int(datetime.combine(date.date(), time.min, tzinfo=tzinfo).timestamp()),
        int(datetime.combine(date.date(), time.max, tzinfo=tzinfo).timestamp()),
    )


def format_unix_to_date(unix_timestamp: int, fmt: str = "%Y-%m-%d %H:%M:%S", tz: str = "UTC") -> str:
    """
    Convert a Unix timestamp to a formatted date string.

    Args:
        unix_timestamp (int): The Unix timestamp to convert.
        fmt (str): The desired output format.
        tz (str): The timezone name.

    Returns:
        str: The formatted date string.
    """
    tzinfo = pytz.timezone(tz)
    return datetime.fromtimestamp(unix_timestamp, tz=tzinfo).strftime(fmt)
