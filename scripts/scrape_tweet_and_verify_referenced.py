#!/usr/bin/env python3
"""One-off script to scrape a tweet and verify referenced_content is populated."""
import json
import os
import sys
from pathlib import Path

# Repo root and web-scraper dir
SCRIPT_DIR = Path(__file__).resolve().parent
WEB_SCRAPER_DIR = SCRIPT_DIR.parent
REPO_ROOT = WEB_SCRAPER_DIR.parent.parent
sys.path.insert(0, str(WEB_SCRAPER_DIR))

# Load .env from repo root
env_file = REPO_ROOT / ".env"
if env_file.exists():
    from dotenv import load_dotenv
    load_dotenv(env_file)

# Data dir: env DATA_DIR or WEB_SCRAPER_DATA_DIR, or repo data/tmp for test
data_dir = Path(
    os.environ.get("WEB_SCRAPER_DATA_DIR")
    or os.environ.get("DATA_DIR")
    or REPO_ROOT / "data" / "tmp"
)

from plugins.twitter_scraper import TwitterScraper

URL = "https://x.com/cdixon/status/2019837259575607401"

def main():
    scraper = TwitterScraper()
    if not scraper.can_handle(URL):
        print("Scraper cannot handle URL")
        return 1
    source_id = scraper.extract_id(URL)
    credentials = {"apify_token": os.environ.get("APIFY_API_TOKEN")}
    if not credentials.get("apify_token"):
        print("APIFY_API_TOKEN not set; cannot run Apify. Set env or add to .env")
        return 1
    print("Scraping tweet (Apify + referenced URL fetch)...")
    scraped_data = scraper.scrape(URL, method="apify", credentials=credentials)
    normalized = scraper.normalize_output(scraped_data, source_id)
    refs = normalized.get("referenced_content") or []
    print(f"referenced_content entries: {len(refs)}")
    if refs:
        for i, r in enumerate(refs):
            if "error" in r:
                print(f"  [{i}] {r['url'][:50]}... -> error: {r['error'][:60]}...")
            else:
                title = (r.get("title") or "")[:60]
                body_preview = (r.get("body") or "")[:120].replace("\n", " ")
                print(f"  [{i}] title: {title}")
                print(f"      body preview: {body_preview}...")
    else:
        print("No referenced_content (tweet may have no outbound links or fetch failed)")
    out_path = scraper.get_storage_path(source_id, data_dir)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(normalized, f, indent=2, ensure_ascii=False)
    print(f"Saved to {out_path}")
    return 0 if refs else 1

if __name__ == "__main__":
    sys.exit(main())
