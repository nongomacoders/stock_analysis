"""Standalone entrypoint for the Results Summaries Playwright scraper.

Run:
  python "scripts_standalone/results_scraper.py" [--ticker TICKER] [--list-only] [--limit N] [--debug-values]

Implementation lives in `scripts_standalone/results_scraper/`.
"""

from __future__ import annotations

import sys
from pathlib import Path


# When executed as a file ("python scripts_standalone/results_scraper.py"),
# `sys.path[0]` is `gui/scripts_standalone`, which is *not* enough to import the
# `scripts_standalone.*` package. Add the GUI root (`gui/`) to sys.path.
_GUI_ROOT = Path(__file__).resolve().parent.parent
if str(_GUI_ROOT) not in sys.path:
  sys.path.insert(0, str(_GUI_ROOT))


from scripts_standalone.results_scraper.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
