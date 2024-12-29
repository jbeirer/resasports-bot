def test_time_bounds():
    """Test the time bounds utility."""
    from pysportbot.utils.time import get_unix_day_bounds

    date = "2024-12-30"
    start, end = get_unix_day_bounds(date)
    assert start < end, "Start time is not less than end time."
    assert isinstance(start, int) and isinstance(end, int), "Timestamps are not integers."
