import os
import sys
import asyncio

# Ensure 'gui' is on sys.path so tests import the project package layout reliably
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from gui.core.utils.technical_utils import update_analysis_db


def test_update_analysis_db_upserts_strategy_on_update(monkeypatch):
    calls = []

    async def fake_execute(query, *args):
        calls.append((query.strip(), args))
        # Simulate an UPDATE that affected 1 row
        return "UPDATE 1"

    monkeypatch.setattr("core.utils.technical_utils.DBEngine.execute", fake_execute)

    # Run the async function
    asyncio.run(update_analysis_db("TICK", 100, 90, 200, True, "my strategy"))

    # Expect at least the UPDATE then the stock_analysis upsert
    assert len(calls) >= 2
    assert calls[0][0].upper().startswith("UPDATE WATCHLIST")
    # Ensure that one of the calls performs the stock_analysis upsert
    assert any("ON CONFLICT" in q[0] for q in calls)


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
    assert len(calls) >= 3
    assert calls[0][0].upper().startswith("UPDATE WATCHLIST")
    # The INSERT can happen in one of the early calls
    assert any(c[0].upper().startswith("INSERT INTO WATCHLIST") for c in calls)
    assert any("ON CONFLICT" in q[0] for q in calls)


def test_update_analysis_db_inserts_support_and_res(monkeypatch):
    calls = []

    async def fake_execute(query, *args):
        calls.append((query.strip(), args))
        # Simulate UPDATE vs INSERT by inspecting the SQL command
        q = query.strip().upper()
        if q.startswith("INSERT INTO PUBLIC.STOCK_PRICE_LEVELS"):
            return "INSERT 1"
        return "UPDATE 1"

    monkeypatch.setattr("core.utils.technical_utils.DBEngine.execute", fake_execute)

    asyncio.run(update_analysis_db("TICK3", 100, 90, 200, True, "strat", support_cs=[123], resistance_cs=[456]))

    # Ensure we inserted support & resistance separately
    insert_count = sum(1 for c in calls if c[0].upper().startswith("INSERT INTO PUBLIC.STOCK_PRICE_LEVELS"))
    assert insert_count >= 2
    # Ensure args include 'support' and 'resistance' level_type strings
    assert any('support' in c[1] for c in calls)
    assert any('resistance' in c[1] for c in calls)


def test_support_resistance_appends(monkeypatch):
    calls = []

    async def fake_execute(query, *args):
        calls.append((query.strip(), args))
        q = query.strip().upper()
        if q.startswith("INSERT INTO PUBLIC.STOCK_PRICE_LEVELS"):
            return "INSERT 1"
        return "UPDATE 1"

    monkeypatch.setattr("core.utils.technical_utils.DBEngine.execute", fake_execute)

    asyncio.run(update_analysis_db("TICK4", 100, 90, 200, True, "strat", support_cs=[100]))
    asyncio.run(update_analysis_db("TICK4", 100, 90, 200, True, "strat", support_cs=[150]))

    insert_calls = [c for c in calls if c[0].upper().startswith("INSERT INTO PUBLIC.STOCK_PRICE_LEVELS")]
    assert len(insert_calls) >= 2
