"""Standalone entrypoint for the News Playwright scraper.

Run:
  python "standalone_scripts/news_scraper.py" [--ticker TICKER] [--list-only] [--limit N]

Implementation lives in `standalone_scripts/news_scraper/`.
"""

from __future__ import annotations

import sys
from pathlib import Path


# When executed as a file ("python standalone_scripts/news_scraper.py"),
# add the GUI root (`gui/`) to sys.path so `standalone_scripts.*` imports work.
_GUI_ROOT = Path(__file__).resolve().parent.parent
if str(_GUI_ROOT) not in sys.path:
    sys.path.insert(0, str(_GUI_ROOT))


from standalone_scripts.news_scraper.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
