"""
Claude share scraper plugin.
"""

import os
import re
import sys
import time
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from scraper_base import ScraperBase


def _extract_message_blocks(text: str, max_blocks: int = 200) -> list[dict[str, Any]]:
    """Convert free-form transcript text into message-like blocks."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    blocks: list[str] = []
    seen = set()

    for line in lines:
        if len(line) < 24:
            continue
        low = line.lower()
        if any(
            marker in low
            for marker in (
                "performing security verification",
                "this website uses a security service",
                "ray id:",
                "privacy",
                "terms",
                "just a moment",
            )
        ):
            continue
        key = line[:160]
        if key in seen:
            continue
        seen.add(key)
        blocks.append(line)
        if len(blocks) >= max_blocks:
            break

    return [
        {
            "role": "user" if i % 2 == 0 else "assistant",
            "text": block,
            "index": i,
        }
        for i, block in enumerate(blocks)
    ]


def _is_cloudflare_gate(title: str, body_text: str) -> bool:
    low_title = (title or "").lower()
    low_body = (body_text or "").lower()
    return (
        "just a moment" in low_title
        or "security verification" in low_body
        or "cloudflare" in low_body
    )


def _run_apify_crawl(url: str, api_token: str) -> dict[str, Any]:
    """Use Apify actor to crawl Claude share page and return normalized text payload."""
    try:
        from apify_client import ApifyClient
    except ImportError as exc:
        raise ImportError(
            "apify-client is required for method='apify'. Install with: pip install apify-client"
        ) from exc

    actor_id = os.getenv("CLAUDE_APIFY_ACTOR_ID", "apify/website-content-crawler")
    client = ApifyClient(api_token)

    run = client.actor(actor_id).call(
        run_input={
            "startUrls": [{"url": url}],
            "maxCrawlDepth": 0,
            "maxCrawlPages": 1,
            "proxyConfiguration": {"useApifyProxy": True},
        },
        timeout_secs=300,
    )

    while client.run(run["id"]).get()["status"] not in [
        "SUCCEEDED",
        "FAILED",
        "ABORTED",
        "TIMED-OUT",
    ]:
        time.sleep(2)

    run_info = client.run(run["id"]).get()
    if run_info["status"] != "SUCCEEDED":
        raise ValueError(f"Apify run failed with status: {run_info['status']}")

    items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
    if not items:
        raise ValueError("Apify returned no items for Claude share URL")

    first = items[0]
    body = first.get("markdown") or first.get("text") or first.get("content") or ""
    title = first.get("title") or "Claude shared conversation"

    if _is_cloudflare_gate(title, body):
        raise ValueError("Apify result appears blocked by Cloudflare challenge")

    return {"title": title, "messages": _extract_message_blocks(body), "raw_data": first}


def _scrape_with_playwright(url: str) -> dict[str, Any]:
    """Scrape Claude share using Playwright page text extraction."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise ImportError(
            "playwright is required for method='playwright'. Install with: pip install playwright && playwright install chromium"
        ) from exc

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)
        page.wait_for_load_state("networkidle", timeout=10000)

        title = page.title()
        body_text = page.locator("body").inner_text()
        browser.close()

    if _is_cloudflare_gate(title, body_text):
        raise ValueError("Claude share page blocked by Cloudflare challenge")

    messages = _extract_message_blocks(body_text)
    if not messages:
        raise ValueError("No conversation text found on Claude share page")

    return {"title": title or "Claude shared conversation", "messages": messages}


def _scrape_with_requests(url: str) -> dict[str, Any]:
    """Scrape Claude share using requests + BeautifulSoup."""
    response = requests.get(
        url,
        timeout=30,
        headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    title = soup.title.text.strip() if soup.title else "Claude shared conversation"
    body_text = soup.get_text("\n", strip=True)

    if _is_cloudflare_gate(title, body_text):
        raise ValueError("Claude share page blocked by Cloudflare challenge")

    messages = _extract_message_blocks(body_text)
    if not messages:
        raise ValueError("No conversation text found in HTTP response")

    return {"title": title, "messages": messages}


class ClaudeScraper(ScraperBase):
    """Scraper for Claude shared conversations."""

    @property
    def source_name(self) -> str:
        return "claude"

    @property
    def supported_methods(self) -> list[str]:
        return ["apify", "playwright", "requests"]

    def can_handle(self, url: str) -> bool:
        return "claude.ai/share/" in url

    def extract_id(self, url: str) -> str:
        match = re.search(r"claude\.ai/share/([a-zA-Z0-9-]+)", url)
        if not match:
            raise ValueError(f"Invalid Claude share URL format: {url}")
        return match.group(1)

    def scrape(
        self,
        url: str,
        method: str = "auto",
        credentials: dict[str, str | None] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        if credentials is None:
            credentials = {}

        apify_token = credentials.get("apify_token") or os.getenv("APIFY_API_TOKEN")

        methods = (
            ["apify", "playwright", "requests"]
            if method == "auto"
            else [method.lower().strip()]
        )

        errors: list[str] = []
        for scrape_method in methods:
            try:
                if scrape_method == "apify":
                    if not apify_token:
                        raise ValueError("APIFY_API_TOKEN required for Claude Apify scraping")
                    result = _run_apify_crawl(url, apify_token)
                elif scrape_method == "playwright":
                    result = _scrape_with_playwright(url)
                elif scrape_method == "requests":
                    result = _scrape_with_requests(url)
                else:
                    raise ValueError(f"Unsupported scraping method for Claude: {scrape_method}")

                result["url"] = url
                result["method_used"] = scrape_method
                return result
            except Exception as exc:
                errors.append(f"{scrape_method}: {exc}")

        raise ValueError(f"All Claude scraping methods failed: {errors}")

    def normalize_output(
        self,
        scraped_data: dict[str, Any],
        source_id: str,
    ) -> dict[str, Any]:
        return {
            "source": "claude",
            "share_id": source_id,
            "title": scraped_data.get("title", "Claude shared conversation"),
            "url": scraped_data.get("url", ""),
            "messages": scraped_data.get("messages", []),
            "method_used": scraped_data.get("method_used", ""),
            "raw_data": scraped_data.get("raw_data", {}),
            "scraped_at": int(time.time()),
        }

    def get_storage_path(self, source_id: str, data_dir: Path) -> Path:
        return data_dir / "imports" / "claude" / f"share_{source_id}.json"
