#!/usr/bin/env python3
"""
MCP Server for General-Purpose Web Scraping

Supports multiple sources (ChatGPT, X/Twitter, etc.) via plugin architecture.
Uses multiple scraping methods: Playwright, Apify, requests.
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

# Add current directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

# Import scraper registry and plugins
from scraper_registry import ScraperRegistry
from plugins.chatgpt_scraper import ChatGPTScraper
from plugins.twitter_scraper import TwitterScraper
from plugins.spotify_scraper import SpotifyScraper

# Configuration directory
CONFIG_DIR = Path.home() / ".config" / "web-scraper"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
ENV_FILE = CONFIG_DIR / ".env"

# Local .env file (in repo directory, for development)
SERVER_DIR = Path(__file__).parent
LOCAL_ENV_FILE = SERVER_DIR / ".env"

# Initialize MCP server
app = Server("web-scraper")

# Initialize scraper registry
registry = ScraperRegistry()

# Register scrapers
try:
    registry.register(ChatGPTScraper())
except Exception as e:
    print(f"Warning: Could not register ChatGPT scraper: {e}", file=sys.stderr)

try:
    registry.register(TwitterScraper())
except Exception as e:
    print(f"Warning: Could not register Twitter scraper: {e}", file=sys.stderr)

try:
    registry.register(SpotifyScraper())
except Exception as e:
    print(f"Warning: Could not register Spotify scraper: {e}", file=sys.stderr)


def load_credentials_from_env() -> dict[str, str | None]:
    """Load credentials from environment variables or .env file."""
    credentials = {
        "apify_token": os.getenv("APIFY_API_TOKEN"),
        "data_dir": os.getenv("DATA_DIR"),
    }

    # Helper function to load from .env file
    def load_from_file(env_file: Path) -> None:
        if not env_file.exists():
            return
        try:
            with open(env_file) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if line.startswith("APIFY_API_TOKEN="):
                        if not credentials["apify_token"]:
                            credentials["apify_token"] = (
                                line.split("=", 1)[1].strip().strip("\"'")
                            )
                    elif line.startswith("DATA_DIR="):
                        if not credentials["data_dir"]:
                            credentials["data_dir"] = (
                                line.split("=", 1)[1].strip().strip("\"'")
                            )
        except Exception:
            pass

    # Priority: environment variables > local .env > config directory .env
    if not credentials["apify_token"] or not credentials["data_dir"]:
        load_from_file(LOCAL_ENV_FILE)
        if not credentials["apify_token"] or not credentials["data_dir"]:
            load_from_file(ENV_FILE)

    return credentials


def get_data_dir() -> Path:
    """Get data directory for storing scraped content."""
    credentials = load_credentials_from_env()
    
    # Try DATA_DIR from credentials
    if credentials.get("data_dir"):
        data_dir = Path(credentials["data_dir"])
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir
    
    # Try to import config module from parent repo
    try:
        server_dir = Path(__file__).parent
        possible_paths = [
            server_dir.parent.parent,  # mcp/web-scraper -> mcp -> personal
        ]
        
        for parent_path in possible_paths:
            config_path = parent_path / "config.py"
            if config_path.exists():
                sys.path.insert(0, str(parent_path))
                try:
                    from config import get_data_dir as _get_data_dir
                    return _get_data_dir()
                except ImportError:
                    continue
    except Exception:
        pass
    
    # Fallback to config directory
    scraped_dir = CONFIG_DIR / "scraped"
    scraped_dir.mkdir(parents=True, exist_ok=True)
    return scraped_dir


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools."""
    sources = registry.list_sources()
    
    return [
        Tool(
            name="scrape_content",
            description=(
                f"Scrape content from supported sources. "
                f"Currently supports: {', '.join(sources)}. "
                f"Automatically detects source from URL. "
                f"Supports multiple methods: Playwright, Apify, requests."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": (
                            "URL to scrape. Supported formats:\n"
                            "- ChatGPT: https://chatgpt.com/share/abc-123 or https://chatgpt.com/c/abc-123\n"
                            "- Twitter/X (single tweet): https://twitter.com/username/status/1234567890 or https://x.com/username/status/1234567890\n"
                            "- Twitter/X (account profile - scrapes all tweets): https://twitter.com/username or https://x.com/username\n"
                            "- Spotify (playlist): https://open.spotify.com/playlist/PLAYLIST_ID"
                        )
                    },
                    "method": {
                        "type": "string",
                        "enum": ["auto", "playwright", "apify", "requests"],
                        "description": (
                            "Scraping method to use. 'auto' tries methods in order until one succeeds. "
                            "Default: auto"
                        ),
                        "default": "auto"
                    },
                    "output_path": {
                        "type": "string",
                        "description": (
                            "Optional: Custom output file path. "
                            "If not provided, saves to $DATA_DIR/imports/{source}/{id}.json"
                        )
                    }
                },
                "required": ["url"]
            }
        ),
        Tool(
            name="list_scraped_content",
            description="List previously scraped content from the data directory",
            inputSchema={
                "type": "object",
                "properties": {
                    "source": {
                        "type": "string",
                        "description": f"Filter by source. Options: {', '.join(sources)} or 'all' for all sources. Default: all",
                        "default": "all"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of items to return. Default: 50",
                        "default": 50
                    },
                    "sort_by": {
                        "type": "string",
                        "enum": ["date", "source"],
                        "description": "Sort order. Default: date",
                        "default": "date"
                    }
                }
            }
        ),
        Tool(
            name="get_scraped_content",
            description="Get details about specific scraped content",
            inputSchema={
                "type": "object",
                "properties": {
                    "source": {
                        "type": "string",
                        "enum": sources,
                        "description": f"Source type. Options: {', '.join(sources)}"
                    },
                    "content_id": {
                        "type": "string",
                        "description": "Content ID (e.g., share ID for ChatGPT, tweet ID for Twitter, playlist ID for Spotify)"
                    }
                },
                "required": ["source", "content_id"]
            }
        ),
        Tool(
            name="list_supported_sources",
            description="List all supported scraping sources",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """Handle tool calls."""
    if name == "scrape_content":
        return await handle_scrape_content(arguments)
    elif name == "list_scraped_content":
        return await handle_list_content(arguments)
    elif name == "get_scraped_content":
        return await handle_get_content(arguments)
    elif name == "list_supported_sources":
        return await handle_list_sources(arguments)
    
    raise ValueError(f"Unknown tool: {name}")


async def handle_scrape_content(args: dict) -> list[TextContent]:
    """Handle scrape_content tool call."""
    try:
        url = args.get("url")
        method = args.get("method", "auto")
        output_path = args.get("output_path")
        
        if not url:
            return [TextContent(
                type="text",
                text=json.dumps({"error": "URL is required"}, indent=2)
            )]
        
        # Find appropriate scraper
        scraper = registry.get_scraper(url)
        if not scraper:
            return [TextContent(
                type="text",
                text=json.dumps({
                    "error": f"Unsupported URL. Supported sources: {', '.join(registry.list_sources())}",
                    "url": url
                }, indent=2)
            )]
        
        # Extract source ID
        try:
            source_id = scraper.extract_id(url)
        except ValueError as e:
            return [TextContent(
                type="text",
                text=json.dumps({"error": str(e)}, indent=2)
            )]
        
        # Determine output path
        if output_path:
            output_file = Path(output_path)
        else:
            data_dir = get_data_dir()
            output_file = scraper.get_storage_path(source_id, data_dir)
        
        # Get credentials
        credentials = load_credentials_from_env()
        
        # Scrape content
        try:
            scraped_data = scraper.scrape(url, method=method, credentials=credentials)
        except Exception as e:
            return [TextContent(
                type="text",
                text=json.dumps({
                    "error": f"Scraping failed: {str(e)}",
                    "source": scraper.source_name
                }, indent=2)
            )]
        
        # Normalize output
        normalized_data = scraper.normalize_output(scraped_data, source_id)
        
        # Check if this is multiple tweets (profile scraping) or single content
        if isinstance(normalized_data, list):
            # Multiple tweets from profile scraping
            data_dir = get_data_dir()
            output_paths = []
            
            for tweet_data in normalized_data:
                tweet_id = tweet_data.get("tweet_id", "unknown")
                tweet_output_file = scraper.get_storage_path(tweet_id, data_dir)
                tweet_output_file.parent.mkdir(parents=True, exist_ok=True)
                
                with open(tweet_output_file, "w", encoding="utf-8") as f:
                    json.dump(tweet_data, f, indent=2, ensure_ascii=False)
                
                output_paths.append(str(tweet_output_file))
            
            # Return result for multiple tweets
            result = {
                "success": True,
                "source": scraper.source_name,
                "account": source_id,
                "tweets_scraped": len(normalized_data),
                "output_paths": output_paths,
                "method_used": method if method != "auto" else "auto (method determined by scraper)",
            }
            
            # Add preview of first few tweets
            if normalized_data:
                result["sample_tweets"] = [
                    {
                        "tweet_id": tweet.get("tweet_id"),
                        "text_preview": tweet.get("text", "")[:100] + "..." if len(tweet.get("text", "")) > 100 else tweet.get("text", "")
                    }
                    for tweet in normalized_data[:3]  # Show first 3 tweets
                ]
        else:
            # Single content (tweet or other source)
            # Save to file
            output_file.parent.mkdir(parents=True, exist_ok=True)
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(normalized_data, f, indent=2, ensure_ascii=False)
            
            # Return result
            result = {
                "success": True,
                "source": scraper.source_name,
                "content_id": source_id,
                "output_path": str(output_file),
                "method_used": method if method != "auto" else "auto (method determined by scraper)",
            }
            
            # Add source-specific metadata
            if scraper.source_name == "chatgpt":
                result["message_count"] = len(normalized_data.get("mapping", {}))
                result["title"] = normalized_data.get("title", "ChatGPT Conversation")
            elif scraper.source_name == "twitter":
                result["username"] = normalized_data.get("username", "")
                result["text_preview"] = normalized_data.get("text", "")[:100] + "..." if len(normalized_data.get("text", "")) > 100 else normalized_data.get("text", "")
        
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    
    except Exception as e:
        return [TextContent(
            type="text",
            text=json.dumps({"error": f"Unexpected error: {str(e)}"}, indent=2)
        )]


async def handle_list_content(args: dict) -> list[TextContent]:
    """Handle list_scraped_content tool call."""
    try:
        source_filter = args.get("source", "all")
        limit = args.get("limit", 50)
        sort_by = args.get("sort_by", "date")
        
        data_dir = get_data_dir()
        
        # Find all scraped content
        all_content = []
        
        for source_name in registry.list_sources():
            if source_filter != "all" and source_filter != source_name:
                continue
            
            scraper = registry.get_scraper_by_name(source_name)
            if not scraper:
                continue
            
            # Look for content in source-specific directory
            source_dir = data_dir / "imports" / source_name
            if not source_dir.exists():
                continue
            
            # Find JSON files
            pattern = "share_*.json" if source_name == "chatgpt" else "tweet_*.json"
            for file_path in source_dir.glob(pattern):
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    
                    content_id = data.get("share_id") or data.get("tweet_id") or file_path.stem
                    
                    all_content.append({
                        "source": source_name,
                        "content_id": content_id,
                        "file_path": str(file_path),
                        "scraped_at": data.get("scraped_at") or data.get("update_time", 0),
                    })
                except Exception:
                    continue
        
        # Sort
        if sort_by == "date":
            all_content.sort(key=lambda x: x.get("scraped_at", 0), reverse=True)
        elif sort_by == "source":
            all_content.sort(key=lambda x: (x.get("source", ""), x.get("scraped_at", 0)), reverse=True)
        
        # Apply limit
        limited_content = all_content[:limit]
        
        result = {
            "content": limited_content,
            "total": len(all_content),
            "shown": len(limited_content)
        }
        
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    
    except Exception as e:
        return [TextContent(
            type="text",
            text=json.dumps({"error": f"Error listing content: {str(e)}"}, indent=2)
        )]


async def handle_get_content(args: dict) -> list[TextContent]:
    """Handle get_scraped_content tool call."""
    try:
        source = args.get("source")
        content_id = args.get("content_id")
        
        if not source or not content_id:
            return [TextContent(
                type="text",
                text=json.dumps({"error": "source and content_id are required"}, indent=2)
            )]
        
        scraper = registry.get_scraper_by_name(source)
        if not scraper:
            return [TextContent(
                type="text",
                text=json.dumps({
                    "error": f"Unknown source: {source}",
                    "supported_sources": registry.list_sources()
                }, indent=2)
            )]
        
        data_dir = get_data_dir()
        file_path = scraper.get_storage_path(content_id, data_dir)
        
        if not file_path.exists():
            return [TextContent(
                type="text",
                text=json.dumps({
                    "error": f"Content not found: {content_id}",
                    "source": source,
                    "file_path": str(file_path)
                }, indent=2)
            )]
        
        # Load content
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        result = {
            "source": source,
            "content_id": content_id,
            "file_path": str(file_path),
            "data": data
        }
        
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    
    except Exception as e:
        return [TextContent(
            type="text",
            text=json.dumps({"error": f"Error getting content: {str(e)}"}, indent=2)
        )]


async def handle_list_sources(args: dict) -> list[TextContent]:
    """Handle list_supported_sources tool call."""
    sources = registry.list_sources()
    
    source_info = []
    for source_name in sources:
        scraper = registry.get_scraper_by_name(source_name)
        if scraper:
            source_info.append({
                "name": source_name,
                "supported_methods": scraper.supported_methods,
                "description": f"Scraper for {source_name}"
            })
    
    result = {
        "sources": source_info,
        "total": len(source_info)
    }
    
    return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def main():
    """Run the MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
