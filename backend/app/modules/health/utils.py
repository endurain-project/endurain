"""Utility functions for health-related operations."""

from datetime import date, timedelta


def get_start_date_for_interval(interval: str) -> date:
    """
    Calculate the start date based on the specified time interval.

    Args:
        interval (str): The time interval for which to calculate the start date.
            Supported values:
            - "last_30_days": Returns date from 30 days ago
            - "last_90_days": Returns date from 90 days ago
            - "last_year": Returns date from 365 days ago
            - "all_time": Returns the minimum date (earliest possible date)
            - Any other value defaults to 7 days ago

    Returns:
        date: The calculated start date for the given interval.
    """
    today = date.today()

    if interval == "last_30_days":
        return today - timedelta(days=30)
    elif interval == "last_90_days":
        return today - timedelta(days=90)
    elif interval == "last_year":
        return today - timedelta(days=365)
    elif interval == "all_time":
        return date.min
    else:
        return today - timedelta(days=7)
