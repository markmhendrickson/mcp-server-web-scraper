#!/usr/bin/env python3
"""
Save Playwright storage_state after you log in to ChatGPT in a headed browser.

Default output: <repo>/playwright/.auth/chatgpt_storage.json

Usage:
  cd mcp/web-scraper && . .venv/bin/activate
  python scripts/chatgpt_save_playwright_storage.py
  python scripts/chatgpt_save_playwright_storage.py /path/to/state.json
"""

import sys
from pathlib import Path

WEB_SCRAPER_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = WEB_SCRAPER_DIR.parent.parent
DEFAULT_STATE = REPO_ROOT / "playwright" / ".auth" / "chatgpt_storage.json"


def main() -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "Install Playwright in this venv: pip install playwright && playwright install chromium",
            file=sys.stderr,
        )
        sys.exit(1)

    out = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else DEFAULT_STATE
    out.parent.mkdir(parents=True, exist_ok=True)

    print("Opening headed Chromium. Log in to ChatGPT if prompted.", file=sys.stderr)
    print("When the main Chat UI loads, press Enter here to save session...", file=sys.stderr)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto("https://chatgpt.com/", wait_until="domcontentloaded", timeout=120000)
        input()
        context.storage_state(path=str(out))
        context.close()
        browser.close()

    print(f"Saved storage state to {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
