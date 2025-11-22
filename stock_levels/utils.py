# In utils.py
from datetime import date, timedelta

def calculate_next_event_hit(event_date: date, today: date, max_days_away: int):
    """
    Checks if a perennial event date falls within the next N days.
    Returns the number of days away, or None if it's not a hit.
    """
    if event_date is None:
        return None, None

    try:
        event_this_year = event_date.replace(year=today.year)
    except ValueError: # Handle Feb 29
        if event_date.month == 2 and event_date.day == 29:
            event_this_year = event_date.replace(year=today.year, day=28)
        else:
            return None, None # Invalid date

    event_next_year = event_this_year.replace(year=today.year + 1)
    
    check_date_limit = today + timedelta(days=max_days_away)

    hit_date = None
    if today <= event_this_year <= check_date_limit:
        hit_date = event_this_year
    elif today <= event_next_year <= check_date_limit:
        hit_date = event_next_year
    
    if hit_date:
        days_away = (hit_date - today).days
        return days_away, hit_date
        
    return None, None

# In utils.py

# ... (Existing calculate_next_event_hit function) ...

def calculate_rr_ratio(entry, target, stop):
    """
    Calculates the Reward/Risk ratio based on prices.
    Returns a tuple: (ratio_float, type_string)
    """
    if not (entry > 0 and target > 0 and stop > 0):
        return None, "--"
    
    if target > entry: # Long Trade
        reward = target - entry
        risk = entry - stop
        if risk <= 0:
            return None, "Invalid Long (Stop >= Entry)"
        ratio = reward / risk
        return ratio, "Long"

    elif target < entry: # Short Trade
        reward = entry - target
        risk = stop - entry
        if risk <= 0:
            return None, "Invalid Short (Stop <= Entry)"
        ratio = reward / risk
        return ratio, "Short"
    
    return None, "Tgt = Entry"


def get_year_from_period(period_str):
    """
    Safely extracts the year (as an int) from a period string
    like "H1 2024" or "2024 H1".
    """
    if not period_str:
        return None
    parts = period_str.split(" ")
    if len(parts) < 2:
        return None
        
    try:
        return int(parts[0])
    except ValueError:
        try:
            return int(parts[1])
        except ValueError:
            return None