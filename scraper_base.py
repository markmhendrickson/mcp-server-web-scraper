"""
Base scraper interface for all source-specific scrapers.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class ScraperBase(ABC):
    """Base class for all source-specific scrapers."""
    
    @property
    @abstractmethod
    def source_name(self) -> str:
        """Return the name of the source (e.g., 'chatgpt', 'twitter', 'x')."""
        pass
    
    @property
    @abstractmethod
    def supported_methods(self) -> list[str]:
        """Return list of supported scraping methods (e.g., ['playwright', 'apify', 'requests'])."""
        pass
    
    @abstractmethod
    def can_handle(self, url: str) -> bool:
        """Check if this scraper can handle the given URL."""
        pass
    
    @abstractmethod
    def extract_id(self, url: str) -> str:
        """Extract a unique identifier from the URL."""
        pass
    
    @abstractmethod
    def scrape(
        self,
        url: str,
        method: str = "auto",
        credentials: dict[str, str | None] | None = None,
    ) -> dict[str, Any]:
        """
        Scrape content from the URL.
        
        Args:
            url: URL to scrape
            method: Scraping method to use ('auto', 'playwright', 'apify', 'requests')
            credentials: Optional credentials dict (e.g., {'apify_token': '...'})
            
        Returns:
            Dictionary with scraped data (structure varies by source)
            
        Raises:
            ValueError: If URL cannot be handled or scraping fails
        """
        pass
    
    @abstractmethod
    def normalize_output(
        self,
        scraped_data: dict[str, Any],
        source_id: str,
    ) -> dict[str, Any]:
        """
        Normalize scraped data to a common format.
        
        Args:
            scraped_data: Raw scraped data from scrape() method
            source_id: Unique identifier extracted from URL
            
        Returns:
            Normalized data structure
        """
        pass
    
    @abstractmethod
    def get_storage_path(self, source_id: str, data_dir: Path) -> Path:
        """
        Get storage path for scraped content.
        
        Args:
            source_id: Unique identifier extracted from URL
            data_dir: Base data directory
            
        Returns:
            Path where scraped content should be saved
        """
        pass
