# Template test - use this as a starting point for new tests

import os
import sys
# Make sure gui package is importable from tests run from repo root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from gui.core.utils.technical_utils import price_from_db


def test_price_from_db_int():
    assert price_from_db(12345) == 123.45


# Demonstrate using monkeypatch for DB / async functions
def test_with_monkeypatch(monkeypatch):
    # Example of mocking a DB call or async function
    calls = []

    async def fake_execute(query, *args):
        calls.append((query, args))
        return 'OK'

    # If your code references DBEngine.execute, monkeypatch accordingly
    monkeypatch.setattr('gui.core.utils.technical_utils.DBEngine.execute', fake_execute)

    # Now run your function that calls DBEngine.execute and assert
    # e.g., result = asyncio.run(my_async_func())
    # assert result == 'OK'
    assert True
