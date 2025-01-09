from datetime import datetime, timedelta

from pysportbot.utils.errors import ErrorMessages


def test_book_and_cancel_activity(bot):
    """Test booking and canceling a Gimnasio session on the upcoming Friday."""

    # Determine the upcoming Friday from today
    today = datetime.now()
    # Calculate the days until next Friday (if today is Friday, book for next week)
    days_until_friday = (4 - today.weekday()) % 7
    # Ensure that if it's already Friday, we move to the next Friday (7 days later)
    if days_until_friday == 0:
        days_until_friday = 7
    upcoming_friday = today + timedelta(days=days_until_friday)
    friday_str = upcoming_friday.strftime("%Y-%m-%d")

    # Fetch available slots for 'Gimnasio' on upcoming Friday
    slots = bot.daily_slots("Gimnasio", friday_str)
    assert not slots.empty, f"No Gimnasio slots available for {friday_str}"

    # Book the first available slot
    booked_slot = None
    for _, slot in slots.iterrows():
        try:
            bot.book("Gimnasio", slot["start_timestamp"])
            booked_slot = slot["start_timestamp"]
            break
        except ValueError as e:
            # If the slot is already booked, unavailable, or not yet open, move on
            if str(e) in [
                ErrorMessages.slot_already_booked(),
                ErrorMessages.slot_unavailable(),
                ErrorMessages.slot_not_bookable_yet(),
            ]:
                continue
            raise

    assert booked_slot is not None, f"No bookable Gimnasio slots found on {friday_str}"

    # Cancel the booking
    bot.cancel("Gimnasio", booked_slot)
    # Simple success assertion—if cancel fails, an exception should be raised
    assert True, f"Failed to cancel Gimnasio slot at {booked_slot}"
