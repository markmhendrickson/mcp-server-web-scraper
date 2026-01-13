"""
X/Twitter scraper plugin using Apify.
"""

import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

# Try to import apify-client
APIFY_AVAILABLE = False
try:
    from apify_client import ApifyClient
    APIFY_AVAILABLE = True
except ImportError:
    pass

# Try to import 1Password credentials utility
CREDENTIALS_AVAILABLE = False
try:
    server_dir = Path(__file__).parent.parent
    possible_paths = [
        server_dir.parent.parent,  # mcp/web-scraper -> mcp -> personal
    ]
    
    for parent_path in possible_paths:
        credentials_path = parent_path / "execution" / "scripts" / "credentials.py"
        if credentials_path.exists():
            sys.path.insert(0, str(parent_path))
            try:
                from execution.scripts.credentials import get_credential
                CREDENTIALS_AVAILABLE = True
                break
            except ImportError:
                continue
except Exception:
    pass

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from scraper_base import ScraperBase


def get_apify_token_from_1password() -> str | None:
    """Get Apify API token from 1Password."""
    if not CREDENTIALS_AVAILABLE:
        return None
    
    try:
        from execution.scripts.credentials import get_credential
        
        # Try to get API token from 1Password item "Apify"
        token = get_credential("Apify", vault="Private", field="API token")
        if token:
            return token
        
        # Try other field name variations
        for field_name in ["api_token", "token", "API key", "apify_token"]:
            try:
                token = get_credential("Apify", vault="Private", field=field_name)
                if token:
                    return token
            except (ValueError, KeyError):
                continue
        
        return None
    except Exception as e:
        print(f"Warning: Could not get Apify token from 1Password: {e}")
        return None


def extract_tweet_id(url: str) -> str:
    """Extract tweet ID from X/Twitter URL."""
    # Support formats:
    # https://twitter.com/username/status/1234567890
    # https://x.com/username/status/1234567890
    # https://twitter.com/username/status/1234567890?s=20
    match = re.search(r"/(?:twitter|x)\.com/\w+/status/(\d+)", url)
    if not match:
        raise ValueError(f"Invalid X/Twitter URL format: {url}")
    return match.group(1)


def extract_username(url: str) -> str | None:
    """Extract username from X/Twitter URL."""
    match = re.search(r"/(?:twitter|x)\.com/(\w+)/", url)
    return match.group(1) if match else None


class TwitterScraper(ScraperBase):
    """Scraper for X/Twitter posts using Apify."""
    
    @property
    def source_name(self) -> str:
        return "twitter"
    
    @property
    def supported_methods(self) -> list[str]:
        return ["apify"]  # Apify is the primary method for Twitter
    
    def can_handle(self, url: str) -> bool:
        """Check if URL is a Twitter/X URL."""
        return (
            "twitter.com/" in url
            or "x.com/" in url
        )
    
    def extract_id(self, url: str) -> str:
        """Extract tweet ID from Twitter URL."""
        try:
            return extract_tweet_id(url)
        except ValueError as e:
            raise ValueError(f"Invalid Twitter URL: {e}")
    
    def scrape(
        self,
        url: str,
        method: str = "auto",
        credentials: dict[str, str | None] | None = None,
    ) -> dict[str, Any]:
        """Scrape Twitter post using Apify."""
        if not APIFY_AVAILABLE:
            raise ImportError(
                "apify-client not installed. Install with: pip install apify-client"
            )
        
        if credentials is None:
            credentials = {}
        
        # Get Apify token
        apify_token = credentials.get("apify_token")
        if not apify_token:
            apify_token = os.getenv("APIFY_API_TOKEN")
        
        if not apify_token:
            apify_token = get_apify_token_from_1password()
        
        if not apify_token:
            raise ValueError(
                "APIFY_API_TOKEN required. Set env var, pass in credentials, "
                "or configure in 1Password item 'Apify' with field 'API token'"
            )
        
        # Use Apify's Twitter Scraper actor
        # Actor ID: apify/twitter-scraper
        client = ApifyClient(apify_token)
        
        print(f"Running Apify Twitter scraper for: {url}")
        
        # Check if it's a single tweet or user profile
        if "/status/" in url:
            # Single tweet
            run = client.actor("apify/twitter-scraper").call(
                run_input={
                    "startUrls": [{"url": url}],
                    "addUserInfo": False,
                    "tweetsDesired": 1,
                },
                timeout_secs=300,
            )
        else:
            # User profile or search - not supported in this version
            raise ValueError(
                "Only single tweet URLs are supported. "
                "Use format: https://twitter.com/username/status/TWEET_ID"
            )
        
        # Wait for run to finish
        from time import sleep
        
        while client.run(run["id"]).get()["status"] not in [
            "SUCCEEDED",
            "FAILED",
            "ABORTED",
            "TIMED-OUT",
        ]:
            sleep(2)
        
        run_info = client.run(run["id"]).get()
        if run_info["status"] != "SUCCEEDED":
            raise ValueError(f"Apify run failed with status: {run_info['status']}")
        
        # Fetch results
        items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
        
        if not items:
            raise ValueError("No tweet data extracted by Apify")
        
        # Return first item (should be the tweet)
        return items[0]
    
    def normalize_output(
        self,
        scraped_data: dict[str, Any],
        source_id: str,
    ) -> dict[str, Any]:
        """Normalize Twitter data to common format."""
        # Apify returns tweet data in their format
        # Normalize to a common structure
        current_time = int(time.time())
        
        # Extract tweet fields from Apify format
        text = scraped_data.get("text", "")
        author = scraped_data.get("author", {})
        username = author.get("username", "") if isinstance(author, dict) else str(author)
        created_at = scraped_data.get("createdAt", current_time)
        likes = scraped_data.get("likeCount", 0)
        retweets = scraped_data.get("retweetCount", 0)
        replies = scraped_data.get("replyCount", 0)
        
        return {
            "source": "twitter",
            "tweet_id": source_id,
            "username": username,
            "text": text,
            "created_at": created_at,
            "likes": likes,
            "retweets": retweets,
            "replies": replies,
            "url": scraped_data.get("url", ""),
            "scraped_at": current_time,
            "raw_data": scraped_data,  # Keep original for reference
        }
    
    def get_storage_path(self, source_id: str, data_dir: Path) -> Path:
        """Get storage path for Twitter post."""
        return data_dir / "imports" / "twitter" / f"tweet_{source_id}.json"
