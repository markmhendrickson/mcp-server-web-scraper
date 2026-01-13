"""
ChatGPT scraper plugin.

Reuses logic from the original ChatGPT scraper.
"""

import sys
from pathlib import Path
from typing import Any

import sys
from pathlib import Path
from typing import Any

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import from scraper.py in parent directory
try:
    from scraper import (
        scrape_with_playwright,
        scrape_with_apify,
        scrape_with_requests,
        extract_share_id,
        convert_to_export_format,
        get_apify_token_from_1password,
    )
except ImportError as e:
    raise ImportError(
        f"Could not import ChatGPT scraper functions: {e}. "
        "Ensure scraper.py is in the parent directory."
    )

from scraper_base import ScraperBase


class ChatGPTScraper(ScraperBase):
    """Scraper for ChatGPT conversations."""
    
    @property
    def source_name(self) -> str:
        return "chatgpt"
    
    @property
    def supported_methods(self) -> list[str]:
        return ["playwright", "apify", "requests"]
    
    def can_handle(self, url: str) -> bool:
        """Check if URL is a ChatGPT share URL."""
        return (
            "chatgpt.com/share/" in url
            or "chatgpt.com/c/" in url
            or "chat.openai.com/share/" in url
        )
    
    def extract_id(self, url: str) -> str:
        """Extract share ID from ChatGPT URL."""
        try:
            return extract_share_id(url)
        except ValueError as e:
            raise ValueError(f"Invalid ChatGPT URL: {e}")
    
    def scrape(
        self,
        url: str,
        method: str = "auto",
        credentials: dict[str, str | None] | None = None,
    ) -> dict[str, Any]:
        """Scrape ChatGPT conversation."""
        if credentials is None:
            credentials = {}
        
        # Get Apify token
        apify_token = credentials.get("apify_token")
        if not apify_token:
            apify_token = get_apify_token_from_1password()
        
        # Determine methods to try
        methods_to_try = []
        if method == "auto":
            methods_to_try = ["playwright", "apify", "requests"]
        else:
            methods_to_try = [method]
        
        errors = []
        for scrape_method in methods_to_try:
            try:
                if scrape_method == "playwright":
                    return scrape_with_playwright(url)
                elif scrape_method == "apify":
                    if not apify_token:
                        errors.append("apify: APIFY_API_TOKEN required")
                        continue
                    return scrape_with_apify(url, apify_token)
                elif scrape_method == "requests":
                    return scrape_with_requests(url)
            except Exception as e:
                errors.append(f"{scrape_method}: {str(e)}")
                continue
        
        raise ValueError(f"All scraping methods failed: {errors}")
    
    def normalize_output(
        self,
        scraped_data: dict[str, Any],
        source_id: str,
    ) -> dict[str, Any]:
        """Normalize ChatGPT data to export format."""
        return convert_to_export_format(scraped_data, source_id)
    
    def get_storage_path(self, source_id: str, data_dir: Path) -> Path:
        """Get storage path for ChatGPT conversation."""
        return data_dir / "imports" / "chatgpt" / f"share_{source_id}.json"
