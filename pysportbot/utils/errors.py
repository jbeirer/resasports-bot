import logging


class ErrorMessages:
    """Centralized error messages for the application."""

    @staticmethod
    def no_centre_selected() -> str:
        """Return an error message for no centre selected."""
        return "No centre selected. Please set a centre first."

    @staticmethod
    def centre_not_found(centre: str) -> str:
        """Return an error message for a centre not found."""
        return f"Centre '{centre}' not found. Please check the list of available centres."

    @staticmethod
    def missing_required_key(key: str) -> str:
        return f"Missing required key in config: {key}"

    @staticmethod
    def invalid_class_definition() -> str:
        return "Each class must include 'activity', 'class_day', " "'class_time', 'booking_execution', and 'weekly'."

    @staticmethod
    def invalid_weekly_now() -> str:
        return "Invalid combination: cannot use weekly=True with booking_execution='now'."

    @staticmethod
    def invalid_booking_execution_format() -> str:
        return "Invalid booking_execution format. Use 'now' or 'Day HH:MM:SS'."

    @staticmethod
    def no_matching_slots_for_time(activity: str, class_time: str, booking_date: str) -> str:
        return f"No matching slots available for {activity} at {class_time} on {booking_date}"

    @staticmethod
    def not_logged_in() -> str:
        """Return an error message for not being logged in."""
        return "You must log in first."

    @staticmethod
    def login_failed() -> str:
        """Return an error message for a failed login."""
        return "Login failed. Please check your credentials and try again."

    @staticmethod
    def invalid_log_level(level: str) -> ValueError:
        """
        Generate a ValueError for an invalid logging level.

        Args:
            level (str): The invalid logging level.

        Returns:
            ValueError: A ValueError with a detailed message.
        """
        valid_levels = ", ".join(logging._nameToLevel.keys())
        return ValueError(f"Invalid logging level: {level}. Valid levels are {valid_levels}.")

    @staticmethod
    def endpoint_not_found(name: str) -> ValueError:
        """
        Generate a ValueError for a missing endpoint.

        Args:
            name (str): The name of the endpoint that was not found.

        Returns:
            ValueError: A ValueError with a detailed message.
        """
        return ValueError(f"Endpoint '{name}' does not exist.")

    @staticmethod
    def no_activities_loaded() -> str:
        """Return an error message for no activities loaded."""
        return "No activities loaded. Please log in first."

    @staticmethod
    def failed_fetch(resource: str) -> str:
        """Return an error message for a failed fetch request."""
        return f"Failed to fetch {resource}. Please try again later."

    @staticmethod
    def activity_not_found(activity_name: str, available_activities: list) -> str:
        """Return an error message for an activity not found."""
        return (
            f"No activity found with the name '{activity_name}'. "
            f"Available activities are: {', '.join(available_activities)}."
        )

    @staticmethod
    def no_slots(activity_name: str, day: str) -> str:
        """Return a warning message when no slots are available."""
        return f"No slots available for activity '{activity_name}' on {day}."

    @staticmethod
    def no_matching_slots(activity_name: str, day: str) -> str:
        """Return a warning message for no matching slots found."""
        return f"No matching slots found for activity '{activity_name}' on {day}."

    @staticmethod
    def slot_not_found(activity_name: str, start_time: str) -> str:
        """Return an error message for a slot not found."""
        return f"No slot found for activity '{activity_name}' at {start_time}."

    @staticmethod
    def slot_not_bookable_yet() -> str:
        """Return an error message for a slot not bookable yet."""
        return "The slot is not bookable yet."

    @staticmethod
    def slot_already_booked() -> str:
        """Return an error message for a slot already booked."""
        return "The slot is already booked."

    @staticmethod
    def slot_unavailable() -> str:
        """Return an error message for a slot that is unavailable."""
        return "The slot is not available."

    @staticmethod
    def cancellation_failed() -> str:
        """Return an error message for a failed cancellation."""
        return "Cancellation failed. The slot may not have been booked."

    @staticmethod
    def failed_login() -> str:
        """Return an error message for a failed login."""
        return "Login failed. Please check your credentials and try again."

    @staticmethod
    def failed_login_nubapp() -> str:
        """Return an error message for a failed login to Nubapp."""
        return "Login to Nubapp failed. Please try again later."

    @staticmethod
    def unknown_error(action: str) -> str:
        """Return an error message for an unknown error."""
        return f"An unknown error occurred during {action}. Please try again later."
