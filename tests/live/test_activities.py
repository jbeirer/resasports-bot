def test_fetch_activities(bot):
    """Test fetching activities."""
    activities = bot.activities(limit=5)
    assert not activities.empty, "No activities fetched. Check server or credentials."


def test_activities_columns(bot):
    """Test that activities contain expected columns."""
    activities = bot.activities(limit=1)
    expected_columns = ["name_activity", "id_activity"]
    for column in expected_columns:
        assert column in activities.columns, f"Missing column: {column}"
