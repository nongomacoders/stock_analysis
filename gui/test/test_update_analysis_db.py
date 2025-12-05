import os
import sys
import asyncio

# Ensure 'gui' is on sys.path so tests import the project package layout reliably
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.utils.technical_utils import update_analysis_db


def test_update_analysis_db_upserts_strategy_on_update(monkeypatch):
    calls = []

    async def fake_execute(query, *args):
        calls.append((query.strip(), args))
        # Simulate an UPDATE that affected 1 row
        return "UPDATE 1"

    monkeypatch.setattr("core.utils.technical_utils.DBEngine.execute", fake_execute)

    # Run the async function
    asyncio.run(update_analysis_db("TICK", 100, 90, 200, True, "my strategy"))

    # Expect the UPDATE then the stock_analysis upsert
    assert len(calls) == 2
    assert calls[0][0].upper().startswith("UPDATE WATCHLIST")
    assert "ON CONFLICT" in calls[1][0]


def test_update_analysis_db_inserts_and_upserts_strategy_when_no_update(monkeypatch):
    calls = []

    # We'll return different results for sequential calls
    results = ["UPDATE 0", "INSERT 1", "INSERT 1"]

    async def fake_execute(query, *args):
        calls.append((query.strip(), args))
        return results.pop(0)

    monkeypatch.setattr("core.utils.technical_utils.DBEngine.execute", fake_execute)

    asyncio.run(update_analysis_db("TICK2", 200, 190, 300, False, "another strategy"))

    # Expect UPDATE, INSERT into watchlist, then upsert into stock_analysis
    assert len(calls) == 3
    assert calls[0][0].upper().startswith("UPDATE WATCHLIST")
    assert calls[1][0].upper().startswith("INSERT INTO WATCHLIST")
    assert "ON CONFLICT" in calls[2][0]
