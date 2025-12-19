"""
Standalone entrypoint for all commodity scrapers.

Run:
  python "standalone_scripts/commodity_scraper.py" [--commodity gold|iron_ore|coal|all]
"""

from __future__ import annotations

import sys
from pathlib import Path


# Add GUI root (`gui/`) to sys.path so DBEngine imports work
_GUI_ROOT = Path(__file__).resolve().parent.parent
if str(_GUI_ROOT) not in sys.path:
    sys.path.insert(0, str(_GUI_ROOT))


from scripts_standalone.commodity_fx_scraper.runner import main


if __name__ == "__main__":
    raise SystemExit(main())
