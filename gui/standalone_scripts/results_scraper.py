"""Standalone entrypoint for the Results Summaries Playwright scraper.

Run:
  python "standalone_scripts/results_scraper.py" [--ticker TICKER] [--list-only] [--limit N] [--debug-values]

Implementation lives in `standalone_scripts/results_scraper/`.
"""

from __future__ import annotations

import sys
from pathlib import Path


# When executed as a file ("python standalone_scripts/results_scraper.py"),
# `sys.path[0]` is `gui/standalone_scripts`, which is *not* enough to import the
# `standalone_scripts.*` package. Add the GUI root (`gui/`) to sys.path.
_GUI_ROOT = Path(__file__).resolve().parent.parent
if str(_GUI_ROOT) not in sys.path:
  sys.path.insert(0, str(_GUI_ROOT))


from standalone_scripts.results_scraper.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
