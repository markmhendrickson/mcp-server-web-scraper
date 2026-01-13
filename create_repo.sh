#!/bin/bash
# Create GitHub repository for web-scraper MCP server using GitHub CLI

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Creating GitHub Repository for Web Scraper MCP Server ==="
echo ""

# Check for GitHub CLI
if ! command -v gh &> /dev/null; then
    echo "GitHub CLI not found. Installing..."
    if command -v brew &> /dev/null; then
        brew install gh
    else
        echo "❌ Homebrew not found. Please install GitHub CLI manually:"
        echo "   https://cli.github.com/"
        exit 1
    fi
fi

# Check authentication
if ! gh auth status &> /dev/null; then
    echo "GitHub CLI not authenticated. Please login:"
    gh auth login
fi

echo ""
echo "Creating repository: mcp-server-web-scraper"
echo ""

# Create repo and push
gh repo create mcp-server-web-scraper \
    --public \
    --description "MCP server for scraping ChatGPT conversations from shared links. Supports multiple scraping methods (Playwright, Apify, requests)." \
    --source=. \
    --remote=origin \
    --push

echo ""
echo "✓ Repository created and pushed!"
echo ""
echo "Repository URL: https://github.com/markmhendrickson/mcp-server-web-scraper"
echo ""
echo "Next: Add as submodule to parent repo:"
echo "  cd /Users/markmhendrickson/repos/personal"
echo "  rm -rf mcp/web-scraper"
echo "  git submodule add https://github.com/markmhendrickson/mcp-server-web-scraper.git mcp/web-scraper"
