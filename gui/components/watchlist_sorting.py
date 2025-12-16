from datetime import date, datetime
import re


def sort_watchlist_records(rows, today=None):
    """Return rows sorted by status priority and days to next event.

    Priority order is: Active-Trade, Pre-Trade, WL-Active. Rows with missing
    next_event_date are placed last within their status group.
    """
    if today is None:
        today = date.today()

    def _status_priority(s):
        order = {"Active-Trade": 0, "Pre-Trade": 1, "WL-Active": 2}
        return order.get(s, 3)

    def _days_to_event(row):
        next_date = row.get("next_event_date")
        if not next_date:
            return 999999
        try:
            return (next_date - today).days
        except Exception:
            try:
                # Support string dates in ISO format as fallback
                return (datetime.strptime(next_date, "%Y-%m-%d").date() - today).days
            except Exception:
                return 999999

    return sorted(rows, key=lambda r: (_status_priority(r.get("status")), _days_to_event(r)))


# Treeview column sorting helper -------------------------------------------------
# This helper keeps the Treeview column-sorting logic in one place and returns
# early if the tree has no items or the column is unknown.


def sort_treeview_column(tree, col, reverse=False):
    """Sort a ttk.Treeview by the given column.

    Parameters
    - tree: ttk.Treeview instance
    - col: column name as displayed in the tree (e.g. "Event", "BTE")
    - reverse: bool

    The function moves the items in the tree to match the sorted order and
    re-registers the heading's command to toggle sorting.
    """
    items = tree.get_children("")
    if not items:
        return

    l = [(tree.set(k, col), k) for k in items]

    if col == "Event":

        def event_key(item):
            val = item[0]
            if val == "-":
                return 999999
            try:
                return int(val.replace("d", ""))
            except ValueError:
                return 999999

        l.sort(key=event_key, reverse=reverse)
    elif col == "Name":
        l.sort(key=lambda t: str(t[0]).lower(), reverse=reverse)
    elif col == "RR":

        def rr_key(item):
            val = item[0]
            if val is None or val == "" or str(val).strip() == "-":
                return float("inf")
            try:
                return float(str(val))
            except Exception:
                return float("inf")

        l.sort(key=rr_key, reverse=reverse)
    elif col == "BTE":

        def bte_key(item):
            val = item[0]
            if val is None or val == "" or str(val).strip() == "-":
                return float("-inf") if reverse else float("inf")
            try:
                s = str(val).strip().replace('%', '')
                return float(s)
            except Exception:
                return float("-inf") if reverse else float("inf")

        l.sort(key=bte_key, reverse=reverse)
    elif col == "Upside":

        def upside_key(item):
            val = item[0]
            if val is None or val == "" or str(val).strip() == "-":
                return float("inf")
            try:
                s = str(val).strip().replace('%', '')
                return float(s)
            except Exception:
                return float("inf")

        l.sort(key=upside_key, reverse=reverse)
    elif col == "Proximity":
        # Proximity displayed as '(0.5%) Entry' — extract leading percent for numeric sort
        l.sort(key=proximity_key, reverse=reverse)
    elif col == "PEG":
        # PEG ratio (numeric). Treat missing values as +inf to push them to end.
        def peg_key(item):
            val = item[0]
            if val is None or val == "" or str(val).strip() == "-":
                return float("-inf") if reverse else float("inf")
            try:
                return float(str(val))
            except Exception:
                return float("inf")

        l.sort(key=peg_key, reverse=reverse)
    else:
        l.sort(reverse=reverse)

    for index, (val, k) in enumerate(l):
        tree.move(k, "", index)

    # Replace heading with the appropriate toggling command
    try:
        tree.heading(col, command=lambda: sort_treeview_column(tree, col, not reverse))
    except Exception:
        # If the heading can't be set (rare cases if col doesn't exist), ignore
        pass


# Module-level helper exposed for unit tests
def proximity_key(item):
    val = item[0]
    if val is None:
        return float("inf")
    s = str(val).strip()
    if s == "" or s == "-" or s.lower() == "no data":
        return float("inf")
    m = re.search(r"\(?\s*([0-9]+(?:\.[0-9]+)?)\s*%", s)
    if m:
        try:
            return float(m.group(1))
        except Exception:
            return float("inf")
    return float("inf")
