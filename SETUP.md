# ChatGPT Scraper MCP Server - Setup Guide

## Implementation Status

✅ **Completed:**
- Core scraping logic extracted to `scraper.py`
- MCP server with 3 tools implemented
- Wrapper script created
- Requirements.txt with dependencies
- Comprehensive README.md
- Basic tests passed (syntax validation, function tests)
- MCP config template updated
- Local git repository initialized with commits

⚠️ **Manual Steps Required:**

### 1. Create GitHub Repository

The local git repository is ready but needs to be pushed to GitHub:

**Using GitHub CLI (Recommended - Always use CLI for repo creation):**

Run the automated script:
```bash
cd /Users/markmhendrickson/repos/personal/mcp/chatgpt-scraper
./create_repo.sh
```

Or manually:
```bash
# Authenticate (if not already)
gh auth login

# Create and push repo
cd /Users/markmhendrickson/repos/personal/mcp/chatgpt-scraper
gh repo create mcp-server-chatgpt-scraper --public --source=. --remote=origin --push
```

**Note:** Always use GitHub CLI (`gh`) to create repositories. The script will:
- Install GitHub CLI if missing
- Authenticate if needed
- Create the repository
- Push all commits

### 2. Add as Submodule to Parent Repo

Once the GitHub repo is created and pushed:

```bash
cd /Users/markmhendrickson/repos/personal

# Remove the local directory (we'll re-add it as submodule)
rm -rf mcp/chatgpt-scraper

# Add as submodule
git submodule add https://github.com/markmhendrickson/mcp-server-chatgpt-scraper.git mcp/chatgpt-scraper

# Commit the submodule addition
git add .gitmodules mcp/chatgpt-scraper
git commit -m "Add chatgpt-scraper MCP server as submodule"
```

### 3. Test the MCP Server

After setting up as submodule:

1. **Test via Cursor:**
   - MCP config is already updated (`.cursor/mcp.json`)
   - Restart Cursor to load the new server
   - Try asking: "Scrape this ChatGPT conversation: https://chatgpt.com/share/YOUR_SHARE_ID"

2. **Test directly:**
   ```bash
   cd mcp/chatgpt-scraper
   ./run-chatgpt-scraper-mcp.sh
   # Server should start without errors
   ```

3. **Test with actual URL:**
   ```bash
   python3 -c "
   from scraper import scrape_with_playwright
   result = scrape_with_playwright('https://chatgpt.com/share/YOUR_SHARE_ID')
   print(f'Found {len(result.get(\"messages\", []))} messages')
   "
   ```

## Configuration

### Environment Variables (Optional)

Create `.env` in repo root or `~/.config/chatgpt-scraper/.env`:

```bash
# Optional: Apify API token (for Apify scraping method)
APIFY_API_TOKEN=your-token-here

# Optional: Data directory
DATA_DIR=/path/to/data
```

### 1Password Integration (Optional)

If you have 1Password CLI:

1. Create item "Apify" in vault "Private"
2. Add field "API token" with your Apify token
3. Server will automatically use it

## Current State

**Files Created:**
- `__init__.py` - Package initialization
- `scraper.py` - Core scraping logic (1,000+ lines)
- `chatgpt_scraper_mcp_server.py` - MCP server (500+ lines)
- `run-chatgpt-scraper-mcp.sh` - Wrapper script
- `requirements.txt` - Dependencies
- `README.md` - Comprehensive documentation
- `.gitignore` - Git ignore patterns
- `SETUP.md` - This file

**Git Status:**
- 2 commits made locally
- Remote configured: https://github.com/markmhendrickson/mcp-server-chatgpt-scraper.git
- Ready to push once GitHub repo is created

**Parent Repo Changes:**
- `mcp/mcp-config-template.json` - Added chatgpt-scraper entry
- `.cursor/mcp.json` - Regenerated with new server

## Next Steps

1. Create GitHub repository (see Manual Steps above)
2. Push local commits to GitHub
3. Add as submodule to parent repo
4. Test via Cursor MCP client
5. Optionally configure Apify API token for enhanced scraping

## Tools Available

1. **scrape_chatgpt_conversation** - Scrape conversations from share URLs
2. **list_scraped_conversations** - List previously scraped conversations
3. **get_conversation_details** - Get details about a specific conversation

## Support

- See `README.md` for detailed usage documentation
- See `README.md` Troubleshooting section for common issues
- All three scraping methods (Playwright, Apify, requests) are implemented
- Auto-installation of dependencies is supported
