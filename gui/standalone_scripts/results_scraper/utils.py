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
