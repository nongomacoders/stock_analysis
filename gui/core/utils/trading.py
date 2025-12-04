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
                return f"Hitting Stop ({diff:.1f}%)", "danger"
        else:
            # For short positions, price rising near/at stop is dangerous
            if p >= s * (1 - proximity):
                diff = ((s - p) / s) * 100
                return f"Hitting Stop ({abs(diff):.1f}%)", "danger"

    # --- Action Zone (entry) ---
    if e is not None and e != 0:
        if is_long:
            if p >= e and p <= e * (1 + proximity):
                diff = ((p - e) / e) * 100
                return f"Near Entry (+{diff:.1f}%)", "success"
        else:
            # For short, entry zone is when price has moved down into the entry level
            if p <= e and p >= e * (1 - proximity):
                diff = ((e - p) / e) * 100
                return f"Near Entry (-{diff:.1f}%)", "success"

    # --- Target Zone ---
    # Only label 'Near Target' when price is within 'proximity' fraction of the target
    if t is not None and t != 0:
        try:
            pct_to_target = abs(p - t) / t
        except Exception:
            pct_to_target = None

        if pct_to_target is not None and pct_to_target <= proximity:
            # Report diff relative to target so the percent is intuitive (how far from target)
            diff = ((t - p) / t) * 100 if t != 0 else 0
            return f"Near Target ({diff:.1f}%)", "info"

    # --- Default / distance to entry ---
    if e is not None and e != 0:
        try:
            # Compute distance to entry relative to the entry price itself so the
            # percentage reported is intuitive. Only display the message when the
            # absolute percentage distance to entry is within the 'proximity' window.
            if is_long:
                pct = abs(e - p) / e
                dist = ((e - p) / e) * 100
            else:
                pct = abs(p - e) / e
                dist = ((p - e) / e) * 100

            if pct <= proximity:
                return f"Entry in {abs(dist):.1f}%", "secondary"
            # Outside proximity window -> return blank to keep UI clean
            return "", "secondary"
        except Exception:
            # Prefer an empty status message instead of 'Watching'
            return "", "secondary"

    # Prefer an empty status when nothing matches
    return "", "secondary"
