"""
Registry for managing multiple scraper plugins.
"""

from typing import Type
from scraper_base import ScraperBase


class ScraperRegistry:
    """Registry for source-specific scrapers."""
    
    def __init__(self):
        self._scrapers: dict[str, ScraperBase] = {}
    
    def register(self, scraper: ScraperBase) -> None:
        """Register a scraper instance."""
        self._scrapers[scraper.source_name] = scraper
    
    def get_scraper(self, url: str) -> ScraperBase | None:
        """Get the appropriate scraper for a URL."""
        for scraper in self._scrapers.values():
            if scraper.can_handle(url):
                return scraper
        return None
    
    def get_scraper_by_name(self, source_name: str) -> ScraperBase | None:
        """Get a scraper by source name."""
        return self._scrapers.get(source_name)
    
    def list_sources(self) -> list[str]:
        """List all registered source names."""
        return list(self._scrapers.keys())
