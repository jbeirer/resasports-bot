import os

from pysportbot.utils.logger import get_logger

logger = get_logger(__name__)


def get_n_threads(max_user_threads: int, requested_bookings: int) -> int:
    """
    Determine the number of threads to use based on user input and system resources.

    Args:
        max_user_threads (int): Maximum number of threads requested by the user (-1 for auto-detect).
        requested_bookings (int): Number of bookings to process.

    Returns:
        int: The maximum number of threads to use.

    Raises:
        ValueError: If max_user_threads is 0.
    """
    logger.debug(f"Maximum number of user-requested threads: {max_user_threads}")
    logger.debug(f"Requested bookings: {requested_bookings}")

    available_threads: int = os.cpu_count() or 1  # Fallback to 1 if os.cpu_count() is None
    logger.debug(f"Available threads: {available_threads}")

    if max_user_threads == 0:
        logger.error("The 'max_user_threads' argument cannot be 0.")
        raise ValueError("The 'max_user_threads' argument cannot be 0.")

    if max_user_threads > available_threads:
        logger.warning(
            f"User-requested threads ({max_user_threads}) exceed available threads ({available_threads}). "
            f"Limiting to {available_threads} threads."
        )

    if requested_bookings <= 0:
        logger.warning("No bookings requested. Returning 0 threads.")
        return 0  # No threads needed if there are no bookings

    # If max_user_threads is -1, use the lesser of available threads and requested bookings
    if max_user_threads == -1:
        max_threads: int = min(available_threads, requested_bookings)
    else:
        # Use the lesser of max_user_threads, available threads, and requested bookings
        max_threads = min(max_user_threads, available_threads, requested_bookings)

    logger.info(f"Using up to {max_threads} threads for booking {requested_bookings} activities.")

    return max_threads
