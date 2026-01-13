# ChatGPT Scraper MCP Server

MCP server for scraping ChatGPT conversations from shared links. Supports multiple scraping methods and provides tools for managing scraped conversations.

> **Note:** This repository was renamed from `mcp-server-chatgpt-scraper` to `mcp-server-web-scraper` on GitHub, but the functionality remains focused on ChatGPT conversation scraping.

## Features

- **Multiple Scraping Methods**: Playwright (default), Apify API, or requests/BeautifulSoup
- **Automatic Method Selection**: Tries methods in order until one succeeds
- **1Password Integration**: Securely retrieve Apify API token from 1Password
- **Auto-Install Dependencies**: Automatically installs missing packages
- **Supports Both URL Types**: Works with `/share/` (public) and `/c/` (private) URLs
- **Conversation Management**: List and retrieve previously scraped conversations
- **Flexible Storage**: Uses `$DATA_DIR` if available, otherwise config directory

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

### 1. scrape_chatgpt_conversation

Scrape a ChatGPT conversation from a share URL.

**Parameters:**
- `url` (required): ChatGPT share URL
  - Supports: `https://chatgpt.com/share/abc-123`
  - Supports: `https://chatgpt.com/c/abc-123` (private, requires auth)
- `method` (optional): Scraping method - "auto", "playwright", "apify", or "requests"
  - Default: "auto" (tries Playwright → Apify → requests)
- `output_path` (optional): Custom output file path
  - Default: `$DATA_DIR/imports/chatgpt/share_{id}.json`

**Returns:**
```json
{
  "success": true,
  "share_id": "abc-123",
  "output_path": "/path/to/file.json",
  "message_count": 9,
  "title": "Conversation Title",
  "method_used": "playwright"
}
```

**Example:**
```json
{
  "url": "https://chatgpt.com/share/69638b9a-bc18-8012-aed2-10ec1e043823",
  "method": "auto"
}
```

### 2. list_scraped_conversations

List previously scraped conversations.

**Parameters:**
- `limit` (optional): Maximum number to return (default: 50)
- `sort_by` (optional): Sort order - "date", "title", or "message_count" (default: "date")

**Returns:**
```json
{
  "conversations": [
    {
      "share_id": "abc-123",
      "title": "Conversation Title",
      "file_path": "/path/to/file.json",
      "message_count": 9,
      "scraped_at": 1768198678
    }
  ],
  "total": 10,
  "shown": 10
}
```

**Example:**
```json
{
  "limit": 10,
  "sort_by": "date"
}
```

### 3. get_conversation_details

Get details about a specific scraped conversation.

**Parameters:**
- `share_id` (required): ChatGPT share ID (e.g., "abc-123")

**Returns:**
```json
{
  "share_id": "abc-123",
  "title": "Conversation Title",
  "file_path": "/path/to/file.json",
  "message_count": 9,
  "scraped_at": 1768198678,
  "messages": [
    {
      "role": "user",
      "text": "Message text...",
      "create_time": 1768198138
    },
    {
      "role": "assistant",
      "text": "Response text...",
      "create_time": 1768198198
    }
  ]
}
```

**Example:**
```json
{
  "share_id": "69638b9a-bc18-8012-aed2-10ec1e043823"
}
```

## Usage Examples

### Via MCP Client (Cursor)

1. **Add to MCP config** (`.cursor/mcp.json`):
   ```json
   {
     "mcpServers": {
       "web-scraper": {
         "command": "/absolute/path/to/mcp/web-scraper/run-chatgpt-scraper-mcp.sh"
       }
     }
   }
   ```

2. **Use tools in Cursor**:
   - Ask Cursor to scrape a ChatGPT conversation
   - Ask Cursor to list your scraped conversations
   - Ask Cursor to show details about a specific conversation

### Via Command Line (Testing)

```bash
# Run MCP server
./run-chatgpt-scraper-mcp.sh

# Or run directly
python3 chatgpt_scraper_mcp_server.py
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

## Development

### Project Structure

```
mcp/web-scraper/
├── __init__.py                      # Package initialization
├── chatgpt_scraper_mcp_server.py   # Main MCP server
├── scraper.py                       # Core scraping logic
├── run-chatgpt-scraper-mcp.sh      # Wrapper script
├── requirements.txt                 # Python dependencies
└── README.md                        # This file
```

### Testing

```bash
# Test Playwright method
python3 -c "
from scraper import scrape_with_playwright
result = scrape_with_playwright('https://chatgpt.com/share/YOUR_SHARE_ID')
print(f'Found {len(result.get(\"messages\", []))} messages')
"

# Test Apify method (requires token)
python3 -c "
from scraper import scrape_with_apify
result = scrape_with_apify('https://chatgpt.com/share/YOUR_SHARE_ID')
print(f'Found {len(result.get(\"messages\", []))} messages')
"
```

## License

MIT License - See parent repository for details

## Contributing

Contributions welcome! Please submit issues and pull requests to the GitHub repository.

## Related Projects

- [conversation_parser.py](../../execution/scripts/conversation_parser.py) - Parse and analyze scraped conversations
- [Apify ChatGPT Scraper](https://apify.com/straightforward_understanding/chatgpt-conversation-scraper) - Apify actor used by this server
