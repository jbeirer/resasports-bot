from datetime import datetime, timedelta

from pysportbot.utils.errors import ErrorMessages


def test_book_and_cancel_activity(bot):
    """Test booking and canceling the first available activity slot within the week, starting from the next day."""

    # Fetch activities
    activities = bot.activities()
    assert not activities.empty, "No activities available for booking."

    # Define the search range (next day to one week later)
    start_date = datetime.now() + timedelta(days=1)
    end_date = start_date + timedelta(days=6)

    # Helper function to find the first bookable slot
    def find_bookable_slot():
        for activity_name in activities["name_activity"]:
            current_date = start_date
            while current_date <= end_date:
                slots = bot.daily_slots(activity_name, current_date.strftime("%Y-%m-%d"))
                if not slots.empty:
                    for _, slot in slots.iterrows():
                        try:
                            bot.book(activity_name, slot["start_timestamp"])
                            return {"activity_name": activity_name, "start_time": slot["start_timestamp"]}
                        except ValueError as e:
                            if str(e) in [
                                ErrorMessages.slot_already_booked(),
                                ErrorMessages.slot_unavailable(),
                            ]:
                                continue
                            raise
                current_date += timedelta(days=1)
        return None

    # Find and book the first available slot
    bookable_slot = find_bookable_slot()
    assert bookable_slot is not None, "No bookable slots found for any activity within the next week."

    # Cancel the booking
    bot.cancel(bookable_slot["activity_name"], bookable_slot["start_time"])
    assert (
        True
    ), f"Failed to cancel activity slot for {bookable_slot['activity_name']} at {bookable_slot['start_time']}."
