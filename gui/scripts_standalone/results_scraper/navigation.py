from __future__ import annotations

import asyncio
import logging
import posixpath
import re
import urllib.parse
from pathlib import Path

from .db import record_results_download
from .utils import (
    dump_debug,
    find_frame,
    sanitize_ticker,
    extract_pdf_creation_date,
    format_pdf_filename,
)


TARGET_URL = "https://securities.standardbank.co.za/ost/"


async def _extract_url_from_anchor(page, anchor) -> str | None:
    """Best-effort extraction of the navigation/download URL behind an anchor.

    Some OST pages use `target=_blank` and/or `javascript:window.open(...)`.
    We avoid clicking when possible by extracting the eventual URL.
    """
    href_attr = None
    try:
        href_attr = await anchor.get_attribute("href")
    except Exception:
        href_attr = None

    # If href is direct, prefer it.
    if href_attr and not href_attr.lower().startswith("javascript:"):
        return href_attr

    # Try DOM-resolved href property (often absolute), even if href attr is JS.
    try:
        href_prop = await anchor.evaluate("(el) => el.href")
        if href_prop and isinstance(href_prop, str) and href_prop.strip():
            # If it's a javascript: URL, keep looking.
            if not href_prop.lower().startswith("javascript:"):
                return href_prop
    except Exception:
        pass

    # Parse onclick handler for window.open('...') style links.
    try:
        onclick = await anchor.get_attribute("onclick")
        if onclick:
            match = re.search(r"window\\.open\\(\s*['\"]([^'\"]+)['\"]", onclick)
            if match:
                return match.group(1)
    except Exception:
        pass

    return None


def _to_absolute_url(page_url: str, maybe_url: str | None) -> str | None:
    if not maybe_url:
        return None
    # OST sometimes returns Windows-style relative paths like: ..\..\..\PDF\file.pdf
    # Normalize all slashes before resolving.
    value = maybe_url.replace("\\", "/").strip()
    if not value:
        return None
    if value.startswith("http://") or value.startswith("https://"):
        joined = value
    else:
        joined = urllib.parse.urljoin(page_url, value)

    # Normalize any dot segments in the final URL path.
    try:
        parts = urllib.parse.urlsplit(joined)
        norm_path = posixpath.normpath(parts.path.replace("\\", "/"))
        if parts.path.endswith("/") and not norm_path.endswith("/"):
            norm_path += "/"
        if not norm_path.startswith("/"):
            norm_path = "/" + norm_path
        return urllib.parse.urlunsplit((parts.scheme, parts.netloc, norm_path, parts.query, parts.fragment))
    except Exception:
        return joined


async def _find_pdf_anchors(page):
    """Return a list of (frame, anchor) candidates for PDF links."""
    selectors = [
        "table a[href*='.pdf']",
        "a[href*='.pdf']",
        "table a[href*='pdf']",
        "a[href*='pdf']",
        "table a[onclick*='pdf']",
        "a[onclick*='pdf']",
    ]

    # Try nav_content first (fast path)
    nav_content = await find_frame(page, name="nav_content", timeout=2.0)
    if nav_content:
        for sel in selectors:
            try:
                anchors = await nav_content.query_selector_all(sel)
                if anchors:
                    return [(nav_content, a) for a in anchors]
            except Exception:
                pass

    # Fall back to scanning all frames
    for frame in page.frames:
        for sel in selectors:
            try:
                anchors = await frame.query_selector_all(sel)
                if anchors:
                    return [(frame, a) for a in anchors]
            except Exception:
                pass

    # Finally, try the main page document
    for sel in selectors:
        try:
            anchors = await page.query_selector_all(sel)
            if anchors:
                return [(page.main_frame, a) for a in anchors]
        except Exception:
            pass

    return []


async def _disable_popups_in_frames(page) -> None:
    """Best-effort: prevent links from opening new tabs/windows.

    Some OST pages use `window.open(...)` or `target=_blank`.
    We override `window.open` to navigate in the same frame.
    """
    script = """() => {
        try {
            window.open = (url) => {
                try { window.location.href = url; } catch (e) {}
                return null;
            };
        } catch (e) {}
    }"""

    # Apply to existing frames/documents.
    try:
        await page.main_frame.evaluate(script)
    except Exception:
        pass

    for frame in page.frames:
        try:
            await frame.evaluate(script)
        except Exception:
            pass


async def attempt_login(page, *, username: str, password: str, debug_dir: Path) -> bool:
    """Attempt to log in using the page, returns True on success."""
    logger = logging.getLogger(__name__)

    try:
        logger.info("Attempting login (username=%s)", (username or "")[:3] + "***" if username else "<empty>")

        found_frame = await find_frame(page, selector="#normalUsername")
        if not found_frame:
            found_frame = await find_frame(page, selector="#j_password")

        if not found_frame:
            logger.warning("Login frame with #normalUsername/#j_password not found; aborting login")
            return False

        frame = found_frame

        if not await frame.query_selector("#normalUsername"):
            logger.warning("#normalUsername not found in selected login frame; aborting login")
            return False

        # Prefer typing (matches user's desired behavior).
        try:
            await frame.wait_for_selector("#normalUsername", state="visible", timeout=15000)
        except Exception:
            pass
        try:
            await frame.focus("#normalUsername")
            # Clear any prefilled content first.
            try:
                await frame.click("#normalUsername", click_count=3)
                await frame.keyboard.press("Backspace")
            except Exception:
                pass
            await frame.type("#normalUsername", username, delay=50)
        except Exception:
            # Fallback: set value via DOM and dispatch events.
            try:
                await frame.evaluate(
                    """(val) => {
                        const el = document.querySelector('#normalUsername');
                        if (!el) return false;
                        el.focus();
                        el.value = val;
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                        return true;
                    }""",
                    username,
                )
            except Exception:
                pass

        try:
            current_user = await frame.input_value("#normalUsername")
            if (current_user or "").strip() != (username or "").strip():
                logger.warning("Username field did not reflect filled value (got=%r)", current_user)
        except Exception:
            pass

        if not await frame.query_selector("#j_password"):
            logger.warning("#j_password not found in selected login frame; aborting login")
            return False

        try:
            await frame.wait_for_selector("#j_password", state="visible", timeout=15000)
        except Exception:
            pass
        try:
            await frame.focus("#j_password")
            try:
                await frame.click("#j_password", click_count=3)
                await frame.keyboard.press("Backspace")
            except Exception:
                pass
            await frame.type("#j_password", password, delay=50)
        except Exception:
            try:
                await frame.evaluate(
                    """(val) => {
                        const el = document.querySelector('#j_password');
                        if (!el) return false;
                        el.focus();
                        el.value = val;
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                        return true;
                    }""",
                    password,
                )
            except Exception:
                pass

        await asyncio.sleep(1)

        try:
            await frame.click("#submitButton")
        except Exception:
            logger.warning("Login submit not performed; aborting login")
            return False

        try:
            await page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            await asyncio.sleep(1)

        # Wait for login to complete: either the login form disappears, or a Logout control appears
        try:
            await page.wait_for_selector("#loginForm", state="hidden", timeout=6000)
            return True
        except Exception:
            try:
                if await page.is_visible("text=Logout", timeout=3000):
                    return True
            except Exception:
                pass

        # As a last check: consider navigation change as success
        if "Home.aspx" not in page.url and page.url != TARGET_URL:
            return True

        return False
    except Exception:
        logger.exception("Error performing login flow")
        try:
            await dump_debug(page, debug_dir, "login_exception")
        except Exception:
            pass
        return False


async def fill_and_click_quote(page, *, ticker: str, debug_dir: Path) -> bool:
    """Types `ticker` into `markIdTextBox` in the `nav_top` frame and clicks quote."""
    logger = logging.getLogger(__name__)

    try:
        await page.wait_for_load_state("networkidle", timeout=5000)
    except Exception:
        await asyncio.sleep(1)

    nav_frame = await find_frame(page, name="nav_top", url_contains="TopMenu", timeout=10.0)
    if not nav_frame:
        logger.warning("nav_top frame not found; aborting quote action")
        try:
            await dump_debug(page, debug_dir, f"nav_top_missing_{ticker}")
        except Exception:
            pass
        return False

    try:
        await nav_frame.wait_for_selector("#markIdTextBox", timeout=5000)
    except Exception:
        await asyncio.sleep(1)

    box = None
    try:
        box = await nav_frame.query_selector("#markIdTextBox")
    except Exception:
        box = None

    if not box:
        logger.warning("markIdTextBox not found in nav_top frame")
        try:
            await dump_debug(page, debug_dir, f"quote_missing_box_nav_top_{ticker}")
        except Exception:
            pass
        return False

    try:
        await nav_frame.focus("#markIdTextBox")
        await nav_frame.type("#markIdTextBox", ticker, delay=50)
    except Exception:
        try:
            await nav_frame.evaluate(
                "(val) => { const el = document.getElementById('markIdTextBox'); if (el) el.value = val; }",
                ticker,
            )
        except Exception:
            logger.debug("Failed to set markIdTextBox value in nav_top frame")

    button = None
    try:
        button = await nav_frame.query_selector("#quoteButton")
    except Exception:
        button = None

    if not button:
        logger.warning("Could not find #quoteButton in nav_top frame")
        try:
            await dump_debug(page, debug_dir, f"quote_missing_nav_top_{ticker}")
        except Exception:
            pass
        return False

    try:
        await button.click()
        try:
            await page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            await asyncio.sleep(1)
        return True
    except Exception:
        logger.exception("Failed to click #quoteButton")
        try:
            await dump_debug(page, debug_dir, f"quote_click_failed_{ticker}")
        except Exception:
            pass
        return False


async def click_results_summaries(page, *, debug_dir: Path) -> bool:
    """Click the 'Results Summaries' link inside the `nav_content` frame."""
    logger = logging.getLogger(__name__)

    nav_content = await find_frame(page, name="nav_content", timeout=10.0)
    if not nav_content:
        logger.warning("nav_content frame not found; cannot click Results Summaries")
        try:
            await dump_debug(page, debug_dir, "nav_content_missing")
        except Exception:
            pass
        return False

    try:
        await nav_content.wait_for_selector("a[title='Results Summaries']", timeout=5000)
    except Exception:
        pass

    link = None
    try:
        link = await nav_content.query_selector("a[title='Results Summaries']")
        if not link:
            link = await nav_content.query_selector("a[href*='ResultsSummaries.htm']")
        if not link:
            link = await nav_content.query_selector("a:has-text('Results Summaries')")
    except Exception:
        link = None

    if not link:
        logger.warning("Results Summaries link not found in nav_content")
        try:
            await dump_debug(page, debug_dir, "results_summaries_missing")
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
        logger.exception("Failed to click Results Summaries link")
        try:
            await dump_debug(page, debug_dir, "results_summaries_click_failed")
        except Exception:
            pass
        return False


async def click_full_glossy_pdf_list(page, *, debug_dir: Path, allow_popups: bool = False) -> bool:
    """Click the 'Full glossy financials in PDF format' list link in `nav_content`."""
    logger = logging.getLogger(__name__)

    nav_content = await find_frame(page, name="nav_content", timeout=10.0)
    if not nav_content:
        logger.warning("nav_content frame not found; cannot click full glossy PDF list")
        return False

    try:
        await nav_content.wait_for_selector("a[href*='PDF.htm']", timeout=5000)
    except Exception:
        await asyncio.sleep(1)

    link = None
    try:
        link = await nav_content.query_selector("a[href*='PDF.htm']")
        if not link:
            link = await nav_content.query_selector("a:has-text('Full glossy financials in PDF format')")
    except Exception:
        link = None

    if not link:
        logger.warning("Full glossy list link not found in nav_content")
        return False

    # Prefer clicking the link (it may rely on session state). Optionally prevent new-tab behavior.
    try:
        if not allow_popups:
            await _disable_popups_in_frames(page)

        # Remove target=_blank if present.
        try:
            await link.evaluate("(el) => { try { el.target = '_self'; el.removeAttribute('target'); } catch (e) {} }")
        except Exception:
            pass

        await link.click()

        # The navigation often happens inside the nav_content frame, so wait for PDF-ish links to appear.
        try:
            await nav_content.wait_for_selector("a[href*='pdf'], a[href*='.pdf']", timeout=10000)
        except Exception:
            # Fallback: try scanning frames
            candidates = await _find_pdf_anchors(page)
            if not candidates:
                raise

        return True
    except Exception:
        logger.exception("Failed to reach full glossy PDF list")
        try:
            await dump_debug(page, debug_dir, "pdf_list_nav_failed")
        except Exception:
            pass
        return False


async def click_first_pdf_in_list(
    page,
    *,
    ticker: str | None,
    results_root: Path,
    debug_dir: Path,
    manual_pdf_url: bool = False,
) -> bool:
    """Download the first PDF-like link on the current page to results/<ticker>.

    This function intentionally avoids clicking links (which can open new tabs).
    """
    logger = logging.getLogger(__name__)

    candidates = await _find_pdf_anchors(page)
    if not candidates:
        logger.warning("No PDF links found on the current page/frames")
        try:
            await dump_debug(page, debug_dir, f"pdf_links_missing_{sanitize_ticker(ticker)}")
        except Exception:
            pass
        return False

    safe_ticker = sanitize_ticker(ticker) if ticker else "unknown"
    results_dir = results_root / safe_ticker
    results_dir.mkdir(parents=True, exist_ok=True)

    # Strictly direct download without clicking (avoids opening a new tab).
    # User preference: only try the *first* PDF in the table/list.
    _frame, first_anchor = candidates[0]

    try:
        target = await _extract_url_from_anchor(page, first_anchor)
        first_url = _to_absolute_url(page.url, target)
    except Exception:
        first_url = None

    if not first_url:
        logger.warning("Could not resolve first PDF URL")
        try:
            await dump_debug(page, debug_dir, f"pdf_first_url_missing_{safe_ticker}")
        except Exception:
            pass
        return False

    # Manual mode: allow the site to open the PDF in a new tab so the user can copy the URL.
    if manual_pdf_url:
        try:
            candidates = await _find_pdf_anchors(page)
            _frame, first_anchor = candidates[0]

            logger.info("Manual mode: opening the first PDF in a new tab...")
            async with page.expect_popup(timeout=15000) as popup_info:
                await first_anchor.click()
            popup = await popup_info.value

            try:
                await popup.wait_for_load_state("domcontentloaded", timeout=15000)
            except Exception:
                pass

            try:
                logger.info("PDF popup URL: %s", popup.url)
            except Exception:
                logger.info("PDF popup opened (URL unavailable)")

            logger.info("Copy the URL, then close the PDF tab to continue...")
            while not popup.is_closed():
                await asyncio.sleep(0.5)

            return True
        except Exception:
            logger.exception("Manual PDF URL mode failed")
            try:
                await dump_debug(page, debug_dir, f"pdf_manual_mode_failed_{safe_ticker}")
            except Exception:
                pass
            return False

    # Try a couple of *URL variants for the same PDF* (some environments serve /ost/PDF/...)
    urls_to_try: list[str] = [first_url]
    try:
        parts = urllib.parse.urlsplit(first_url)
        if parts.path.startswith("/PDF/"):
            alt_path = "/ost" + parts.path
            alt_url = urllib.parse.urlunsplit((parts.scheme, parts.netloc, alt_path, parts.query, parts.fragment))
            if alt_url not in urls_to_try:
                urls_to_try.append(alt_url)

            # Observed: PDFs are served under /ost/sp/profilem/PDF/... for authenticated sessions.
            alt_path_profilem = "/ost/sp/profilem" + parts.path
            alt_url_profilem = urllib.parse.urlunsplit(
                (parts.scheme, parts.netloc, alt_path_profilem, parts.query, parts.fragment)
            )
            if alt_url_profilem not in urls_to_try:
                urls_to_try.append(alt_url_profilem)
        elif parts.path.startswith("/ost/PDF/"):
            alt_path_profilem = parts.path.replace("/ost/PDF/", "/ost/sp/profilem/PDF/", 1)
            alt_url_profilem = urllib.parse.urlunsplit(
                (parts.scheme, parts.netloc, alt_path_profilem, parts.query, parts.fragment)
            )
            if alt_url_profilem not in urls_to_try:
                urls_to_try.append(alt_url_profilem)
    except Exception:
        pass

    last_status = None
    last_content_type = None
    last_error: Exception | None = None
    for abs_url in urls_to_try:
        try:
            resp = await page.request.get(
                abs_url,
                headers={
                    "referer": page.url,
                    "accept": "application/pdf,*/*",
                },
            )
            last_status = getattr(resp, "status", None)
            if last_status != 200:
                logger.info("PDF candidate %s returned status %s", abs_url, last_status)
                continue

            data = await resp.body()
            if not data.startswith(b"%PDF"):
                try:
                    last_content_type = resp.headers.get("content-type")
                except Exception:
                    last_content_type = None
                logger.info("Candidate %s not a PDF (content-type=%s)", abs_url, last_content_type)
                continue

            filename = Path(abs_url).name or "download.pdf"
            try:
                cd = resp.headers.get("content-disposition")
                if cd and "filename=" in cd:
                    raw = cd.split("filename=", 1)[1].strip()
                    if raw.startswith('"') and '"' in raw[1:]:
                        raw = raw.split('"', 2)[1]
                    filename = raw or filename
            except Exception:
                pass

            out_path = results_dir / filename
            out_path.write_bytes(data)
            logger.info("Saved PDF via request to %s", out_path)

            # Try to extract creation date from PDF and rename file accordingly
            release_date = None
            final_path = out_path
            try:
                dt = extract_pdf_creation_date(data)
                if dt:
                    release_date = dt.date()
                    new_name = format_pdf_filename(dt)
                    new_path = out_path.with_name(new_name)
                    # Ensure unique filename
                    i = 1
                    while new_path.exists():
                        stem = new_name[:-4]
                        new_path = out_path.with_name(f"{stem}_{i}.pdf")
                        i += 1
                    out_path.rename(new_path)
                    final_path = new_path
                    logger.info("Renamed PDF to %s", new_path)
            except Exception:
                logger.exception("Failed to rename PDF to creation date")

            # Record the download in the DB for automation/traceability.
            try:
                record_path = final_path
                try:
                    record_path = final_path.relative_to(results_root.parent)
                except Exception:
                    pass
                await record_results_download(
                    ticker=ticker or "",
                    release_date=release_date,
                    pdf_path=record_path,
                    pdf_url=abs_url,
                    source="ost",
                    data=data,
                )
            except Exception:
                logger.exception("Failed to record results download for %s", safe_ticker)

            # Cleanup: remove older PDFs and news items in this ticker folder
            try:
                import shutil

                removed = []
                for child in results_dir.iterdir():
                    # Skip the file we just saved
                    try:
                        if child.samefile(final_path):
                            continue
                    except Exception:
                        # On some platforms samefile may fail for non-existing paths; fallback to name check
                        if child.resolve() == final_path.resolve():
                            continue

                    # Files to delete: PDFs, HTML/text/json news artifacts, or names that start with 'news'
                    if child.is_file():
                        low = child.suffix.lower()
                        if low == ".pdf" or low in {".html", ".htm", ".txt", ".json"} or child.name.lower().startswith("news"):
                            try:
                                child.unlink()
                                removed.append(child)
                            except Exception:
                                logger.exception("Failed to remove old artifact %s", child)
                    elif child.is_dir():
                        if child.name.lower().startswith("news"):
                            try:
                                shutil.rmtree(child)
                                removed.append(child)
                            except Exception:
                                logger.exception("Failed to remove news directory %s", child)

                if removed:
                    logger.info("Cleaned up %d old file(s)/dir(s) in %s: %s", len(removed), results_dir, removed)
            except Exception:
                logger.exception("Cleanup of older PDFs/news items failed")

            return True
        except Exception as ex:
            last_error = ex
            continue

    if last_error:
        logger.exception("Direct PDF download failed", exc_info=last_error)
    logger.warning("Failed to download first PDF (status=%s content-type=%s)", last_status, last_content_type)
    try:
        await dump_debug(page, debug_dir, f"pdf_download_failed_{safe_ticker}")
    except Exception:
        pass
    return False
