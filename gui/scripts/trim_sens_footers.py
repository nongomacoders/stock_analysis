"""Trim boilerplate SENS footer text from extracted announcement .txt files.

Goal: reduce token/size before feeding to AI.

Heuristics (in order):
1) If we see the standard footer start ("Produced by the JSE SENS Department"),
   drop that line and everything after it.
2) Otherwise, find the last occurrence of a sponsor marker (Sponsor/JSE sponsor/
   misspelling sponser) near the end of the document and drop everything after
   the sponsor block.

By default this runs in dry-run mode and prints what it *would* do.
Use --in-place to rewrite files.

Examples:
  python gui/scripts/trim_sens_footers.py --dry-run
  python gui/scripts/trim_sens_footers.py --in-place --backup
  python gui/scripts/trim_sens_footers.py --in-place --paths gui/results/NPN/news_*.txt
"""

from __future__ import annotations

import argparse
import glob
import re
from dataclasses import dataclass
from pathlib import Path


_PRODUCED_BY_RE = re.compile(r"\bproduced\s+by\b.*\bsens\b", re.IGNORECASE)
_DATE_LINE_RE = re.compile(r"^\s*date\s*:\s*\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}", re.IGNORECASE)
_SPONSOR_RE = re.compile(r"\bspon(?:s|c)or\b", re.IGNORECASE)  # sponsor/sponser

# Extra footer markers that frequently appear after Sponsor.
_FOOTER_MARKER_RE = re.compile(
    r"\bproduced\s+by\b|\bthe\s+sens\s+service\b|\bthe\s+jse\s+does\s+not\b|^\s*date\s*:",
    re.IGNORECASE | re.MULTILINE,
)


@dataclass(frozen=True)
class TrimResult:
    changed: bool
    reason: str
    original_chars: int
    trimmed_chars: int


def _normalize_text(text: str) -> str:
    t = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    # Strip trailing whitespace per line.
    lines = [ln.rstrip() for ln in t.split("\n")]

    # Collapse excessive blank lines (keep max 2).
    out: list[str] = []
    blank_run = 0
    for ln in lines:
        if ln.strip() == "":
            blank_run += 1
            if blank_run <= 2:
                out.append("")
        else:
            blank_run = 0
            out.append(ln)

    # Trim leading/trailing blank lines.
    while out and out[0].strip() == "":
        out.pop(0)
    while out and out[-1].strip() == "":
        out.pop()

    return "\n".join(out) + ("\n" if out else "")


def trim_sens_footer(text: str) -> tuple[str, TrimResult]:
    original = _normalize_text(text)
    if not original.strip():
        return original, TrimResult(False, "empty", 0, 0)

    lines = original.splitlines()
    n = len(lines)

    # 1) Strong anchor: Produced by...
    produced_idx = None
    for i, ln in enumerate(lines):
        if _PRODUCED_BY_RE.search(ln):
            produced_idx = i
            break
    if produced_idx is not None:
        kept = lines[:produced_idx]
        trimmed = _normalize_text("\n".join(kept))
        return trimmed, TrimResult(
            changed=trimmed != original,
            reason="cut_at_produced_by",
            original_chars=len(original),
            trimmed_chars=len(trimmed),
        )

    # 2) Sponsor-based trimming (near end + only if footer markers exist after it)
    sponsor_idxs = [i for i, ln in enumerate(lines) if _SPONSOR_RE.search(ln)]
    if sponsor_idxs:
        sponsor_idx = sponsor_idxs[-1]

        # Only consider it a footer section if sponsor appears late in the doc.
        if sponsor_idx >= int(0.6 * n):
            # Determine end of sponsor block: keep sponsor line + up to 3 following non-empty lines.
            j = sponsor_idx + 1
            captured_follow = 0
            while j < n and captured_follow < 3:
                if lines[j].strip() == "":
                    if captured_follow > 0:
                        break
                    j += 1
                    continue
                captured_follow += 1
                j += 1
            sponsor_block_end = max(sponsor_idx, j - 1)

            remainder = "\n".join(lines[sponsor_block_end + 1 :])
            if _FOOTER_MARKER_RE.search(remainder):
                kept = lines[: sponsor_block_end + 1]
                trimmed = _normalize_text("\n".join(kept))
                return trimmed, TrimResult(
                    changed=trimmed != original,
                    reason="cut_after_sponsor_block",
                    original_chars=len(original),
                    trimmed_chars=len(trimmed),
                )

    # 3) Optional fallback: if there's a Date: line very near the end and then boilerplate, cut at Date:
    # (kept conservative: only triggers if we also see boilerplate markers somewhere after Date)
    date_idxs = [i for i, ln in enumerate(lines) if _DATE_LINE_RE.match(ln)]
    if date_idxs:
        date_idx = date_idxs[-1]
        if date_idx >= int(0.7 * n):
            remainder = "\n".join(lines[date_idx:])
            if _FOOTER_MARKER_RE.search(remainder):
                kept = lines[:date_idx]
                trimmed = _normalize_text("\n".join(kept))
                return trimmed, TrimResult(
                    changed=trimmed != original,
                    reason="cut_at_date_line",
                    original_chars=len(original),
                    trimmed_chars=len(trimmed),
                )

    return original, TrimResult(False, "no_change", len(original), len(original))


def _iter_target_files(root: Path, patterns: list[str]) -> list[Path]:
    files: list[Path] = []
    for pat in patterns:
        files.extend(root.glob(pat))
    # De-dup while preserving order.
    seen: set[Path] = set()
    out: list[Path] = []
    for p in files:
        rp = p.resolve()
        if rp in seen:
            continue
        seen.add(rp)
        out.append(p)
    return [p for p in out if p.is_file()]


def _expand_path_specs(specs: list[str], *, repo_root: Path, gui_root: Path) -> list[Path]:
    """Expand --paths entries.

    PowerShell does not always expand globs for Python args (depends on quoting).
    This function treats each spec as either a literal path or a glob pattern.

    It also tries common bases so users can run the script from either repo root
    or inside the gui/ folder.
    """

    expanded: list[Path] = []

    for raw in specs:
        s = (raw or "").strip("\"'")
        if not s:
            continue

        # Candidate patterns to try.
        candidates: list[str] = []
        p = Path(s)

        # 1) As provided (relative to current working directory).
        candidates.append(s)

        # 2) If relative, try interpreting relative to repo root and gui root.
        if not p.is_absolute():
            candidates.append(str((repo_root / p).resolve()))
            candidates.append(str((gui_root / p).resolve()))

        # 3) If it starts with gui/, additionally try stripping that prefix.
        # Useful when running from inside gui/ but passing gui/results/...
        if len(p.parts) >= 2 and p.parts[0].lower() == "gui":
            try:
                without_gui = Path(*p.parts[1:])
                candidates.append(str(without_gui))
                if not without_gui.is_absolute():
                    candidates.append(str((gui_root / without_gui).resolve()))
            except Exception:
                pass

        matches: list[str] = []
        seen_patterns: set[str] = set()
        for cand in candidates:
            if cand in seen_patterns:
                continue
            seen_patterns.add(cand)
            matches.extend(glob.glob(cand, recursive=True))

        if matches:
            for m in matches:
                expanded.append(Path(m))
        else:
            # Keep as a literal; the caller will report read failure.
            expanded.append(Path(s))

    # De-dup while preserving order.
    seen: set[Path] = set()
    out: list[Path] = []
    for p in expanded:
        rp = p.resolve() if p.exists() else p
        if rp in seen:
            continue
        seen.add(rp)
        out.append(p)
    return out


def main(argv: list[str] | None = None) -> int:
    script_dir = Path(__file__).resolve().parent
    gui_root = script_dir.parent
    repo_root = gui_root.parent
    default_root = gui_root / "results"

    parser = argparse.ArgumentParser(description="Trim SENS boilerplate footer from extracted .txt files")
    parser.add_argument("--root", type=Path, default=default_root, help=f"Root folder to scan (default: {default_root})")
    parser.add_argument(
        "--glob",
        action="append",
        default=["**/*.txt"],
        help="Glob pattern(s) under root (default: **/*.txt). Can be specified multiple times.",
    )
    parser.add_argument(
        "--paths",
        nargs="*",
        default=None,
        help="Optional explicit file paths or glob patterns. If provided, ignores --root/--glob.",
    )
    parser.add_argument("--in-place", action="store_true", help="Rewrite files in place")
    parser.add_argument("--backup", action="store_true", help="When using --in-place, write a .bak copy")
    parser.add_argument("--dry-run", action="store_true", help="Show changes but do not write")
    args = parser.parse_args(argv)

    if args.paths:
        targets = _expand_path_specs(args.paths, repo_root=repo_root, gui_root=gui_root)
    else:
        targets = _iter_target_files(args.root, args.glob)

    if not targets:
        print("No files found.")
        return 0

    write_enabled = args.in_place and not args.dry_run

    changed = 0
    total = 0
    saved_chars = 0

    for path in targets:
        total += 1
        try:
            raw = path.read_text(encoding="utf-8", errors="ignore")
        except Exception as ex:
            print(f"SKIP {path}: read failed: {ex}")
            continue

        trimmed, info = trim_sens_footer(raw)
        if info.changed:
            changed += 1
            saved_chars += max(0, info.original_chars - info.trimmed_chars)

            print(f"TRIM {path} ({info.reason}) chars {info.original_chars} -> {info.trimmed_chars}")

            if write_enabled:
                try:
                    if args.backup:
                        bak = path.with_suffix(path.suffix + ".bak")
                        if not bak.exists():
                            bak.write_text(raw, encoding="utf-8")
                    path.write_text(trimmed, encoding="utf-8")
                except Exception as ex:
                    print(f"ERROR {path}: write failed: {ex}")
        else:
            print(f"KEEP {path} ({info.reason})")

    print(f"\nProcessed {total} file(s). Trimmed {changed}. Saved ~{saved_chars} characters.")
    if args.dry_run or not args.in_place:
        print("No files were modified (dry-run / not in-place).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
