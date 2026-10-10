from pysportbot import Activity


def test_fetch_activities(bot):
    """Test fetching activities."""
    activities = bot.activities()[:5]
    assert activities, "No activities fetched. Check server or credentials."


def test_activities_are_models(bot):
    """Test that activities are parsed into Activity models."""
    for activity in bot.activities():
        assert isinstance(activity, Activity)
        assert activity.name, f"Activity {activity.id} has no name"
