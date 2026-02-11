"""
Pytest configuration for web-scraper MCP server tests.
"""
import sys
from pathlib import Path

import pytest

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def sample_chatgpt_url():
    """Sample ChatGPT share URL."""
    return "https://chatgpt.com/share/abc123"


@pytest.fixture
def sample_twitter_url():
    """Sample Twitter/X URL."""
    return "https://twitter.com/user/status/1234567890"


@pytest.fixture
def sample_spotify_url():
    """Sample Spotify playlist URL."""
    return "https://open.spotify.com/playlist/PLAYLIST_ID"


@pytest.fixture
def mock_scraped_content():
    """Sample scraped content structure."""
    return {
        "source": "chatgpt",
        "id": "abc123",
        "title": "Test Conversation",
        "content": "Test content",
        "timestamp": "2025-01-23T12:00:00Z"
    }
