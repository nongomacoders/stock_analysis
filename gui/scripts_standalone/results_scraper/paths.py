from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProjectPaths:
    gui_root: Path
    script_dir: Path
    debug_dir: Path
    results_root: Path


def compute_paths() -> ProjectPaths:
    """Compute key paths.

    This package is located at: gui/standalone_scripts/results_scraper/
    So:
    - script_dir = gui/standalone_scripts
    - gui_root   = gui
    """
    package_dir = Path(__file__).resolve().parent
    script_dir = package_dir.parent
    gui_root = script_dir.parent

    debug_dir = script_dir / "debug"
    results_root = gui_root / "results"

    return ProjectPaths(
        gui_root=gui_root,
        script_dir=script_dir,
        debug_dir=debug_dir,
        results_root=results_root,
    )
