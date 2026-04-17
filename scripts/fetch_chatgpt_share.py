#!/usr/bin/env python3
"""Fetch a ChatGPT share or conversation URL and print or save export JSON. Loads .env from repo root."""

import argparse
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

DEFAULT_STORAGE = REPO_ROOT / "playwright" / ".auth" / "chatgpt_storage.json"


def _apify_eligible(url: str) -> bool:
    return "chatgpt.com/share/" in url


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape ChatGPT conversation to export JSON")
    parser.add_argument("url", nargs="?", default=os.getenv("CHATGPT_SHARE_URL"), help="ChatGPT URL")
    parser.add_argument(
        "-o",
        "--out",
        help="Write JSON to this file instead of stdout",
    )
    parser.add_argument("--skip-apify", action="store_true", help="Only use Playwright")
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Run Playwright with headless=False (often needed for Cloudflare)",
    )
    parser.add_argument(
        "--storage-state",
        metavar="PATH",
        help=f"Playwright storage state JSON (default: {DEFAULT_STORAGE} if that file exists)",
    )
    args = parser.parse_args()
    url = args.url
    if not url:
        parser.error("pass url or set CHATGPT_SHARE_URL")
    share_id = extract_share_id(url)
    print("Share ID:", share_id, file=sys.stderr)

    storage = args.storage_state
    if not storage and DEFAULT_STORAGE.is_file():
        storage = str(DEFAULT_STORAGE)

    out = None
    token = os.getenv("APIFY_API_TOKEN")
    if token and not args.skip_apify and _apify_eligible(url):
        try:
            out = scrape_with_apify(url, token)
        except Exception as e:
            print("Apify failed:", e, file=sys.stderr)
    elif token and not args.skip_apify and not _apify_eligible(url):
        print(
            "Skipping Apify: actor only accepts chatgpt.com/share/... links.",
            file=sys.stderr,
        )

    if not out:
        print("Trying Playwright...", file=sys.stderr)
        try:
            out = scrape_with_playwright(
                url,
                headless=not args.headed,
                storage_state_path=storage,
            )
        except Exception as e:
            print("Playwright failed:", e, file=sys.stderr)
    if not out:
        print("No content retrieved.", file=sys.stderr)
        sys.exit(1)
    export = convert_to_export_format(out, share_id)
    text = json.dumps(export, indent=2, ensure_ascii=False)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(args.out, file=sys.stderr)
    else:
        print(text)


if __name__ == "__main__":
    main()
