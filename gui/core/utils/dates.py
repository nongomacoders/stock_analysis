from datetime import date


def calculate_days_to_event(event_dates):
    """
    Returns the minimum days to the next event from a list of date objects.
    Returns 999 if no future events found.
    """
    today = date.today()
    min_days = 999

    for d in event_dates:
        if d and d >= today:
            days = (d - today).days
            if days < min_days:
                min_days = days
    return min_days
