# Web Scraper MCP Server

MCP server for general-purpose web scraping. Supports multiple sources (ChatGPT, X/Twitter, etc.) via a plugin architecture. Uses multiple scraping methods: Playwright, Apify, requests.

## Features

- **Multiple Scraping Methods**: Playwright (default), Apify API, or requests/BeautifulSoup
- **Automatic Method Selection**: Tries methods in order until one succeeds
- **1Password Integration**: Securely retrieve Apify API token from 1Password
- **Auto-Install Dependencies**: Automatically installs missing packages
- **Extensible Architecture**: Plugin-based design allows easy addition of new sources
- **Flexible Storage**: Uses `$DATA_DIR` if available, otherwise config directory

## Supported Sources

### ChatGPT
- **URL Formats**: 
  - `https://chatgpt.com/share/abc-123`
  - `https://chatgpt.com/c/abc-123` (private)
- **Methods**: Playwright, Apify, requests
- **Storage**: `$DATA_DIR/imports/chatgpt/share_{id}.json`

### X/Twitter
- **URL Formats**:
  - Single tweet: `https://twitter.com/username/status/1234567890` or `https://x.com/username/status/1234567890`
  - Account profile (all tweets): `https://twitter.com/username` or `https://x.com/username`
- **Methods**: Apify (primary)
- **Storage**: 
  - Single tweet: `$DATA_DIR/imports/twitter/tweet_{id}.json`
  - Account profile: One file per tweet in `$DATA_DIR/imports/twitter/tweet_{id}.json`
- **Profile Scraping**: When scraping an account profile, all available tweets are fetched and each tweet is saved to a separate JSON file
- **Referenced content**: Tweet links are scraped (Apify for X tweets; for X article URLs we try several Apify actors in order until one returns actual content, then fallback to Playwright). Article actors tried: `apidojo/twitter-scraper-lite`, `pratikdani/twitter-posts-scraper`, `web.harvester/twitter-scraper`, `scrapier/twitter-x-scraper`, `xtdata/twitter-x-scraper`, `apify/website-content-crawler`. Cookie/consent pages are rejected; x.com may still only serve cookie walls for `/i/article/` URLs.

### Extensibility
- Additional sources can be added via plugin architecture
- Create new plugin classes inheriting from `ScraperBase`

## Installation

### As Submodule (Recommended)

1. **Add as submodule** (once GitHub repo is created):
   ```bash
   cd /path/to/parent/repo
   git submodule add https://github.com/markmhendrickson/mcp-server-web-scraper.git mcp/web-scraper
   git submodule update --init mcp/web-scraper
   ```

2. **Install dependencies**:
   ```bash
   cd mcp/web-scraper
   pip install -r requirements.txt
   ```

3. **Install Playwright browsers** (if using Playwright method):
   ```bash
   playwright install chromium
   ```

### Standalone

1. **Clone repository**:
   ```bash
   git clone https://github.com/markmhendrickson/mcp-server-web-scraper.git
   cd mcp-server-web-scraper
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Install Playwright browsers** (if using Playwright method):
   ```bash
   playwright install chromium
   ```

## Configuration

### Environment Variables

Configure via environment variables or `.env` file:

```bash
# Optional: Apify API token (for Apify scraping method)
APIFY_API_TOKEN=your-token-here

# Optional: Data directory for storing conversations
DATA_DIR=/path/to/data
```

### Configuration Priority

1. Environment variables
2. Repo `.env` file (in parent repo root)
3. Config directory `.env` (`~/.config/chatgpt-scraper/.env`)
4. 1Password (if available)

### 1Password Integration

If you have 1Password CLI set up, the server can automatically retrieve your Apify API token:

1. Create 1Password item named "Apify" in vault "Private"
2. Add field named "API token" with your token
3. Server will automatically use it if `APIFY_API_TOKEN` env var is not set

## MCP Tools

### 1. scrape_content

Scrape content from any supported source. Automatically detects source from URL.

**Parameters:**
- `url` (required): URL to scrape
  - ChatGPT: `https://chatgpt.com/share/abc-123` or `https://chatgpt.com/c/abc-123`
  - Twitter/X (single tweet): `https://twitter.com/username/status/1234567890` or `https://x.com/username/status/1234567890`
  - Twitter/X (account profile): `https://twitter.com/username` or `https://x.com/username` (scrapes all tweets)
- `method` (optional): Scraping method - "auto", "playwright", "apify", or "requests"
  - Default: "auto" (tries methods in order)
- `output_path` (optional): Custom output file path
  - Default: `$DATA_DIR/imports/{source}/{id}.json`
  - Note: For profile scraping, each tweet gets its own file

**Returns (single content):**
```json
{
  "success": true,
  "source": "chatgpt",
  "content_id": "abc-123",
  "output_path": "/path/to/file.json",
  "method_used": "playwright",
  "message_count": 9,
  "title": "Conversation Title"
}
```

**Returns (profile scraping):**
```json
{
  "success": true,
  "source": "twitter",
  "account": "username",
  "tweets_scraped": 150,
  "output_paths": [
    "/path/to/tweet_123.json",
    "/path/to/tweet_456.json"
  ],
  "sample_tweets": [
    {
      "tweet_id": "123",
      "text_preview": "First tweet text..."
    }
  ]
}
```

**Examples:**
```json
{
  "url": "https://chatgpt.com/share/69638b9a-bc18-8012-aed2-10ec1e043823",
  "method": "auto"
}
```

```json
{
  "url": "https://twitter.com/username",
  "method": "apify"
}
```

### 2. list_scraped_content

List previously scraped content.

**Parameters:**
- `source` (optional): Filter by source ("chatgpt", "twitter", or "all")
  - Default: "all"
- `limit` (optional): Maximum number to return (default: 50)
- `sort_by` (optional): Sort order - "date" or "source" (default: "date")

**Returns:**
```json
{
  "content": [
    {
      "source": "chatgpt",
      "content_id": "abc-123",
      "file_path": "/path/to/file.json",
      "scraped_at": 1768198678
    }
  ],
  "total": 10,
  "shown": 10
}
```

### 3. get_scraped_content

Get details about specific scraped content.

**Parameters:**
- `source` (required): Source type ("chatgpt", "twitter")
- `content_id` (required): Content ID (e.g., share ID for ChatGPT, tweet ID for Twitter)

**Returns:**
```json
{
  "source": "chatgpt",
  "content_id": "abc-123",
  "file_path": "/path/to/file.json",
  "data": { ... }
}
```

### 4. list_supported_sources

List all supported scraping sources.

**Returns:**
```json
{
  "sources": [
    {
      "name": "chatgpt",
      "supported_methods": ["playwright", "apify", "requests"],
      "description": "Scraper for chatgpt"
    },
    {
      "name": "twitter",
      "supported_methods": ["apify"],
      "description": "Scraper for twitter"
    }
  ],
  "total": 2
}
```

## Usage Examples

### Via MCP Client (Cursor)

1. **Add to MCP config** (`.cursor/mcp.json`):
   ```json
   {
     "mcpServers": {
       "web-scraper": {
         "command": "/absolute/path/to/mcp/web-scraper/run-web-scraper-mcp.sh"
       }
     }
   }
   ```

2. **Use tools in Cursor**:
   - Ask Cursor to scrape a ChatGPT conversation
   - Ask Cursor to scrape a Twitter/X post (single tweet)
   - Ask Cursor to scrape all tweets from a Twitter/X account (profile scraping)
   - Ask Cursor to list your scraped content
   - Ask Cursor to show details about specific content

### Via Command Line (Testing)

```bash
# Run MCP server
./run-web-scraper-mcp.sh

# Or run directly
python3 web_scraper_mcp_server.py
```

## Scraping Methods

### Playwright (Default, Most Reliable)

- Handles JavaScript-rendered content
- Extracts messages from DOM
- Intercepts API responses
- Auto-installs if missing

**Pros:** Most reliable, works with complex pages
**Cons:** Slower, requires browser installation

### Apify API

- Uses Apify's ChatGPT Conversation Scraper actor
- Requires `APIFY_API_TOKEN`
- Cloud-based scraping

**Pros:** Fast, reliable, no browser needed
**Cons:** Requires API token (paid service)

### Requests/BeautifulSoup

- Simple HTTP requests
- Limited to server-rendered content
- Fallback method

**Pros:** Fast, no dependencies
**Cons:** Limited effectiveness (ChatGPT uses client-side rendering)

## Data Storage

Conversations are saved to:
1. `$DATA_DIR/imports/chatgpt/share_{id}.json` (if `DATA_DIR` is set)
2. `~/.config/chatgpt-scraper/conversations/share_{id}.json` (fallback)

**Format:** ChatGPT export JSON format with `mapping` structure

```json
{
  "title": "Conversation Title",
  "create_time": 1768198138,
  "update_time": 1768198678,
  "mapping": {
    "node_0": {
      "id": "node_0",
      "message": {
        "id": "msg_0",
        "author": { "role": "user" },
        "create_time": 1768198138,
        "content": {
          "content_type": "text",
          "parts": ["Message text..."]
        }
      },
      "parent": null,
      "children": ["node_1"]
    }
  },
  "current_node": "node_0",
  "share_id": "abc-123"
}
```

## Troubleshooting

### Playwright timeout errors

**Problem:** Playwright times out when loading page

**Solution:**
- Ensure internet connection is stable
- Try increasing timeout (currently 60 seconds)
- Check if URL is accessible in browser

### Apify API errors

**Problem:** "APIFY_API_TOKEN required" error

**Solution:**
- Set `APIFY_API_TOKEN` environment variable
- Or configure in 1Password (item "Apify", field "API token")
- Get token at https://console.apify.com/account/integrations

### No messages found

**Problem:** Scraping succeeds but returns 0 messages

**Solution:**
- `/c/` URLs (private) require authentication - use `/share/` URL instead
- Share the conversation from ChatGPT to get a public URL
- Try different scraping method: `"method": "apify"`

### Import errors

**Problem:** "Module not found" errors

**Solution:**
```bash
pip install -r requirements.txt
playwright install chromium
```

### Submodule not initialized

**Problem:** "Submodule not initialized" error

**Solution:**
```bash
cd /path/to/parent/repo
git submodule update --init mcp/web-scraper
```

### Unsupported URL

**Problem:** "Unsupported URL" error

**Solution:**
- Check that URL matches supported formats
- Use `list_supported_sources` tool to see available sources
- Add new source plugin if needed

## Development

### Project Structure

```
mcp/web-scraper/
├── __init__.py                      # Package initialization
├── web_scraper_mcp_server.py       # Main MCP server
├── scraper_base.py                  # Base scraper interface
├── scraper_registry.py              # Scraper registry
├── scraper.py                       # ChatGPT scraping logic
├── plugins/
│   ├── __init__.py
│   ├── chatgpt_scraper.py          # ChatGPT plugin
│   └── twitter_scraper.py           # Twitter/X plugin
├── run-web-scraper-mcp.sh          # Wrapper script
├── requirements.txt                 # Python dependencies
└── README.md                        # This file
```

### Testing

```bash
# Test ChatGPT scraper
python3 -c "
from plugins.chatgpt_scraper import ChatGPTScraper
scraper = ChatGPTScraper()
result = scraper.scrape('https://chatgpt.com/share/YOUR_SHARE_ID')
print(f'Found {len(result.get(\"messages\", []))} messages')
"

# Test Twitter scraper - single tweet (requires Apify token)
python3 -c "
from plugins.twitter_scraper import TwitterScraper
scraper = TwitterScraper()
result = scraper.scrape('https://twitter.com/username/status/TWEET_ID')
print(result)
"

# Test Twitter scraper - profile (all tweets, requires Apify token)
python3 -c "
from plugins.twitter_scraper import TwitterScraper
scraper = TwitterScraper()
result = scraper.scrape('https://twitter.com/username')
print(f'Found {len(result.get(\"tweets\", []))} tweets')
"
```

## Adding New Sources

To add a new source, create a plugin class:

1. **Create plugin file** in `plugins/` directory:
   ```python
   from scraper_base import ScraperBase
   
   class MySourceScraper(ScraperBase):
       @property
       def source_name(self) -> str:
           return "mysource"
       
       # Implement required methods...
   ```

2. **Register in main server** (`web_scraper_mcp_server.py`):
   ```python
   from plugins.my_source_scraper import MySourceScraper
   registry.register(MySourceScraper())
   ```

## License

MIT License - See parent repository for details

## Contributing

Contributions welcome! Please submit issues and pull requests to the GitHub repository.

## Related Projects

- [conversation_parser.py](../../execution/scripts/conversation_parser.py) - Parse and analyze scraped conversations
- [Apify ChatGPT Scraper](https://apify.com/straightforward_understanding/chatgpt-conversation-scraper) - Apify actor used for ChatGPT scraping
- [Apify Twitter Scraper](https://apify.com/apify/twitter-scraper) - Apify actor used for Twitter/X scraping
