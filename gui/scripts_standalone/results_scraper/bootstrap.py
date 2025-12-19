from __future__ import annotations

import sys
from pathlib import Path


def ensure_gui_root_on_syspath() -> Path:
    """Ensure the GUI root (../..) is on sys.path so local imports work.

    The standalone script lives under `gui/standalone_scripts/`.
    """
    gui_root = Path(__file__).resolve().parents[2]
    if str(gui_root) not in sys.path:
        sys.path.insert(0, str(gui_root))
    return gui_root
