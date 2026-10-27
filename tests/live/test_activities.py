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


def test_activities_list_endpoint_works(bot):
    """The activities list answers, so fetch() does not silently fall back to the slow calendar."""
    assert bot._activities_manager._list(), "The activities list has no bookable activities."
