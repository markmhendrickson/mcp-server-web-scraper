"""Tests for the optional Xquik Twitter scraping method."""

from __future__ import annotations

import pytest

from plugins.twitter_scraper import TwitterScraper


class FakeResponse:
    """Small response stub for Xquik request tests."""

    def __init__(self, payload: dict, status_code: int = 200):
        self.payload = payload
        self.status_code = status_code

    def json(self) -> dict:
        """Return the stubbed JSON payload."""
        return self.payload


def test_xquik_single_tweet_lookup(monkeypatch):
    """Xquik single-tweet reads normalize into the existing Twitter shape."""
    calls = []

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append(
            {"url": url, "params": params, "headers": headers, "timeout": timeout}
        )
        return FakeResponse(
            {
                "tweet": {
                    "id": "1234567890",
                    "text": "Launch note",
                    "createdAt": "2026-06-06T12:00:00Z",
                    "likeCount": 42,
                    "retweetCount": 5,
                    "replyCount": 3,
                    "quoteCount": 1,
                    "bookmarkCount": 2,
                    "media": [
                        {
                            "mediaUrl": "https://pbs.twimg.com/media/example.jpg",
                            "type": "photo",
                        }
                    ],
                },
                "author": {
                    "username": "xquikcom",
                    "profilePicture": "https://example.com/avatar.jpg",
                },
            }
        )

    monkeypatch.setattr("plugins.twitter_scraper.requests.get", fake_get)

    scraper = TwitterScraper()
    raw = scraper.scrape(
        "https://x.com/xquikcom/status/1234567890",
        method="xquik",
        credentials={
            "xquik_api_key": "test-key",
            "xquik_base_url": "https://api.example.test/v1",
        },
    )
    normalized = scraper.normalize_output(raw, "1234567890")

    assert calls == [
        {
            "url": "https://api.example.test/v1/x/tweets/1234567890",
            "params": None,
            "headers": {"x-api-key": "test-key"},
            "timeout": 30,
        }
    ]
    assert normalized["tweet_id"] == "1234567890"
    assert normalized["username"] == "xquikcom"
    assert normalized["text"] == "Launch note"
    assert normalized["likes"] == 42
    assert normalized["images"] == ["https://pbs.twimg.com/media/example.jpg"]


def test_xquik_profile_search_uses_author_filter(monkeypatch):
    """Xquik profile reads use documented search parameters."""
    calls = []

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append(
            {"url": url, "params": params, "headers": headers, "timeout": timeout}
        )
        return FakeResponse(
            {
                "tweets": [
                    {
                        "id": "111",
                        "text": "First",
                        "author": {"username": "xquikcom"},
                    },
                    {
                        "id": "222",
                        "text": "Second",
                        "author": {"username": "xquikcom"},
                    },
                ]
            }
        )

    monkeypatch.setattr("plugins.twitter_scraper.requests.get", fake_get)

    scraper = TwitterScraper()
    raw = scraper.scrape(
        "https://x.com/xquikcom",
        method="xquik",
        credentials={
            "xquik_api_key": "test-key",
            "xquik_base_url": "https://api.example.test/v1",
        },
        max_tweets=2,
    )
    normalized = scraper.normalize_output(raw, "xquikcom")

    assert calls[0]["url"] == "https://api.example.test/v1/x/tweets/search"
    assert calls[0]["params"] == {
        "q": "from:xquikcom",
        "fromUser": "xquikcom",
        "queryType": "Latest",
        "limit": 2,
    }
    assert len(normalized) == 2
    assert normalized[0]["tweet_id"] == "111"
    assert normalized[1]["text"] == "Second"


def test_xquik_method_requires_api_key(monkeypatch):
    """The opt-in Xquik method fails clearly without credentials."""
    monkeypatch.delenv("XQUIK_API_KEY", raising=False)

    scraper = TwitterScraper()

    with pytest.raises(ValueError, match="XQUIK_API_KEY required"):
        scraper.scrape("https://x.com/xquikcom/status/1234567890", method="xquik")


def test_apify_remains_primary_twitter_method():
    """The optional Xquik method does not replace Apify as the default."""
    scraper = TwitterScraper()

    assert scraper.supported_methods[0] == "apify"
    assert "xquik" in scraper.supported_methods
