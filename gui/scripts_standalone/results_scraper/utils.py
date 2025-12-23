from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime
from pathlib import Path


def sanitize_ticker(ticker: str | None) -> str:
    if not ticker:
        return ""
    value = str(ticker).strip()
    if value.upper().endswith(".JO"):
        return value[:-3]
    return value


async def dump_debug(page, debug_dir: Path, label: str) -> None:
    logger = logging.getLogger(__name__)
    try:
        os.makedirs(debug_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = debug_dir / f"{ts}_{label}"

        try:
            await page.screenshot(path=str(base) + ".png", full_page=True)
        except Exception:
            logger.debug("screenshot failed")

        try:
            html = await page.content()
            (Path(str(base) + ".html")).write_text(html, encoding="utf-8")
        except Exception:
            logger.debug("saving HTML failed")

        logger.info("Debug dumped to %s.*", base)
    except Exception:
        logger.exception("Failed to write debug artifacts")


async def find_frame(
    page,
    *,
    name: str | None = None,
    url_contains: str | None = None,
    selector: str | None = None,
    timeout: float = 10.0,
):
    """Find a frame by name, URL substring, or presence of a selector."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        for frame in page.frames:
            try:
                if name and getattr(frame, "name", None) == name:
                    return frame
                if url_contains and getattr(frame, "url", None) and url_contains in frame.url:
                    return frame
                if selector:
                    try:
                        el = await frame.query_selector(selector)
                        if el:
                            return frame
                    except Exception:
                        pass
            except Exception:
                continue
        await asyncio.sleep(0.25)
    return None


# PDF metadata helpers -------------------------------------------------------
import re
from dateutil import parser as _dateutil_parser
from datetime import datetime as _dt


def extract_pdf_creation_date(data: bytes) -> _dt | None:
    """Try to extract a creation datetime from PDF bytes.

    Looks for XMP CreateDate, then /CreationDate or /ModDate in PDF info.
    Returns a timezone-aware datetime when possible, otherwise naive datetime.
    """
    try:
        # 1) Try XMP packet
        xmp_start = data.find(b"<x:xmpmeta")
        if xmp_start >= 0:
            xmp_end = data.find(b"</x:xmpmeta>", xmp_start)
            if xmp_end >= 0:
                xmp = data[xmp_start : xmp_end + 12]
                m = re.search(rb"<xmp:CreateDate>([^<]+)</xmp:CreateDate>", xmp)
                if m:
                    s = m.group(1).decode("utf-8", errors="replace").strip()
                    try:
                        return _dateutil_parser.parse(s)
                    except Exception:
                        pass
                # Common alternate XMP tags
                m = re.search(rb"<xmp:CreateDate[^>]*>([^<]+)</xmp:CreateDate>", xmp)
                if m:
                    s = m.group(1).decode("utf-8", errors="replace").strip()
                    try:
                        return _dateutil_parser.parse(s)
                    except Exception:
                        pass

        # 2) Try PDF Info dictionary: /CreationDate (D:YYYY...)
        m = re.search(rb"/CreationDate\s*\(\s*(D:[^\)]+)\s*\)", data)
        if not m:
            m = re.search(rb"/CreationDate\s*\(\s*([^\)]+)\s*\)", data)
        if not m:
            m = re.search(rb"/ModDate\s*\(\s*(D:[^\)]+)\s*\)", data)
        if m:
            raw = m.group(1).decode("utf-8", errors="replace").strip()
            # Normalize D:DATE strings
            if raw.startswith("D:"):
                raw = raw[2:]
                # timezone may be +02'00' style, remove apostrophes
                raw = re.sub(r"'", "", raw)
                # insert colon in timezone if needed for fromisoformat compatibility
                try:
                    return _dateutil_parser.parse(raw)
                except Exception:
                    # Fallback: parse fixed-width components
                    digits = re.match(r"(\d{4})(\d{2})?(\d{2})?(\d{2})?(\d{2})?(\d{2})?", raw)
                    if digits:
                        parts = digits.groups()
                        year = int(parts[0])
                        month = int(parts[1] or 1)
                        day = int(parts[2] or 1)
                        hour = int(parts[3] or 0)
                        minute = int(parts[4] or 0)
                        second = int(parts[5] or 0)
                        return _dt(year, month, day, hour, minute, second)
            else:
                try:
                    return _dateutil_parser.parse(raw)
                except Exception:
                    pass

    except Exception:
        # Best-effort: don't raise from helper
        return None

    return None


def format_pdf_filename(dt: _dt) -> str:
    """Format a datetime into a filesystem-safe filename for a PDF.

    Example: 20251223_101512+0200.pdf
    """
    base = dt.strftime("%Y%m%d_%H%M%S")
    tz = dt.strftime("%z")
    if tz:
        base = f"{base}{tz}"
    return f"{base}.pdf"

