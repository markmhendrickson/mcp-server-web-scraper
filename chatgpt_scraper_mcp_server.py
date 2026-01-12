#!/usr/bin/env python3
"""
MCP Server for ChatGPT Conversation Scraping

Provides tools for scraping ChatGPT conversations from shared links.
Supports multiple methods: Playwright, Apify, requests.
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

# Import scraping functions
from scraper import (
    scrape_with_playwright,
    scrape_with_apify,
    scrape_with_requests,
    extract_share_id,
    convert_to_export_format,
    save_conversation_json,
    get_apify_token_from_1password,
)

# Configuration directory (portable, uses user's home directory)
CONFIG_DIR = Path.home() / ".config" / "chatgpt-scraper"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
ENV_FILE = CONFIG_DIR / ".env"

# Local .env file (in repo directory, for development)
SERVER_DIR = Path(__file__).parent
LOCAL_ENV_FILE = SERVER_DIR / ".env"

# Initialize MCP server
app = Server("chatgpt-scraper")


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
        # Try local .env file first (for development)
        load_from_file(LOCAL_ENV_FILE)
        # Then try config directory .env (for portable deployment)
        if not credentials["apify_token"] or not credentials["data_dir"]:
            load_from_file(ENV_FILE)

    return credentials


def get_credentials() -> dict[str, str | None]:
    """Get credentials from environment, .env file, or 1Password."""
    # Priority: environment variable > .env file > 1Password
    credentials = load_credentials_from_env()
    
    # Try 1Password for Apify token if not found
    if not credentials["apify_token"]:
        credentials["apify_token"] = get_apify_token_from_1password()
    
    return credentials


def get_data_dir() -> Path:
    """Get data directory for storing scraped conversations."""
    credentials = get_credentials()
    
    # Try DATA_DIR from credentials
    if credentials.get("data_dir"):
        data_dir = Path(credentials["data_dir"]) / "imports" / "chatgpt"
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir
    
    # Try to import config module from parent repo
    try:
        server_dir = Path(__file__).parent
        possible_paths = [
            server_dir.parent.parent,  # mcp/chatgpt-scraper -> mcp -> personal
        ]
        
        for parent_path in possible_paths:
            config_path = parent_path / "config.py"
            if config_path.exists():
                sys.path.insert(0, str(parent_path))
                try:
                    from config import get_data_dir as _get_data_dir
                    return _get_data_dir() / "imports" / "chatgpt"
                except ImportError:
                    continue
    except Exception:
        pass
    
    # Fallback to config directory
    conversations_dir = CONFIG_DIR / "conversations"
    conversations_dir.mkdir(parents=True, exist_ok=True)
    return conversations_dir


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools."""
    return [
        Tool(
            name="scrape_chatgpt_conversation",
            description="Scrape a ChatGPT conversation from a share URL. Supports both /share/ and /c/ URLs. Uses Playwright (default), Apify, or requests methods.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "ChatGPT share URL (e.g., https://chatgpt.com/share/abc-123 or https://chatgpt.com/c/abc-123)"
                    },
                    "method": {
                        "type": "string",
                        "enum": ["auto", "playwright", "apify", "requests"],
                        "description": "Scraping method to use. 'auto' tries Playwright first, then Apify, then requests. Default: auto",
                        "default": "auto"
                    },
                    "output_path": {
                        "type": "string",
                        "description": "Optional: Custom output file path. If not provided, saves to $DATA_DIR/imports/chatgpt/share_{id}.json"
                    }
                },
                "required": ["url"]
            }
        ),
        Tool(
            name="list_scraped_conversations",
            description="List previously scraped ChatGPT conversations from the data directory",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of conversations to return. Default: 50",
                        "default": 50
                    },
                    "sort_by": {
                        "type": "string",
                        "enum": ["date", "title", "message_count"],
                        "description": "Sort order. Default: date",
                        "default": "date"
                    }
                }
            }
        ),
        Tool(
            name="get_conversation_details",
            description="Get details about a specific scraped ChatGPT conversation",
            inputSchema={
                "type": "object",
                "properties": {
                    "share_id": {
                        "type": "string",
                        "description": "ChatGPT share ID (e.g., 'abc-123' from the URL)"
                    }
                },
                "required": ["share_id"]
            }
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """Handle tool calls."""
    if name == "scrape_chatgpt_conversation":
        return await handle_scrape_conversation(arguments)
    elif name == "list_scraped_conversations":
        return await handle_list_conversations(arguments)
    elif name == "get_conversation_details":
        return await handle_get_details(arguments)
    
    raise ValueError(f"Unknown tool: {name}")


async def handle_scrape_conversation(args: dict) -> list[TextContent]:
    """Handle scrape_chatgpt_conversation tool call."""
    try:
        url = args.get("url")
        method = args.get("method", "auto")
        output_path = args.get("output_path")
        
        if not url:
            return [TextContent(
                type="text",
                text=json.dumps({"error": "URL is required"}, indent=2)
            )]
        
        # Extract share ID
        try:
            share_id = extract_share_id(url)
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
            output_file = data_dir / f"share_{share_id}.json"
        
        # Scrape conversation
        scraped_data = None
        method_used = None
        credentials = get_credentials()
        
        methods_to_try = []
        if method == "auto":
            methods_to_try = ["playwright", "apify", "requests"]
        else:
            methods_to_try = [method]
        
        errors = []
        for scrape_method in methods_to_try:
            try:
                if scrape_method == "playwright":
                    scraped_data = scrape_with_playwright(url)
                    method_used = "playwright"
                    break
                elif scrape_method == "apify":
                    scraped_data = scrape_with_apify(url, credentials.get("apify_token"))
                    method_used = "apify"
                    break
                elif scrape_method == "requests":
                    scraped_data = scrape_with_requests(url)
                    method_used = "requests"
                    break
            except ImportError as e:
                errors.append(f"{scrape_method}: {str(e)}")
                continue
            except Exception as e:
                errors.append(f"{scrape_method}: {str(e)}")
                continue
        
        if not scraped_data:
            return [TextContent(
                type="text",
                text=json.dumps({
                    "error": "All scraping methods failed",
                    "details": errors
                }, indent=2)
            )]
        
        # Convert to export format
        export_data = convert_to_export_format(scraped_data, share_id)
        
        # Save to file
        save_conversation_json(export_data, output_file)
        
        # Return result
        result = {
            "success": True,
            "share_id": share_id,
            "output_path": str(output_file),
            "message_count": len(export_data.get("mapping", {})),
            "title": export_data.get("title", "ChatGPT Conversation"),
            "method_used": method_used
        }
        
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    
    except Exception as e:
        return [TextContent(
            type="text",
            text=json.dumps({"error": f"Unexpected error: {str(e)}"}, indent=2)
        )]


async def handle_list_conversations(args: dict) -> list[TextContent]:
    """Handle list_scraped_conversations tool call."""
    try:
        limit = args.get("limit", 50)
        sort_by = args.get("sort_by", "date")
        
        data_dir = get_data_dir()
        
        # Find all JSON files in data directory
        if not data_dir.exists():
            return [TextContent(
                type="text",
                text=json.dumps({
                    "conversations": [],
                    "total": 0,
                    "message": f"Data directory not found: {data_dir}"
                }, indent=2)
            )]
        
        conversation_files = list(data_dir.glob("share_*.json"))
        
        # Extract metadata from each file
        conversations = []
        for file_path in conversation_files:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                share_id = data.get("share_id", file_path.stem.replace("share_", ""))
                
                conversations.append({
                    "share_id": share_id,
                    "title": data.get("title", "Unknown"),
                    "file_path": str(file_path),
                    "message_count": len(data.get("mapping", {})),
                    "scraped_at": data.get("update_time", 0),
                })
            except Exception as e:
                # Skip files that can't be parsed
                continue
        
        # Sort conversations
        if sort_by == "date":
            conversations.sort(key=lambda x: x.get("scraped_at", 0), reverse=True)
        elif sort_by == "title":
            conversations.sort(key=lambda x: x.get("title", "").lower())
        elif sort_by == "message_count":
            conversations.sort(key=lambda x: x.get("message_count", 0), reverse=True)
        
        # Apply limit
        limited_conversations = conversations[:limit]
        
        result = {
            "conversations": limited_conversations,
            "total": len(conversations),
            "shown": len(limited_conversations)
        }
        
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    
    except Exception as e:
        return [TextContent(
            type="text",
            text=json.dumps({"error": f"Error listing conversations: {str(e)}"}, indent=2)
        )]


async def handle_get_details(args: dict) -> list[TextContent]:
    """Handle get_conversation_details tool call."""
    try:
        share_id = args.get("share_id")
        
        if not share_id:
            return [TextContent(
                type="text",
                text=json.dumps({"error": "share_id is required"}, indent=2)
            )]
        
        data_dir = get_data_dir()
        file_path = data_dir / f"share_{share_id}.json"
        
        if not file_path.exists():
            return [TextContent(
                type="text",
                text=json.dumps({
                    "error": f"Conversation not found: {share_id}",
                    "file_path": str(file_path)
                }, indent=2)
            )]
        
        # Load conversation data
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # Extract messages from mapping
        messages = []
        mapping = data.get("mapping", {})
        
        # Sort by node order (node_0, node_1, etc.)
        sorted_nodes = sorted(mapping.items(), key=lambda x: int(x[0].split("_")[1]) if "_" in x[0] else 0)
        
        for node_id, node in sorted_nodes:
            msg = node.get("message", {})
            if msg:
                messages.append({
                    "role": msg.get("author", {}).get("role", "unknown"),
                    "text": msg.get("content", {}).get("parts", [""])[0] if isinstance(msg.get("content"), dict) else str(msg.get("content", "")),
                    "create_time": msg.get("create_time", 0)
                })
        
        result = {
            "share_id": share_id,
            "title": data.get("title", "Unknown"),
            "file_path": str(file_path),
            "message_count": len(messages),
            "scraped_at": data.get("update_time", 0),
            "messages": messages
        }
        
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    
    except Exception as e:
        return [TextContent(
            type="text",
            text=json.dumps({"error": f"Error getting conversation details: {str(e)}"}, indent=2)
        )]


if __name__ == "__main__":
    asyncio.run(stdio_server(app))
