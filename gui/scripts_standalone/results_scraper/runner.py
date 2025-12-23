from __future__ import annotations

import asyncio
import logging

from playwright.async_api import async_playwright

from .env import Credentials
from .navigation import (
    TARGET_URL,
    attempt_login,
    click_first_pdf_in_list,
    click_full_glossy_pdf_list,
    click_results_summaries,
    fill_and_click_quote,
)
from .paths import ProjectPaths
from .utils import dump_debug, sanitize_ticker
from .watchlist import DBENGINE_IMPORT_PATH, WATCHLIST_HELPER_PATH, DBEngine, debug_get_watchlist_rows, resolve_tickers_to_process


async def run(
    *,
    ticker: str | None,
    list_only: bool,
    limit: int | None,
    debug_values: bool,
    manual_pdf_url: bool,
    creds: Credentials,
    paths: ProjectPaths,
) -> int:
    logger = logging.getLogger(__name__)
    step_delay_seconds = 2

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            context = await browser.new_context()
            page = await context.new_page()

            async def _close_popup(popup_page):
                try:
                    logger.warning("Popup opened (%s). Closing it.", getattr(popup_page, "url", ""))
                    await popup_page.close()
                except Exception:
                    pass

            # Belt-and-suspenders: close popups so PDF links don't open new tabs.
            # If user wants to copy the URL, don't auto-close.
            if not manual_pdf_url:
                try:
                    page.on("popup", lambda popup: asyncio.create_task(_close_popup(popup)))
                except Exception:
                    pass
                try:
                    context.on("page", lambda new_page: asyncio.create_task(_close_popup(new_page)))
                except Exception:
                    pass

            logger.info("Navigating to %s", TARGET_URL)
            try:
                await page.goto(TARGET_URL, wait_until="networkidle", timeout=30000)
            except Exception:
                logger.warning("Initial goto timed out; retrying with domcontentloaded and longer timeout")
                try:
                    await page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)
                except Exception:
                    logger.exception("Page.goto failed on retry; dumping debug and aborting")
                    try:
                        await dump_debug(page, paths.debug_dir, "goto_failed")
                    except Exception:
                        pass
                    raise

            logger.info("Page loaded. Close the browser to exit.")

            if creds.username and creds.password:
                logger.info("Attempting to log in using credentials from .env")
                success = await attempt_login(page, username=creds.username, password=creds.password, debug_dir=paths.debug_dir)
                if success:
                    logger.info("Logged in successfully")
                else:
                    logger.warning("Login attempt failed; continuing without authentication")
                    try:
                        await dump_debug(page, paths.debug_dir, "login_failed")
                    except Exception:
                        pass
            else:
                logger.warning(
                    "Skipping login: OST_USERNAME/OST_PASSWORD not set (or placeholders). "
                    "Create a .env next to the script with OST_USERNAME and OST_PASSWORD, or set env vars."
                )

            logger.info("DBEngine import path: %s; watchlist helper path: %s", DBENGINE_IMPORT_PATH, WATCHLIST_HELPER_PATH)

            tickers_to_process = await resolve_tickers_to_process(ticker, limit)
            logger.info("Processing %d ticker(s)", len(tickers_to_process))

            if list_only:
                for t in tickers_to_process:
                    print(t)

                if debug_values and DBEngine:
                    rows = await debug_get_watchlist_rows(limit=limit)
                    for r in rows:
                        print(r)

                await browser.close()
                return 0

            for t in tickers_to_process:
                if not t:
                    continue
                canon = sanitize_ticker(t)

                logger.info("Processing ticker %s (sanitized %s)", t, canon)

                # Allow the user to visually follow each automation step.
                await asyncio.sleep(step_delay_seconds)

                filled = await fill_and_click_quote(page, ticker=canon, debug_dir=paths.debug_dir)
                if not filled:
                    logger.warning("Unable to fill or click quote for %s", canon)
                    continue

                await asyncio.sleep(step_delay_seconds)

                clicked_rs = await click_results_summaries(page, debug_dir=paths.debug_dir)
                if not clicked_rs:
                    logger.warning("Failed to click Results Summaries for %s", canon)
                    continue

                await asyncio.sleep(step_delay_seconds)

                clicked_pdf_list = await click_full_glossy_pdf_list(
                    page,
                    debug_dir=paths.debug_dir,
                    allow_popups=manual_pdf_url,
                )
                if not clicked_pdf_list:
                    logger.warning("Failed to click Full glossy PDF link for %s", canon)
                    continue

                await asyncio.sleep(step_delay_seconds)

                downloaded = await click_first_pdf_in_list(
                    page,
                    ticker=canon,
                    results_root=paths.results_root,
                    debug_dir=paths.debug_dir,
                    manual_pdf_url=manual_pdf_url,
                )
                if downloaded:
                    logger.info("Downloaded first PDF for %s", canon)
                else:
                    logger.warning("Failed to download first PDF for %s", canon)

                await asyncio.sleep(step_delay_seconds)

                # Reset UI state for the next ticker
                try:
                    await page.goto(TARGET_URL, wait_until="networkidle", timeout=15000)
                except Exception:
                    try:
                        await page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=30000)
                    except Exception:
                        pass
                await asyncio.sleep(1)

            # Wait until the page is closed by the user.
            close_event = asyncio.Event()

            def _on_close(_=None):
                close_event.set()

            try:
                page.on("close", _on_close)
            except Exception:
                pass

            try:
                browser.on("disconnected", _on_close)
            except Exception:
                try:
                    context.on("close", _on_close)
                except Exception:
                    pass

            if not page.is_closed():
                await close_event.wait()

            logger.info("Detected browser/page close — exiting.")
            await browser.close()

        return 0

    except Exception:
        logger.exception("Fatal error in Playwright run")
        return 2
