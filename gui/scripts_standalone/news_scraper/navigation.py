from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from scripts_standalone.results_scraper.utils import dump_debug, find_frame


async def click_news(page, *, debug_dir: Path) -> bool:
    """Click the 'News (N)' link inside the nav_content frame."""
    logger = logging.getLogger(__name__)

    nav_content = await find_frame(page, name="nav_content", timeout=10.0)
    if not nav_content:
        logger.warning("nav_content frame not found; cannot click News")
        try:
            await dump_debug(page, debug_dir, "nav_content_missing_news")
        except Exception:
            pass
        return False

    # Wait for the News anchor to appear.
    try:
        await nav_content.wait_for_selector("a[title='News (N)']", timeout=5000)
    except Exception:
        # fallback below
        pass

    link = None
    try:
        link = await nav_content.query_selector("a[title='News (N)']")
        if not link:
            link = await nav_content.query_selector("a[href*='News/NewsHeadlines.aspx']")
        if not link:
            link = await nav_content.query_selector("a:has-text('News')")
    except Exception:
        link = None

    if not link:
        logger.warning("News link not found in nav_content")
        try:
            await dump_debug(page, debug_dir, "news_link_missing")
        except Exception:
            pass
        return False

    try:
        await link.click()
        try:
            await page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            await asyncio.sleep(1)
        return True
    except Exception:
        logger.exception("Failed to click News link")
        try:
            await dump_debug(page, debug_dir, "news_click_failed")
        except Exception:
            pass
        return False
