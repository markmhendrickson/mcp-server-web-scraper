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

try:
    from plugins.url_body_fetcher import fetch_url_body
except ImportError:
    from url_body_fetcher import fetch_url_body


def _wait_run(client: Any, run_id: str, sleep_fn: Any) -> None:
    """Poll run until terminal status."""
    while client.run(run_id).get()["status"] not in [
        "SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT",
    ]:
        sleep_fn(2)


def _get_run_items(client: Any, run: dict[str, Any]) -> list[dict[str, Any]]:
    """Return dataset items for a run."""
    return list(client.dataset(run["defaultDatasetId"]).iterate_items())


def _substitute_url(obj: Any, url: str) -> Any:
    """Replace __URL__ placeholder in dict/list/str with url."""
    if isinstance(obj, dict):
        return {k: _substitute_url(v, url) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_substitute_url(v, url) for v in obj]
    if isinstance(obj, str) and obj == "__URL__":
        return url
    return obj


# Phrases that indicate cookie/consent or error pages, not actual article content
_FAKE_CONTENT_PHRASES = (
    "did someone say … cookies?",
    "did someone say … cookies",
    "x and third parties integrated by x use cookies",
    "third parties integrated by x use cookies",
    "cookies to provide you with a better, safer and faster",
    "not supported",
    "javascript is not available",
    "enable javascript",
    "this page is not supported",
    "please visit the author's profile",
)


def _is_actual_article_content(body: str) -> bool:
    """True if body looks like real article content, not cookie/consent or error page."""
    if not body or len(body.strip()) < 80:
        return False
    lower = body.lower()
    for phrase in _FAKE_CONTENT_PHRASES:
        if phrase in lower:
            return False
    # If most of the body is cookie-like (very short and cookie-related), reject
    if len(body) < 400 and "cookies" in lower and "necessary" in lower:
        return False
    return True


def _article_item_usable(item: dict[str, Any]) -> bool:
    """True if Apify item has usable article body (tweet-like or website-content-crawler)."""
    body = (
        item.get("fullText") or item.get("text") or ""
    ) or (
        item.get("markdown") or item.get("content") or ""
    )
    if not body or len(body.strip()) < 50:
        return False
    if not _is_actual_article_content(body):
        return False
    return True


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
    # Remove trailing slash for consistent matching
    url = url.rstrip('/')
    # Match username after domain, before any additional path
    match = re.search(r"(?:twitter|x)\.com/(\w+)(?:/|$)", url)
    return match.group(1) if match else None


def is_profile_url(url: str) -> bool:
    """Check if URL is a profile URL (not a tweet)."""
    return (
        ("twitter.com/" in url or "x.com/" in url)
        and "/status/" not in url
    )


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
        """Extract tweet ID or username from Twitter URL."""
        if is_profile_url(url):
            # Profile URL - extract username
            username = extract_username(url)
            if not username:
                raise ValueError(f"Could not extract username from URL: {url}")
            return username
        else:
            # Tweet URL - extract tweet ID
            try:
                return extract_tweet_id(url)
            except ValueError as e:
                raise ValueError(f"Invalid Twitter URL: {e}")
    
    def scrape(
        self,
        url: str,
        method: str = "auto",
        credentials: dict[str, str | None] | None = None,
        max_tweets: int | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Scrape Twitter post using Apify."""
        # Check for apify-client at runtime (not just import time)
        try:
            from apify_client import ApifyClient
        except ImportError:
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
        
        # Use Apify's apidojo/tweet-scraper for both single tweets and profiles (try free actor first for profiles)
        client = ApifyClient(apify_token)
        
        print(f"Running Apify Twitter scraper for: {url}")
        
        # Check if it's a single tweet or user profile
        if is_profile_url(url):
            # User profile - scrape tweets (try free actor first, fallback to paid with optional max_tweets)
            tweet_limit = max_tweets if max_tweets is not None else 0  # 0 = all available
            print(f"Scraping tweets from profile: {url}" + (f" (max {tweet_limit})" if tweet_limit else ""))
            try:
                run = client.actor("coder_luffy/free-tweet-scraper").call(
                    run_input={"urls": [url]},
                    timeout_secs=600,
                )
            except Exception as e:
                print(f"Free actor failed, trying paid actor: {e}")
                run_input: dict[str, Any] = {"startUrls": [url]}
                if tweet_limit > 0:
                    run_input["maxItems"] = tweet_limit
                run = client.actor("apidojo/tweet-scraper").call(
                    run_input=run_input,
                    timeout_secs=600,
                )
        elif "/status/" in url:
            # Single tweet - same actor, one URL, max 1 item
            run = client.actor("apidojo/tweet-scraper").call(
                run_input={
                    "startUrls": [url],
                    "maxItems": 1,
                },
                timeout_secs=600,
            )
        else:
            raise ValueError(
                "Unsupported Twitter URL format. "
                "Use: https://twitter.com/username (profile) or "
                "https://twitter.com/username/status/TWEET_ID (single tweet)"
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
        
        # Return all items for profile URLs, single item for tweet URLs
        if is_profile_url(url):
            return {"tweets": items, "is_profile": True, "url": url}
        # Single tweet: fetch referenced X content via second Apify call(s).
        # Tweets: apidojo/tweet-scraper. Articles: try ARTICLE_ACTORS in order until one returns usable content.
        single = items[0]
        ref_urls = self._extract_outbound_urls(single, include_x_urls=True)
        x_refs: list[dict[str, Any]] = []
        for ref_url in ref_urls:
            if self._is_x_tweet_url(ref_url):
                # Tweet URL: single actor
                try:
                    run_ref = client.actor(self.ACTOR_TWEET).call(
                        run_input={"startUrls": [ref_url], "maxItems": 1},
                        timeout_secs=300,
                    )
                    _wait_run(client, run_ref["id"], sleep)
                    ref_items = _get_run_items(client, run_ref)
                    if ref_items:
                        x_refs.append({"url": ref_url, "data": ref_items[0]})
                    else:
                        x_refs.append({"url": ref_url, "error": "No data from Apify"})
                except Exception as e:
                    x_refs.append({"url": ref_url, "error": str(e)})
                continue
            if self._is_x_article_url(ref_url):
                # Article URL: try actors in order until one returns usable content
                got = False
                for actor_id, input_template in self.ARTICLE_ACTORS:
                    run_input = _substitute_url(input_template, ref_url)
                    try:
                        run_ref = client.actor(actor_id).call(
                            run_input=run_input,
                            timeout_secs=300,
                        )
                        _wait_run(client, run_ref["id"], sleep)
                        if client.run(run_ref["id"]).get()["status"] != "SUCCEEDED":
                            continue
                        ref_items = _get_run_items(client, run_ref)
                        if ref_items and _article_item_usable(ref_items[0]):
                            x_refs.append({"url": ref_url, "data": ref_items[0], "actor": actor_id})
                            got = True
                            break
                    except Exception as e:
                        # Log so we see which actors were tried; then try next
                        sys.stderr.write(f"[article] {actor_id} failed: {e}\n")
                        continue
                if not got:
                    x_refs.append({"url": ref_url, "error": "No article actor returned usable content"})
                continue
        single["_referenced_apify"] = x_refs
        return single
    
    def normalize_output(
        self,
        scraped_data: dict[str, Any],
        source_id: str,
    ) -> dict[str, Any] | list[dict[str, Any]]:
        """Normalize Twitter data to common format."""
        current_time = int(time.time())
        
        # Check if this is profile scraping (multiple tweets)
        if scraped_data.get("is_profile"):
            tweets = scraped_data.get("tweets", [])
            normalized_tweets = []
            
            for tweet in tweets:
                # Extract tweet ID from tweet data or URL
                tweet_id = tweet.get("id", "")
                if not tweet_id:
                    # Try to extract from URL
                    tweet_url = tweet.get("url", "")
                    if "/status/" in tweet_url:
                        try:
                            tweet_id = extract_tweet_id(tweet_url)
                        except ValueError:
                            tweet_id = f"unknown_{len(normalized_tweets)}"
                
                normalized_tweet = self._normalize_single_tweet(tweet, tweet_id, current_time)
                normalized_tweets.append(normalized_tweet)
            
            return normalized_tweets
        else:
            # Single tweet
            return self._normalize_single_tweet(scraped_data, source_id, current_time)
    
    @staticmethod
    def _is_x_or_twitter_url(url: str) -> bool:
        """True if URL is X/Twitter (tweet or article)."""
        return bool(
            re.search(r"(?:twitter|x)\.com/(?:\w+/status/\d+|i/article/\d+)", url)
        )

    @staticmethod
    def _is_x_tweet_url(url: str) -> bool:
        """True if URL is a tweet (/status/). Use apidojo/tweet-scraper."""
        return bool(re.search(r"(?:twitter|x)\.com/\w+/status/\d+", url))

    @staticmethod
    def _is_x_article_url(url: str) -> bool:
        """True if URL is an X long-form article (/i/article/). Use apidojo/twitter-scraper-lite."""
        return bool(re.search(r"(?:twitter|x)\.com/i/article/\d+", url))

    # Apify actors: tweet-scraper for tweets
    ACTOR_TWEET = "apidojo/tweet-scraper"
    # Article URL actors to try in order until one returns usable content (then fetch_url_body as final fallback)
    ARTICLE_ACTORS: list[tuple[str, dict[str, Any]]] = [
        ("apidojo/twitter-scraper-lite", {"startUrls": ["__URL__"], "maxItems": 1}),
        ("pratikdani/twitter-posts-scraper", {"startUrls": ["__URL__"]}),
        ("web.harvester/twitter-scraper", {"startUrls": ["__URL__"], "tweetsDesired": 1}),
        ("scrapier/twitter-x-scraper", {"startUrls": ["__URL__"], "maxTweets": 1}),
        ("xtdata/twitter-x-scraper", {"startUrls": ["__URL__"], "maxItems": 1}),
        ("apify/website-content-crawler", {"startUrls": [{"url": "__URL__"}], "maxCrawlDepth": 0, "maxCrawlPages": 1, "proxyConfiguration": {"useApifyProxy": True}}),
    ]

    def _extract_outbound_urls(
        self, tweet_data: dict[str, Any], max_urls: int = 5, include_x_urls: bool = True
    ) -> list[str]:
        """Extract outbound URLs from tweet for scraping referenced content."""
        urls: list[str] = []
        entities = tweet_data.get("entities") or {}
        for u in (entities.get("urls") or [])[: max_urls * 2]:
            if not isinstance(u, dict):
                continue
            expanded = (u.get("expanded_url") or u.get("url") or "").strip()
            if not expanded or expanded in urls:
                continue
            if not include_x_urls and self._is_x_or_twitter_url(expanded):
                continue
            urls.append(expanded)
            if len(urls) >= max_urls:
                break
        return urls

    def _extract_media_urls(self, tweet_data: dict[str, Any]) -> list[str]:
        """Extract media/image URLs from tweet data (Apify output)."""
        urls: list[str] = []
        # Direct images array
        images = tweet_data.get("images") or tweet_data.get("photos")
        if isinstance(images, list):
            for img in images:
                if isinstance(img, str) and img.startswith("http"):
                    urls.append(img)
                elif isinstance(img, dict) and img.get("url"):
                    urls.append(img["url"])
        # entities.media or media array with media_url_https
        media = tweet_data.get("media") or (
            (tweet_data.get("entities") or {}).get("media")
            if isinstance(tweet_data.get("entities"), dict)
            else None
        )
        if isinstance(media, list):
            for m in media:
                if isinstance(m, dict):
                    u = m.get("media_url_https") or m.get("url") or m.get("media_url")
                    if u and isinstance(u, str):
                        urls.append(u)
        return urls

    def _normalize_single_tweet(
        self,
        tweet_data: dict[str, Any],
        tweet_id: str,
        scraped_at: int,
    ) -> dict[str, Any]:
        """Normalize a single tweet to common format."""
        # Extract tweet fields from Apify format
        text = tweet_data.get("text", "")
        author = tweet_data.get("author", {})
        author_obj = author if isinstance(author, dict) else {}
        username = author_obj.get("userName", author_obj.get("username", "")) or str(author)
        created_at = tweet_data.get("createdAt", scraped_at)
        likes = tweet_data.get("likeCount", 0)
        retweets = tweet_data.get("retweetCount", 0)
        replies = tweet_data.get("replyCount", 0)
        quote_count = tweet_data.get("quoteCount", 0)
        bookmark_count = tweet_data.get("bookmarkCount", 0)
        is_reply = tweet_data.get("isReply", False)
        is_retweet = tweet_data.get("isRetweet", False)
        is_quote = tweet_data.get("isQuote", False)
        lang = tweet_data.get("lang", "")
        images = self._extract_media_urls(tweet_data)
        author_name = author_obj.get("name", "")
        author_profile = author_obj.get("profilePicture", "")

        out: dict[str, Any] = {
            "source": "twitter",
            "tweet_id": tweet_id,
            "username": username,
            "text": text,
            "created_at": created_at,
            "likes": likes,
            "retweets": retweets,
            "replies": replies,
            "quote_count": quote_count,
            "bookmark_count": bookmark_count,
            "is_reply": is_reply,
            "is_retweet": is_retweet,
            "is_quote": is_quote,
            "lang": lang,
            "images": images,
            "author_name": author_name,
            "author_profile_picture": author_profile,
            "url": tweet_data.get("url", ""),
            "scraped_at": scraped_at,
            "raw_data": tweet_data,  # Keep original for reference
        }

        # Always scrape referenced URLs / body content when present
        ref_urls = self._extract_outbound_urls(tweet_data)
        apify_refs = {r["url"]: r for r in (tweet_data.get("_referenced_apify") or [])}
        if ref_urls:
            referenced_content: list[dict[str, Any]] = []
            for ref_url in ref_urls:
                # Use second Apify result when we have it (X/twitter URLs)
                if ref_url in apify_refs:
                    ar = apify_refs[ref_url]
                    if "error" not in ar and ar.get("data"):
                        d = ar["data"]
                        # Tweet-like (Apify Twitter actors)
                        body = d.get("fullText") or d.get("text") or ""
                        author = d.get("author") or {}
                        title = author.get("name", "") if isinstance(author, dict) else ""
                        # Website-content-crawler (or similar) output
                        if not body:
                            body = d.get("markdown") or d.get("content") or d.get("text") or ""
                        if not title:
                            title = d.get("title") or d.get("metadata", {}).get("title", "") if isinstance(d.get("metadata"), dict) else ""
                        if _is_actual_article_content(body or ""):
                            referenced_content.append(
                                {"url": ref_url, "title": title or "", "body": body or ""}
                            )
                        else:
                            referenced_content.append({"url": ref_url, "error": "Only cookie/consent or error page retrieved"})
                    else:
                        # Apify failed (e.g. actor doesn't support /i/article/); fall back to URL fetch
                        try:
                            ref = fetch_url_body(ref_url)
                            if "error" not in ref:
                                body = ref.get("body", "")
                                if _is_actual_article_content(body or ""):
                                    referenced_content.append(
                                        {"url": ref_url, "title": ref.get("title", ""), "body": body}
                                    )
                                else:
                                    referenced_content.append({"url": ref_url, "error": "Only cookie/consent or error page retrieved"})
                            else:
                                referenced_content.append({"url": ref_url, "error": ref["error"]})
                        except Exception as e:
                            referenced_content.append({"url": ref_url, "error": str(e)})
                    continue
                # Non-X URL: fetch with requests/Playwright
                try:
                    ref = fetch_url_body(ref_url)
                    if "error" not in ref:
                        referenced_content.append(
                            {"url": ref_url, "title": ref.get("title", ""), "body": ref.get("body", "")}
                        )
                    else:
                        referenced_content.append({"url": ref_url, "error": ref["error"]})
                except Exception as e:
                    referenced_content.append({"url": ref_url, "error": str(e)})
            out["referenced_content"] = referenced_content

        return out

    def get_storage_path(self, source_id: str, data_dir: Path) -> Path:
        """Get storage path for Twitter post."""
        return data_dir / "imports" / "twitter" / f"tweet_{source_id}.json"
