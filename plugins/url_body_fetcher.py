"""
Fetch main body content from arbitrary URLs.
Used to scrape referenced links (e.g. from tweets) so the scraper returns full context.
"""

import re
import subprocess
import sys
from pathlib import Path
from typing import Any

# Add parent for scraper utilities
sys.path.insert(0, str(Path(__file__).parent.parent))

REQUESTS_AVAILABLE = False
BEAUTIFULSOUP_AVAILABLE = False
PLAYWRIGHT_AVAILABLE = False

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    pass

try:
    from bs4 import BeautifulSoup
    BEAUTIFULSOUP_AVAILABLE = True
except ImportError:
    pass

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    pass


def _ensure_playwright() -> bool:
    try:
        __import__("playwright.sync_api")
        return True
    except ImportError:
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "playwright"],
                capture_output=True,
                check=True,
            )
            subprocess.run(
                [sys.executable, "-m", "playwright", "install", "chromium"],
                capture_output=True,
                check=True,
            )
            return True
        except Exception:
            return False


def _extract_body_soup(soup: Any) -> str:
    """Extract main text from BeautifulSoup, stripping nav/script/footer."""
    for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form"]):
        tag.decompose()
    body = soup.find("body") or soup
    # Prefer main/article for content
    main = body.find("main") or body.find("article") or body.find("div", role="main")
    if main:
        body = main
    text = body.get_text(separator="\n", strip=True)
    # Collapse multiple newlines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def fetch_url_body(
    url: str,
    timeout_requests: int = 25,
    timeout_playwright_ms: int = 30000,
    min_body_chars: int = 100,
) -> dict[str, Any]:
    """
    Fetch a URL and return its title and main body text.
    Tries requests+BeautifulSoup first; falls back to Playwright for JS-rendered pages.

    Returns:
        {"url": str, "title": str, "body": str} on success, or
        {"url": str, "error": str} on failure.
    """
    result: dict[str, Any] = {"url": url}

    # 1) Try requests + BeautifulSoup
    if REQUESTS_AVAILABLE and BEAUTIFULSOUP_AVAILABLE:
        try:
            import requests as req
            from bs4 import BeautifulSoup as BS

            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            r = req.get(url, headers=headers, timeout=timeout_requests)
            r.raise_for_status()
            soup = BS(r.text, "html.parser")
            title_tag = soup.find("title")
            title = (title_tag.get_text(strip=True) or "").strip() if title_tag else ""
            body = _extract_body_soup(soup)
            # Treat "enable JavaScript" / JS-required pages as insufficient (e.g. x.com articles)
            js_required = (
                "javascript is not available" in body.lower()
                or "enable javascript" in body.lower()
                or "javascript is disabled" in body.lower()
            )
            if len(body) >= min_body_chars and not js_required:
                result["title"] = title
                result["body"] = body
                return result
            # Body too short or JS-required page, fall through to Playwright
        except Exception as e:
            # Fall through to Playwright
            pass

    # 2) Playwright for JS-rendered or when requests didn't yield enough content
    if not PLAYWRIGHT_AVAILABLE:
        if not _ensure_playwright():
            result["error"] = "Playwright not available and requests yielded no content"
            return result
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            result["error"] = "Playwright install failed or import error"
            return result

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        result["error"] = "Playwright not installed"
        return result

    try:
        # x.com/twitter.com need more time and networkidle so JS-rendered content (e.g. articles) loads
        is_x = "x.com" in url or "twitter.com" in url
        wait_ms = min(45000, timeout_playwright_ms * 2) if is_x else timeout_playwright_ms
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=wait_ms)
            if is_x:
                try:
                    page.wait_for_load_state("networkidle", timeout=15000)
                except Exception:
                    pass
            else:
                page.wait_for_load_state("domcontentloaded")
            title = (page.title() or "").strip()
            # Prefer main/article, else full body
            body = ""
            for selector in ["main", "article", '[role="main"]', "body"]:
                try:
                    el = page.query_selector(selector)
                    if el:
                        body = el.inner_text()
                        break
                except Exception:
                    continue
            if not body:
                body = page.inner_text("body")
            body = re.sub(r"\n{3,}", "\n\n", body.strip())
            browser.close()
            result["title"] = title
            result["body"] = body
            return result
    except Exception as e:
        result["error"] = str(e)
        return result
