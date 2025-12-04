from datetime import date, timedelta

from components.watchlist import sort_watchlist_records


def test_sort_watchlist_records_status_and_days():
    today = date(2025, 12, 1)

    rows = [
        {"ticker": "A", "status": "Pre-Trade", "next_event_date": today + timedelta(days=2)},
        {"ticker": "B", "status": "Active-Trade", "next_event_date": today + timedelta(days=5)},
        {"ticker": "C", "status": "Active-Trade", "next_event_date": today + timedelta(days=1)},
        {"ticker": "D", "status": "WL-Active", "next_event_date": None},
        {"ticker": "E", "status": "Pre-Trade", "next_event_date": today + timedelta(days=10)},
        {"ticker": "F", "status": "WL-Active", "next_event_date": today + timedelta(days=3)},
    ]

    sorted_rows = sort_watchlist_records(rows, today=today)

    # After sorting we expect all Active-Trade first (C before B), then Pre-Trade (A before E), then WL-Active (F then D)
    expected_tick_order = ["C", "B", "A", "E", "F", "D"]
    assert [r["ticker"] for r in sorted_rows] == expected_tick_order


if __name__ == "__main__":
    # Allow ad-hoc execution: run the test and report
    try:
        test_sort_watchlist_records_status_and_days()
        print("OK: test_sort_watchlist_records_status_and_days passed")
    except AssertionError as e:
        print("FAIL: test_sort_watchlist_records_status_and_days failed")
        raise
