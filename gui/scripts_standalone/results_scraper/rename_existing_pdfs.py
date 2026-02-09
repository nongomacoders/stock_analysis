"""Rename existing PDFs under the results directory to their PDF creation date.

Usage:
    python -m scripts_standalone.results_scraper.rename_existing_pdfs [--results-root PATH] [--apply] [--verbose]

By default the script performs a dry-run and prints proposed renames. Use --apply to perform the filesystem changes.
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Iterable

try:
    # When executed as a module (recommended): use relative imports
    from .paths import compute_paths
    from .utils import extract_pdf_creation_date, format_pdf_filename
except Exception:
    # Support direct execution of the script file (python path/to/rename_existing_pdfs.py)
    # by adding package parent to sys.path and importing by absolute name.
    import sys
    from pathlib import Path

    # Insert the project `gui` directory (parent of scripts_standalone)
    _ROOT = Path(__file__).resolve().parent.parent.parent
    if str(_ROOT) not in sys.path:
        sys.path.insert(0, str(_ROOT))

    from scripts_standalone.results_scraper.paths import compute_paths
    from scripts_standalone.results_scraper.utils import (
        extract_pdf_creation_date,
        format_pdf_filename,
    )


logger = logging.getLogger(__name__)


def iter_pdf_files(root: Path) -> Iterable[Path]:
    """Yield all .pdf files under `root` (recursively)."""
    if not root.exists():
        return
    for p in root.rglob("*.pdf"):
        if p.is_file():
            yield p


def unique_target_path(path: Path, new_name: str) -> Path:
    """Return a Path that does not collide by appending _N if necessary."""
    candidate = path.with_name(new_name)
    if not candidate.exists() or candidate.samefile(path):
        return candidate

    stem = new_name[:-4] if new_name.lower().endswith(".pdf") else new_name
    i = 1
    while True:
        new_candidate = path.with_name(f"{stem}_{i}.pdf")
        if not new_candidate.exists():
            return new_candidate
        i += 1


def process_file(path: Path, apply: bool = False) -> bool:
    """Try to extract creation date and rename the file (date-only). Returns True if renamed."""
    try:
        data = path.read_bytes()
    except Exception as ex:
        logger.exception("Failed to read %s: %s", path, ex)
        return False

    if not data.startswith(b"%PDF"):
        logger.debug("Skipping %s: not a PDF (magic missing)", path)
        return False

    dt = extract_pdf_creation_date(data)
    if not dt:
        logger.info("No creation date found for %s", path)
        return False

    new_name = format_pdf_filename(dt)
    if path.name == new_name:
        logger.debug("Already named: %s", path)
        return False

    target = unique_target_path(path, new_name)

    logger.info("Rename: %s -> %s %s", path, target, "(dry-run)" if not apply else "")
    if apply:
        try:
            path.rename(target)
            logger.info("Renamed %s -> %s", path, target)
            return True
        except Exception:
            logger.exception("Failed to rename %s -> %s", path, target)
            return False

    return False


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Rename existing PDFs to their creation date")
    ap.add_argument("--results-root", type=Path, help="Path to results directory (default from project layout)")
    ap.add_argument("--apply", action="store_true", help="Actually perform renames. By default this is a dry-run")
    ap.add_argument("--verbose", action="store_true", help="Verbose logging")
    args = ap.parse_args(argv)

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s: %(message)s")

    paths = compute_paths()
    root = args.results_root or paths.results_root

    if not root.exists():
        logger.error("Results root does not exist: %s", root)
        return 2

    total = 0
    renamed = 0
    for p in iter_pdf_files(root):
        total += 1
        if process_file(p, apply=args.apply):
            renamed += 1

    logger.info("Done: scanned %d PDF(s), renamed %d", total, renamed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
