#!/usr/bin/env python3
"""One-off: fetch a ChatGPT share URL and print JSON. Loads .env from repo root."""

import json
import os
import sys
from pathlib import Path

# Repo root: scripts/ -> web-scraper -> mcp -> ateles
WEB_SCRAPER_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = WEB_SCRAPER_DIR.parent.parent
sys.path.insert(0, str(WEB_SCRAPER_DIR))

# Load .env from repo root
env_file = REPO_ROOT / ".env"
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip("'\""))

from scraper import (
    scrape_with_apify,
    scrape_with_playwright,
    extract_share_id,
    convert_to_export_format,
)


def main():
    url = os.getenv("CHATGPT_SHARE_URL")
    if len(sys.argv) > 1:
        url = sys.argv[1]
    if not url:
        print("Usage: fetch_chatgpt_share.py <chatgpt share url>", file=sys.stderr)
        print("  or set CHATGPT_SHARE_URL in env", file=sys.stderr)
        sys.exit(2)
    share_id = extract_share_id(url)
    print("Share ID:", share_id, file=sys.stderr)
    token = os.getenv("APIFY_API_TOKEN")
    out = None
    if token:
        try:
            out = scrape_with_apify(url, token)
        except Exception as e:
            print("Apify failed:", e, file=sys.stderr)
    if not out:
        print("Trying Playwright...", file=sys.stderr)
        try:
            out = scrape_with_playwright(url)
        except Exception as e:
            print("Playwright failed:", e, file=sys.stderr)
    if not out:
        print("No content retrieved.", file=sys.stderr)
        sys.exit(1)
    export = convert_to_export_format(out, share_id)
    print(json.dumps(export, indent=2))


if __name__ == "__main__":
    main()
