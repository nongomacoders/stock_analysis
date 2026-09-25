"""Strict manual historical results-package discovery and validation.

Core invariant
--------------
``period_end``   – the date the economics occurred (reporting period close).
``published_at`` – the date the document became available to an analyst.

These are NEVER interchangeable.  A backtest may only use evidence whose
``published_at`` <= backtest ``as_of_date``.  An unresolved ``published_at``
(None) means the source is BLOCKED from historical evidence until resolved.
"""
from __future__ import annotations

import re
import json
from datetime import date
from hashlib import sha256
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

from scripts_standalone.results_scraper.utils import sanitize_ticker
from modules.analysis.results_package import (
    classify_path,
    build_results_package,
    read_document_text,
    RESULTS_SENS,
    ANNUAL_FINANCIAL_STATEMENTS,
)

try:
    from modules.analysis.results_package import _period as _results_period
except Exception:
    _results_period = None

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PERIOD_RE = re.compile(r'^(FY\d{4}|H[12]_FY\d{4}|Q[1-4]_FY\d{4}|9M_FY\d{4})$')
HISTORICAL_RESULTS_ROOT = Path(__file__).resolve().parents[2] / 'results_history'
WINDOWS_RESERVED = {
    'CON', 'PRN', 'AUX', 'NUL',
    *[f'COM{x}' for x in range(1, 10)],
    *[f'LPT{x}' for x in range(1, 10)],
}

# JSE SENS footer: "Date: DD/MM/YYYY HH:MM:SS" or "Date: DD-MM-YYYY HH:MM:SS"
# Accepts slash or dash separators.
_SENS_DATE_RE = re.compile(
    r'\bDate:\s*(\d{2})[/\-](\d{2})[/\-](\d{4})(?:\s+\d{2}:\d{2}:\d{2})?',
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def canonical_ticker_folder(ticker: str) -> str:
    value = ticker.strip().upper()
    if not re.fullmatch(r'[A-Z0-9][A-Z0-9.\-]*\.JO', value):
        raise ValueError('Unsupported ticker identity')
    symbol = sanitize_ticker(value).upper()
    if not symbol or symbol in WINDOWS_RESERVED or re.search(r'[<>:"/\\|?*]', symbol):
        raise ValueError('Invalid Windows ticker folder')
    return symbol


def controlled_period_label(label: str) -> str:
    value = label.strip().upper()
    if not PERIOD_RE.fullmatch(value):
        raise ValueError('Uncontrolled historical period label')
    if '..' in value or re.search(r'[<>:"/\\|?*]', value) or value in WINDOWS_RESERVED:
        raise ValueError('Unsafe historical period label')
    return value


def controlled_period_values(start_year=2000, end_year=None):
    end_year = end_year or date.today().year + 5
    values = []
    for year in range(start_year, end_year + 1):
        values.extend((
            f'FY{year}', f'H1_FY{year}', f'H2_FY{year}',
            f'Q1_FY{year}', f'Q2_FY{year}', f'Q3_FY{year}', f'Q4_FY{year}',
            f'9M_FY{year}',
        ))
    return tuple(values)


def period_type(label: str) -> str:
    if label.startswith('FY'):
        return 'fiscal_year'
    if label.startswith('H'):
        return 'half_year'
    if label.startswith('Q'):
        return 'quarter'
    return 'nine_month'


def expected_filenames(ticker: str, label: str) -> dict[str, str]:
    symbol = canonical_ticker_folder(ticker)
    period = controlled_period_label(label)
    return {'SENS': f'{symbol}_{period}_SENS.txt', 'AFS': f'{symbol}_{period}_AFS.pdf'}


def package_folder(ticker: str, label: str, root: Path | None = None) -> Path:
    root = (root or HISTORICAL_RESULTS_ROOT).resolve()
    target = (root / canonical_ticker_folder(ticker) / controlled_period_label(label)).resolve()
    if root not in target.parents:
        raise ValueError('Historical package path escapes results_history')
    return target


def starter_manifest(ticker: str, label: str) -> dict:
    period = controlled_period_label(label)
    return {
        'schema_version': 1,
        'ticker': ticker.strip().upper(),
        'symbol': canonical_ticker_folder(ticker),
        'period_label': period,
        'period_type': period_type(period),
        'period_start': None,
        'period_end': None,
        'sources': [],
    }


# ---------------------------------------------------------------------------
# SENS publication-date parser
# ---------------------------------------------------------------------------

def parse_sens_publication_date(text: str) -> tuple[Optional[date], Optional[str]]:
    """Extract the JSE SENS footer publication date from document text.

    Returns
    -------
    (parsed_date, detection_source)
        where detection_source is a human-readable description of how the date
        was found, or (None, None) if unresolved.

    Priority
    --------
    1. JSE SENS footer: "Date: DD/MM/YYYY HH:MM:SS" or "Date: DD-MM-YYYY ..."
    2. (Future) Announcement/publication date in document body.
    3. Explicit user/manifest override (handled upstream, not here).
    """
    # 1. JSE SENS footer timestamp (supports DD/MM/YYYY and DD-MM-YYYY)
    for m in _SENS_DATE_RE.finditer(text):
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            d = date(year, month, day)
            return d, 'SENS footer timestamp'
        except ValueError:
            continue  # malformed values, keep scanning

    # 2. No structured date found
    return None, None


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class ManifestSource(BaseModel):
    type: Literal['SENS', 'AFS', 'PRESENTATION', 'TRANSCRIPT']
    file: str
    # published_at is Optional – None means "unresolved / not yet established"
    published_at: Optional[date] = None
    # availability_status is derived from published_at
    availability_status: Literal['resolved', 'unresolved'] = 'unresolved'
    revision: int = Field(default=1, ge=1)
    active: bool = True
    supersedes: Optional[str] = None

    @model_validator(mode='after')
    def derive_availability_status(self) -> 'ManifestSource':
        object.__setattr__(
            self,
            'availability_status',
            'resolved' if self.published_at is not None else 'unresolved',
        )
        return self


class HistoricalManifest(BaseModel):
    schema_version: int = 1
    ticker: str
    symbol: str
    period_label: str
    period_type: Literal['fiscal_year', 'half_year', 'quarter', 'nine_month']
    period_start: Optional[date] = None
    period_end: date
    sources: list[ManifestSource]
    # Populated by model_validator when suspicious (but non-blocking) dates are found
    date_warnings: list[str] = Field(default_factory=list)
    has_suspicious_dates: bool = False

    @model_validator(mode='after')
    def controlled(self) -> 'HistoricalManifest':
        if not PERIOD_RE.fullmatch(self.period_label):
            raise ValueError('Uncontrolled historical period label')
        if sanitize_ticker(self.ticker).upper() != self.symbol.upper():
            raise ValueError('Ticker and symbol disagree')
        if self.period_start and self.period_start > self.period_end:
            raise ValueError('period_start after period_end')

        # Exactly one active SENS and one active AFS are required
        for required in ('SENS', 'AFS'):
            actives = [x for x in self.sources if x.type == required and x.active]
            if len(actives) != 1:
                raise ValueError(f'Exactly one active {required} source is required')

        date_warnings: list[str] = []
        for src in self.sources:
            if src.published_at is None:
                continue  # unresolved is handled by availability_status

            # BLOCKING: published_at < period_end is physically impossible
            if src.published_at < self.period_end:
                raise ValueError(
                    f'BLOCKING_ERROR: {src.type} source published_at ({src.published_at}) '
                    f'precedes period_end ({self.period_end}). '
                    'A document cannot be published before the reporting period has closed.'
                )

            # SUSPICIOUS_DATE warning: equality is almost certainly wrong but
            # not physically impossible (e.g. same-day announcement).  Warn
            # rather than block, so existing manifests remain loadable while
            # the analyst corrects them.
            if src.published_at == self.period_end:
                date_warnings.append(
                    f'SUSPICIOUS_DATE: {src.type} source published_at ({src.published_at}) '
                    f'equals period_end ({self.period_end}). '
                    'published_at should represent document availability, not the period close. '
                    'Review and correct this manifest entry.'
                )

        object.__setattr__(self, 'date_warnings', date_warnings)
        object.__setattr__(self, 'has_suspicious_dates', bool(date_warnings))
        return self


# ---------------------------------------------------------------------------
# Scaffold / status
# ---------------------------------------------------------------------------

def create_package_scaffold(ticker: str, label: str, root: Path | None = None, *,
                             create_missing_manifest: bool = False):
    folder = package_folder(ticker, label, root)
    existed = folder.exists()
    folder.mkdir(parents=True, exist_ok=True)
    manifest = folder / 'manifest.json'
    created_manifest = False
    if not manifest.exists() and (not existed or create_missing_manifest):
        manifest.write_text(
            json.dumps(starter_manifest(ticker, label), indent=2) + '\n',
            encoding='utf-8',
        )
        created_manifest = True
    return {
        'folder': folder,
        'folder_created': not existed,
        'manifest_created': created_manifest,
        'expected_files': expected_filenames(ticker, label),
        'status': package_status(ticker, label, root),
    }


def package_status(ticker: str, label: str, root: Path | None = None):
    folder = package_folder(ticker, label, root)
    expected = expected_filenames(ticker, label)
    manifest = folder / 'manifest.json'
    sens = folder / expected['SENS']
    afs = folder / expected['AFS']
    known = {'manifest.json', *expected.values()}
    unexpected = (
        sorted(x.name for x in folder.iterdir() if x.is_file() and x.name not in known)
        if folder.is_dir() else []
    )
    state = 'MISSING'
    validation = None
    if folder.is_dir():
        state = (
            'READY TO VALIDATE'
            if manifest.is_file() and sens.is_file() and afs.is_file()
            else 'INCOMPLETE'
        )
        if state == 'READY TO VALIDATE':
            validation = validate_period_folder(folder, ticker)
    return {
        'ticker': ticker,
        'period_label': controlled_period_label(label),
        'folder': folder,
        'folder_exists': folder.is_dir(),
        'manifest_exists': manifest.is_file(),
        'sens_exists': sens.is_file(),
        'afs_exists': afs.is_file(),
        'unexpected_files': unexpected,
        'status': state,
        'validation': validation,
        'expected_files': expected,
    }


# ---------------------------------------------------------------------------
# Folder validation
# ---------------------------------------------------------------------------

def validate_period_folder(folder: Path, expected_ticker: str, as_of_date: date | None = None):
    folder = Path(folder)
    errors: list[str] = []
    warnings: list[str] = []
    manifest_path = folder / 'manifest.json'

    if not manifest_path.is_file():
        return {'status': 'INVALID', 'errors': ['Missing manifest.json'], 'warnings': []}

    try:
        raw = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
        period = controlled_period_label(str(raw.get('period_label') or ''))
        symbol = canonical_ticker_folder(str(raw.get('ticker') or ''))
        if (raw.get('symbol', '').upper() != symbol
                or folder.parent.name.upper() != symbol
                or folder.name != period):
            raise ValueError('Starter manifest identity or folder mismatch')
        if raw.get('period_end') is None or not raw.get('sources'):
            return {
                'status': 'INCOMPLETE',
                'errors': [],
                'warnings': ['Starter manifest requires period_end and source metadata'],
                'manifest': raw,
                'sources': [],
            }
        manifest = HistoricalManifest.model_validate(raw)
    except Exception as exc:
        return {'status': 'INVALID', 'errors': [str(exc)], 'warnings': []}

    symbol = sanitize_ticker(expected_ticker)
    if folder.parent.name.upper() != symbol.upper():
        errors.append('Ticker folder mismatch')
    if folder.name != manifest.period_label:
        errors.append('Period folder mismatch')
    if manifest.ticker.upper() != expected_ticker.upper():
        errors.append('Manifest ticker mismatch')

    sources: list[dict] = []
    hashes: dict[str, str] = {}
    expected_roles = {'SENS': RESULTS_SENS, 'AFS': ANNUAL_FINANCIAL_STATEMENTS}
    declared = {x.file for x in manifest.sources}

    for spec in manifest.sources:
        path = folder / spec.file
        expected_stem = f'{manifest.symbol}_{manifest.period_label}_{spec.type}'
        stem = re.sub(r'_v\d+$', '', path.stem)
        if stem != expected_stem:
            errors.append(f'Filename identity mismatch: {spec.file}')
        if path.suffix.lower() not in (
            {'.txt'} if spec.type in {'SENS', 'TRANSCRIPT'} else {'.pdf'}
        ):
            errors.append(f'Unsupported extension for {spec.type}: {spec.file}')
        if not path.is_file():
            errors.append(f'Missing file: {spec.file}')
            continue

        try:
            data = path.read_bytes()
        except OSError as exc:
            errors.append(f'Unreadable file {spec.file}: {exc}')
            continue
        if not data:
            errors.append(f'Zero-byte file: {spec.file}')
            continue

        digest = sha256(data).hexdigest()
        if digest in hashes:
            errors.append(f'Duplicate file hash: {spec.file} and {hashes[digest]}')
        hashes[digest] = spec.file

        detected = classify_path(path)
        if spec.type in expected_roles and detected != expected_roles[spec.type]:
            errors.append(f'Filename says {spec.type} but content classified as {detected}')

        # ── Leakage-proof availability gate ──────────────────────────────
        if spec.published_at is None:
            # Unresolved: BLOCKED from historical evidence.
            # No code path may substitute period_end here.
            warnings.append(
                f'{spec.type} source {spec.file} has unresolved published_at '
                f'– excluded from historical evidence until resolved.'
            )
            continue

        if as_of_date and spec.published_at > as_of_date:
            continue  # not yet available as of the backtest date

        # ── Extract text ──────────────────────────────────────────────────
        text = ''
        if path.suffix.lower() == '.txt':
            text = data.decode('utf-8', errors='ignore')
        else:
            try:
                try:
                    from pypdf import PdfReader
                except ImportError:
                    from PyPDF2 import PdfReader
                text = '\n'.join(
                    page.extract_text() or ''
                    for page in PdfReader(path).pages
                )
            except Exception as exc:
                errors.append(f'PDF extraction failed {spec.file}: {exc}')

        sources.append({
            'source_id': f'historical:{digest}',
            'name': spec.file,
            'text': text,
            'source_date': spec.published_at.isoformat(),
            'available_date': spec.published_at.isoformat(),
            # period_end is metadata only – never used as availability fallback
            'period_end': manifest.period_end.isoformat(),
            'original_path': str(path.resolve()),
            'archive_path': str(path.resolve()),
            'sha256': digest,
            'document_role': detected,
            'active': spec.active,
            'revision': spec.revision,
        })

    for item in folder.iterdir():
        if item.is_file() and item.name != 'manifest.json' and item.name not in declared:
            warnings.append(f'Unexpected file: {item.name}')

    status = 'INVALID' if errors else 'WARNING' if warnings else 'VALID'
    return {
        'status': status,
        'errors': errors,
        'warnings': warnings,
        'manifest': manifest,
        'sources': sources,
    }


# ---------------------------------------------------------------------------
# Package discovery
# ---------------------------------------------------------------------------

def discover_packages(root: Path, ticker: str, as_of_date: date):
    """Discover all validated result packages available on or before as_of_date.

    Leakage rule: sources with unresolved published_at are EXCLUDED.
    No code path substitutes period_end as a fallback.
    """
    ticker_dir = Path(root) / sanitize_ticker(ticker)
    packages = []
    if not ticker_dir.is_dir():
        return packages
    for folder in sorted(x for x in ticker_dir.iterdir() if x.is_dir()):
        result = validate_period_folder(folder, ticker, as_of_date)
        if result['status'] != 'INVALID' and result.get('sources'):
            active = [x for x in result['sources'] if x['active']]
            package = build_results_package(active)
            packages.append({
                'folder': str(folder),
                'validation': result,
                'results_package': package,
            })
    return packages


# ---------------------------------------------------------------------------
# Manifest suggestion helper
# ---------------------------------------------------------------------------

def suggest_manifest(
    ticker: str,
    period_label: str,
    *,
    afs_published_at_override: Optional[date] = None,
    force_afs_date_override: bool = False,  # legacy compat; retained but ignored
) -> dict:
    """Suggest a manifest dict from an existing SENS + AFS pair.

    published_at rules
    ------------------
    SENS: parsed from JSE footer timestamp (DD/MM/YYYY or DD-MM-YYYY).
          Fails closed if not found – will NOT substitute period_end.
    AFS:  ``afs_published_at_override`` if provided; otherwise the SENS
          publication date (defensible: AFS released through same announcement);
          otherwise None (unresolved, BLOCKED).

    Raises ValueError if SENS file is missing or publication date unresolvable.
    """
    folder = package_folder(ticker, period_label, HISTORICAL_RESULTS_ROOT)
    sens_path = folder / expected_filenames(ticker, period_label)['SENS']
    afs_path  = folder / expected_filenames(ticker, period_label)['AFS']

    # ── SENS parsing ──────────────────────────────────────────────────────
    if not sens_path.is_file():
        raise ValueError(
            f'SENS file missing: {sens_path}. '
            'Cannot determine published_at – failing closed.'
        )

    sens_text = sens_path.read_text(encoding='utf-8', errors='ignore')
    sens_date, sens_detection_source = parse_sens_publication_date(sens_text)

    if sens_date is None:
        raise ValueError(
            f'Could not determine SENS publication date from {sens_path.name}. '
            'No JSE footer timestamp (Date: DD/MM/YYYY or Date: DD-MM-YYYY) found. '
            'Failing closed – will not substitute period_end.'
        )

    # ── period_end extraction ─────────────────────────────────────────────
    period_end: Optional[date] = None
    if _results_period:
        try:
            period_end = _results_period(sens_text)
        except Exception:
            pass
    if period_end is None and afs_path.is_file():
        try:
            try:
                from pypdf import PdfReader
            except ImportError:
                from PyPDF2 import PdfReader
            afs_text = ''.join(
                page.extract_text() or ''
                for page in PdfReader(str(afs_path)).pages
            )
            if _results_period:
                period_end = _results_period(afs_text)
        except Exception:
            pass

    # ── AFS published_at ─────────────────────────────────────────────────
    if afs_published_at_override is not None:
        afs_date: Optional[date] = afs_published_at_override
        afs_detection = 'explicit analyst/user override'
    elif afs_path.is_file():
        # Defensible link: AFS first made available through the same SENS announcement
        afs_date = sens_date
        afs_detection = f'linked to SENS publication date ({sens_detection_source})'
    else:
        afs_date = None
        afs_detection = 'AFS file not found – unresolved'

    # ── DATE VALIDATION before building manifest dict ─────────────────────
    # published_at < period_end  → BLOCKING_ERROR (physically impossible)
    # published_at == period_end → SUSPICIOUS_DATE warning (logged, not raised)
    # published_at > period_end  → VALID
    if period_end is not None:
        for src_name, d in [('SENS', sens_date), ('AFS', afs_date)]:
            if d is None:
                continue
            if d < period_end:
                raise ValueError(
                    f'BLOCKING_ERROR: {src_name} published_at ({d}) precedes '
                    f'period_end ({period_end}). '
                    'A document cannot be published before the reporting period has closed.'
                )
            if d == period_end:
                import warnings as _warnings
                _warnings.warn(
                    f'SUSPICIOUS_DATE: {src_name} published_at ({d}) equals '
                    f'period_end ({period_end}). '
                    'published_at should represent document availability, not period close.',
                    stacklevel=2,
                )


    manifest = {
        'schema_version': 1,
        'ticker': ticker.strip().upper(),
        'symbol': canonical_ticker_folder(ticker),
        'period_label': controlled_period_label(period_label),
        'period_type': period_type(period_label),
        'period_start': None,
        'period_end': period_end.isoformat() if period_end else None,
        'sources': [
            {
                'type': 'SENS',
                'file': expected_filenames(ticker, period_label)['SENS'],
                'published_at': sens_date.isoformat() if sens_date else None,
                'revision': 1,
                'active': True,
                '_detection': {
                    'reporting_period_end': period_end.isoformat() if period_end else None,
                    'detected_publication_date': sens_date.isoformat() if sens_date else None,
                    'detection_source': sens_detection_source,
                },
            },
            {
                'type': 'AFS',
                'file': expected_filenames(ticker, period_label)['AFS'],
                'published_at': afs_date.isoformat() if afs_date else None,
                'revision': 1,
                'active': True,
                '_detection': {
                    'reporting_period_end': period_end.isoformat() if period_end else None,
                    'detected_publication_date': afs_date.isoformat() if afs_date else None,
                    'detection_source': afs_detection,
                },
            },
        ],
    }
    return manifest


# ---------------------------------------------------------------------------
# Suspicious manifest audit
# ---------------------------------------------------------------------------

def audit_manifests_for_suspicious_dates(root: Optional[Path] = None) -> list[dict]:
    """Scan all manifests and flag those where published_at == period_end.

    Returns findings list.  Does NOT modify any manifest.  Equality is not
    guaranteed wrong (edge case: SENS published on last day of period) but is
    highly suspicious and must be reviewed.
    """
    root = (root or HISTORICAL_RESULTS_ROOT).resolve()
    findings: list[dict] = []
    if not root.is_dir():
        return findings

    for ticker_dir in sorted(root.iterdir()):
        if not ticker_dir.is_dir():
            continue
        for period_dir in sorted(ticker_dir.iterdir()):
            if not period_dir.is_dir():
                continue
            manifest_path = period_dir / 'manifest.json'
            if not manifest_path.is_file():
                continue
            try:
                raw = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
            except Exception as exc:
                findings.append({'path': str(manifest_path), 'suspicious': False, 'error': str(exc)})
                continue

            period_end_str = raw.get('period_end')
            for src in raw.get('sources', []):
                pa = src.get('published_at')
                if pa and pa == period_end_str:
                    findings.append({
                        'path': str(manifest_path),
                        'ticker': raw.get('ticker'),
                        'period_label': raw.get('period_label'),
                        'source_type': src.get('type'),
                        'source_file': src.get('file'),
                        'published_at': pa,
                        'period_end': period_end_str,
                        'suspicious': True,
                        'reason': (
                            'published_at == period_end: availability date '
                            'should almost never equal the reporting period close. '
                            'Review and correct this manifest entry.'
                        ),
                    })

    return findings


# ---------------------------------------------------------------------------
# UI display helper
# ---------------------------------------------------------------------------

def describe_source_availability(source_entry: dict, period_end: Optional[date] = None) -> str:
    """Return a human-readable availability description for a manifest source."""
    detection = source_entry.get('_detection', {})
    pa_str  = source_entry.get('published_at')
    det_src = detection.get('detection_source')
    pe_str  = detection.get('reporting_period_end') or (
        period_end.isoformat() if period_end else None
    )
    lines = []
    if pe_str:
        lines.append(f'Reporting period end  : {pe_str}')
    if pa_str and det_src:
        lines.append(f'Detected publication  : {pa_str}')
        lines.append(f'Detection source      : {det_src}')
    elif pa_str:
        lines.append(f'Publication date      : {pa_str}')
    else:
        lines.append('Publication date      : UNRESOLVED')
        lines.append('Historical eligibility: BLOCKED')
    return '\n'.join(lines)
