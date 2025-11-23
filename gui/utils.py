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

def get_proximity_status(price, entry, stop, target):
    """
    Returns (Text, ColorBootstyle) based on price position.
    Prioritizes Risk (Stop) over Reward (Target).
    """
    if not price: return "No Data", "secondary"
    
    # Convert Decimals to floats for comparison if needed
    p = float(price)
    s = float(stop) if stop else 0
    e = float(entry) if entry else 0
    t = float(target) if target else 0

    # 1. Critical Risk
    if s > 0 and p <= s * 1.02: # Within 2% of Stop or below
        diff = ((p - s) / s) * 100
        return f"Hitting Stop ({diff:.1f}%)", "danger"

    # 2. Action Zone (Entry)
    if e > 0 and p >= e and p <= e * 1.05:
        diff = ((p - e) / e) * 100
        return f"Near Entry (+{diff:.1f}%)", "success"
        
    # 3. Target Zone
    if t > 0 and p >= t * 0.95:
        diff = ((t - p) / p) * 100
        return f"Near Target ({diff:.1f}%)", "info"

    # 4. Default
    if e > 0:
        dist = ((e - p) / p) * 100
        return f"Entry in {dist:.1f}%", "secondary"
        
    return "Watching", "secondary"