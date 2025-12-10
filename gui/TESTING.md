# Testing Guidelines — GUI Project

This file explains how to run the unit tests, add new tests, and contains recommendations to keep tests stable across environments.

## Running tests

Run tests under the `gui/test` folder using Python's unittest from the project root (recommended):

```bash
# From repository root (GITHUBPROJECTS):
python -m unittest discover gui/test -v

# Or run a single test file
python -m unittest -v gui.test.test_imports
```

Notes:
- Do not execute `python gui/test/test_foo.py` directly; prefer `python -m unittest` - the package imports rely on proper package paths.
- Tests use `gui` as the package root; imports should be `from gui.core...` / `from gui.components...` / `from gui.modules...`.

## New test guidelines

1. Place tests in `gui/test/` and name files `test_*.py`.
2. Use `gui.*` qualified imports (e.g., `from gui.core.utils.technical_utils import price_from_db`).
3. Where GUI APIs are required (tkinter, ttkbootstrap), mock them or skip in CI with an environment variable.
4. Use `monkeypatch` or `unittest.mock` to isolate network, DB, or file IO.
5. Avoid using live DBs in unit tests; use mock or ephemeral DB instances for integration tests.

## Conventions & helpers

- Tests should be deterministic, isolated, and fast.
- Keep tests small with single responsibilities.

### Example test pattern

```python
from gui.core.utils.technical_utils import price_from_db


def test_price_from_db_decimal():
    assert price_from_db(Decimal('100')) == 1.0
```

## Running tests locally (PowerShell)

```powershell
cd path\to\project\stock_analysis
python -m unittest discover gui/test -v
```

## Running tests locally (bash)

```bash
cd path/to/project/stock_analysis
python -m unittest discover gui/test -v
```

## Adding tests for DB migrations

- For migration tests, add assertions which check that the migration SQL file contains the relevant statements (these are static tests to validate the migration script content).
- For integration/smoke testing, consider creating a temporary PostgreSQL database and running the migration in a test container (not covered here).

## CI

We add a GitHub Actions workflow to run tests automatically, see `.github/workflows/python-tests.yml`.

## Troubleshooting

If tests fail due to imports:
- Make sure you run from the repository root.
- Ensure `gui/test/__init__.py` exists and `gui/` is visible as a package root.  

If you want, I can add `pytest` and a `pytest.ini` for more advanced config.
