def get_proximity_status(price, entry, stop, target, is_long: bool = True, proximity: float = 0.02):
    """Return (text, bootstyle) describing proximity to stop/entry/target.

    - is_long determines the direction of comparisons (long vs short positions)
    - proximity is the percentage (as fraction) used to determine "near" thresholds
      (defaults to 2% as requested).

    Logic summary (long=True):
      * Critical Risk (danger) when price is <= stop * (1 + proximity)
      * Action Zone (success) when price is between entry and entry*(1+proximity)
      * Target Zone (info) when price >= target*(1 - proximity)

    Logic summary (long=False / short):
      * Critical Risk (danger) when price >= stop * (1 - proximity)
      * Action Zone (success) when price is between entry*(1 - proximity) and entry
        (i.e., price has moved down into the entry zone)
      * Target Zone (info) when price <= target*(1 + proximity)
    """
    if price is None:
        return "No Data", "secondary"

    try:
        p = float(price)
    except Exception:
        return "No Data", "secondary"

    def to_float(v):
        try:
            return float(v) if v is not None else None
        except Exception:
            return None

    s = to_float(stop)
    e = to_float(entry)
    t = to_float(target)

    # --- Critical Risk (stop) ---
    if s is not None and s != 0:
        if is_long:
            # For long positions, price falling near/at stop is dangerous
            if p <= s * (1 + proximity):
                diff = ((p - s) / s) * 100
                # Format as '(x%) Stop' so numeric sorting is easier
                return f"({abs(diff):.1f}%) Stop", "danger"
        else:
            # For short positions, price rising near/at stop is dangerous
            if p >= s * (1 - proximity):
                diff = ((s - p) / s) * 100
                return f"({abs(diff):.1f}%) Stop", "danger"

    # --- Action Zone (entry) ---
    if e is not None and e != 0:
        if is_long:
            if p >= e and p <= e * (1 + proximity):
                diff = ((p - e) / e) * 100
                return f"({abs(diff):.1f}%) Entry", "success"
        else:
            # For short, entry zone is when price has moved down into the entry level
            # Use strict bounds so the exact boundary value (== e*(1-proximity)) is
            # treated as the default 'Entry in' message rather than the action zone.
            if p < e and p > e * (1 - proximity):
                diff = ((e - p) / e) * 100
                return f"({abs(diff):.1f}%) Entry", "success"

    # --- Target Zone ---
    # Only label 'Near Target' when price is within 'proximity' fraction of the target
    pct_to_target = None # Initialize to None
    if t is not None and t != 0:
        try:
            pct_to_target = abs(p - t) / t
        except Exception:
            pct_to_target = None
    if pct_to_target is not None and pct_to_target <= proximity:
        # Report diff relative to target so the percent is intuitive (how far from target)
        diff = ((t - p) / t) * 100 if t != 0 else 0
        return f"({abs(diff):.1f}%) Target", "info"

    # --- Default / distance to entry ---
    if e is not None and e != 0:
        try:
            # Compute distance to entry relative to the entry price itself so the
            # percentage reported is intuitive. We always return a numeric proximity
            # value so the column is sortable, but the styling remains 'secondary'
            if is_long:
                pct = abs(e - p) / e
                dist = ((e - p) / e) * 100
            else:
                pct = abs(p - e) / e
                dist = ((p - e) / e) * 100

            # Always show proximity to entry (numeric) to allow sorting.
            return f"({abs(dist):.1f}%) Entry", "secondary"
        except Exception:
            # Prefer an empty status message instead of 'Watching'
            return "", "secondary"

    # Prefer an empty status when nothing matches
    return "", "secondary"
