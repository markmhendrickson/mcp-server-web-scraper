"""
Core scraping logic for ChatGPT conversations.

Supports multiple methods:
1. Playwright (handles JavaScript rendering) - Default, most reliable
2. Apify API (requires APIFY_API_TOKEN)
3. Requests/BeautifulSoup (limited, for server-rendered content)
"""

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

# Availability flags
REQUESTS_AVAILABLE = False
BEAUTIFULSOUP_AVAILABLE = False
PLAYWRIGHT_AVAILABLE = False
APIFY_AVAILABLE = False
CREDENTIALS_AVAILABLE = False

# Try to import optional dependencies
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    pass

try:
    from bs4 import BeautifulSoup
    BEAUTIFULSOUP_AVAILABLE = True
except ImportError:
    pass

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    pass

try:
    from apify_client import ApifyClient
    APIFY_AVAILABLE = True
except ImportError:
    pass

# Try to import 1Password credentials utility
try:
    # Try to find credentials module (may be in parent repo)
    server_dir = Path(__file__).parent
    possible_paths = [
        server_dir.parent.parent,  # mcp/chatgpt-scraper -> mcp -> personal
    ]
    
    for parent_path in possible_paths:
        credentials_path = parent_path / "execution" / "scripts" / "credentials.py"
        if credentials_path.exists():
            sys.path.insert(0, str(parent_path))
            try:
                from execution.scripts.credentials import get_credential
                CREDENTIALS_AVAILABLE = True
                break
            except ImportError:
                continue
except Exception:
    pass


def install_package(package_name: str) -> bool:
    """Install a Python package using pip."""
    try:
        print(f"Installing {package_name}...")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", package_name],
            capture_output=True,
            text=True,
            check=True,
        )
        print(f"✓ Successfully installed {package_name}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ Failed to install {package_name}: {e.stderr}")
        return False
    except Exception as e:
        print(f"✗ Error installing {package_name}: {e}")
        return False


def ensure_package_installed(package_name: str, import_name: str | None = None) -> bool:
    """Ensure a package is installed, install if missing."""
    if import_name is None:
        import_name = package_name
    
    try:
        __import__(import_name)
        return True
    except ImportError:
        return install_package(package_name)


def get_apify_token_from_1password() -> str | None:
    """Get Apify API token from 1Password."""
    if not CREDENTIALS_AVAILABLE:
        return None
    
    try:
        from execution.scripts.credentials import get_credential
        
        # Try to get API token from 1Password item "Apify"
        # Field name variations: "API token", "api_token", "token", "API key"
        token = get_credential("Apify", vault="Private", field="API token")
        if token:
            return token
        
        # Try other field name variations
        for field_name in ["api_token", "token", "API key", "apify_token"]:
            try:
                token = get_credential("Apify", vault="Private", field=field_name)
                if token:
                    return token
            except (ValueError, KeyError):
                continue
        
        return None
    except Exception as e:
        print(f"Warning: Could not get Apify token from 1Password: {e}")
        return None


def extract_share_id(url: str) -> str:
    """Extract share ID from ChatGPT share URL."""
    # Support formats:
    # https://chatgpt.com/share/abc-123-def
    # https://chatgpt.com/share/abc-123-def/
    # chat.openai.com/share/abc-123-def
    # https://chatgpt.com/c/abc-123-def (private conversation)
    # https://chatgpt.com/c/abc-123-def?ref=mini
    match = re.search(r"/(?:share|c)/([a-zA-Z0-9-]+)", url)
    if not match:
        raise ValueError(f"Invalid ChatGPT share URL format: {url}")
    return match.group(1)


def _extract_messages_from_mapping(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract messages list from ChatGPT mapping structure."""
    messages = []
    mapping = data.get("mapping", {})

    for node_id, node in mapping.items():
        msg = node.get("message")
        if not msg:
            continue

        author = msg.get("author", {})
        role = author.get("role") if isinstance(author, dict) else author
        if role not in ["user", "assistant"]:
            continue

        content = msg.get("content", {})
        if isinstance(content, dict):
            if content.get("content_type") != "text":
                continue
            parts = content.get("parts", [])
            text = parts[0] if parts else ""
        elif isinstance(content, str):
            text = content
        else:
            continue

        if not text:
            continue

        create_time = msg.get("create_time")
        messages.append(
            {
                "role": role,
                "text": text,
                "create_time": create_time,
                "index": len(messages),
            }
        )

    # Sort by create_time if available
    messages.sort(key=lambda x: x.get("create_time", 0))
    return messages


def scrape_with_playwright(share_url: str, timeout: int = 60000) -> dict[str, Any]:
    """
    Scrape conversation using Playwright (handles JavaScript rendering).
    
    Args:
        share_url: ChatGPT share URL
        timeout: Page load timeout in milliseconds
        
    Returns:
        Dictionary with conversation data (messages, title, url)
        
    Raises:
        ImportError: If playwright not installed
        Exception: If scraping fails
    """
    global PLAYWRIGHT_AVAILABLE
    
    # Ensure playwright is installed
    if not PLAYWRIGHT_AVAILABLE:
        if not ensure_package_installed("playwright", "playwright"):
            raise ImportError(
                "playwright not installed and installation failed. "
                "Install manually with: pip install playwright && playwright install"
            )
        # Re-import after installation
        try:
            from playwright.sync_api import sync_playwright
            PLAYWRIGHT_AVAILABLE = True
        except ImportError:
            raise ImportError("playwright installed but import failed")
    
    # Import playwright after ensuring it's installed
    from playwright.sync_api import sync_playwright

    print(f"Scraping with Playwright: {share_url}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Intercept network responses to find conversation data API
        api_responses = []

        def handle_response(response):
            url = response.url
            # Look for API endpoints that might contain conversation data
            if any(
                keyword in url.lower()
                for keyword in ["api", "share", "conversation", "backend", "v1"]
            ):
                try:
                    # Try to get JSON response
                    if "application/json" in response.headers.get("content-type", ""):
                        api_responses.append({"url": url, "data": response.json()})
                except Exception:
                    pass

        page.on("response", handle_response)

        try:
            page.goto(share_url, wait_until="domcontentloaded", timeout=timeout)

            # Wait for content to load - ChatGPT pages need time for React to render
            time.sleep(3)

            # Try to wait for message content to appear
            try:
                # Wait for any potential message containers
                page.wait_for_selector("div, article, main", timeout=5000)
            except Exception:
                pass

            # Wait for React to fully hydrate
            try:
                page.wait_for_load_state("networkidle", timeout=30000)
            except Exception:
                pass  # Continue even if networkidle times out
            time.sleep(8)  # ChatGPT needs extra time for content rendering

            # Scroll to bottom to trigger lazy loading if needed
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(2)
            page.evaluate("window.scrollTo(0, 0)")  # Scroll back to top
            time.sleep(2)

            # First, try to get the page's visible text content
            visible_text = page.locator("body").inner_text()

            # Try to extract conversation from page
            # ChatGPT shared pages structure messages differently - try multiple approaches
            conversation_data = page.evaluate(
                r"""
                () => {
                    const messages = [];

                    // Approach 1: Look for message containers by common patterns
                    // ChatGPT shared pages often use specific data attributes or classes
                    const possibleSelectors = [
                        'div[data-message-author-role]',
                        'div[class*="group"]',
                        'div[class*="flex-col"]',
                        'div[class*="w-full"]',
                        'article',
                        'div[role="article"]',
                        'main > div > div',
                        'div[class*="markdown"]',
                    ];

                    let messageContainers = [];
                    for (const selector of possibleSelectors) {
                        const elements = document.querySelectorAll(selector);
                        if (elements.length > 2) {  // Should have multiple messages
                            messageContainers = Array.from(elements);
                            break;
                        }
                    }

                    // Approach 2: Look for elements with data-message-author-role attribute
                    if (messageContainers.length === 0) {
                        const roleElements = document.querySelectorAll('[data-message-author-role]');
                        messageContainers = Array.from(roleElements);
                    }

                    // Extract messages from containers
                    messageContainers.forEach((container, idx) => {
                        // Try to get role from attribute
                        let role = container.getAttribute('data-message-author-role') ||
                                  container.getAttribute('data-author-role') ||
                                  null;

                        // Get text content - look for markdown or text content
                        let textContent = '';
                        const markdownEl = container.querySelector('[class*="markdown"], [class*="prose"], pre, code');
                        if (markdownEl) {
                            textContent = markdownEl.innerText || markdownEl.textContent || '';
                        } else {
                            textContent = container.innerText || container.textContent || '';
                        }

                        // Clean up text - remove UI elements and JavaScript code
                        textContent = textContent
                            .replace(/Skip to content|ChatGPT|Log in|Sign up|Attach|Search|Create image|Voice/gi, '')
                            .replace(/By messaging.*Privacy Policy\./g, '')
                            .replace(/window\.__[a-zA-Z]+|requestAnimationFrame|Date\.now\(\)/g, '')  // Remove JS code
                            .trim();

                        // Filter out JavaScript code, function calls, and very short content
                        if (textContent.length > 20 &&
                            !textContent.match(/^window\.|^function|^import|^requestAnimationFrame|^__/i) &&
                            !textContent.match(/^\s*[\{\}\[\]\(\);,]+/)) {  // Not just symbols
                            // If role not found, use heuristic: first is usually user
                            if (!role) {
                                role = idx % 2 === 0 ? 'user' : 'assistant';
                            } else if (role === 'system') {
                                return;  // Skip system messages
                            }

                            // Normalize role to 'user' or 'assistant'
                            if (role.toLowerCase().includes('user') || role === 'user') {
                                role = 'user';
                            } else {
                                role = 'assistant';
                            }

                            messages.push({
                                role: role,
                                text: textContent,
                                index: messages.length,
                            });
                        }
                    });

                    // Approach 3: Extract from main content area, look for paragraph-like blocks
                    if (messages.length === 0 || messages.every(m => m.text.match(/window\.__|requestAnimationFrame/))) {
                        // Find main content container
                        const mainContainer = document.querySelector('main') ||
                                            document.querySelector('[role="main"]') ||
                                            document.querySelector('body');

                        if (mainContainer) {
                            // Look for elements that look like message content
                            // ChatGPT often uses divs with text content, sometimes in groups
                            const candidates = mainContainer.querySelectorAll('div, p, article');
                            const seenTexts = new Set();

                            candidates.forEach(el => {
                                // Skip if in nav/header/footer
                                if (el.closest('nav') || el.closest('header') || el.closest('footer')) {
                                    return;
                                }

                                const text = el.innerText || el.textContent || '';
                                const cleanText = text
                                    .replace(/Skip to content|ChatGPT|Log in|Sign up|Attach|Search|Create image|Voice/gi, '')
                                    .replace(/By messaging.*Privacy Policy\./g, '')
                                    .replace(/window\.__[a-zA-Z]+|requestAnimationFrame|Date\.now\(\)/g, '')
                                    .trim();

                                // Must be substantial content, not UI, not JS code
                                // Check it looks like human-readable text (has spaces, not all code)
                                const hasReadableText = cleanText.includes(' ') || cleanText.length > 50;
                                const isNotCode = !cleanText.match(/^[a-zA-Z_$][a-zA-Z0-9_$]*\s*[=\(\)]/) &&  // Not var assignments
                                                 !cleanText.match(/^\s*[\{\}\[\]\(\);,\.]+/);  // Not just symbols

                                if (cleanText.length > 30 &&
                                    hasReadableText &&
                                    isNotCode &&
                                    !cleanText.match(/^(Skip|Log in|Sign up|Attach|Search|Create|Voice|Cookie|Terms|Privacy)/i) &&
                                    !cleanText.match(/window\.__[a-zA-Z]+|requestAnimationFrame|Date\.now\(\)|__oai/i) &&
                                    !seenTexts.has(cleanText.substring(0, 100))) {

                                    seenTexts.add(cleanText.substring(0, 100));

                                    // Determine role - look for clues or use position
                                    let role = null;

                                    // Check for role indicators
                                    const parent = el.closest('[data-message-author-role]');
                                    if (parent) {
                                        role = parent.getAttribute('data-message-author-role');
                                    }

                                    // If no role found, alternate
                                    if (!role) {
                                        role = messages.length % 2 === 0 ? 'user' : 'assistant';
                                    } else if (role === 'system') {
                                        return;
                                    }

                                    // Normalize role
                                    if (role.toLowerCase().includes('user') || role === 'user') {
                                        role = 'user';
                                    } else {
                                        role = 'assistant';
                                    }

                                    messages.push({
                                        role: role,
                                        text: cleanText,
                                        index: messages.length,
                                    });
                                }
                            });
                        }
                    }

                    return {
                        messages: messages,
                        title: document.title || 'ChatGPT Conversation',
                        url: window.location.href,
                    };
                }
            """
            )

            # Check if we got conversation data from API responses
            conversation_from_api = None
            for resp in api_responses:
                data = resp.get("data", {})
                # Look for conversation structure in API response
                if isinstance(data, dict):
                    # Check for various possible structures
                    if (
                        "mapping" in data
                        or "messages" in data
                        or "conversation" in data
                    ):
                        conversation_from_api = data
                        break
                    # Check nested structures
                    for key, value in data.items():
                        if isinstance(value, dict) and (
                            "mapping" in value or "messages" in value
                        ):
                            conversation_from_api = value
                            break

            # If visible text was extracted, try to parse it as a fallback
            if visible_text and len(visible_text) > 100:
                # Filter out UI elements from visible text
                lines = [
                    line.strip() for line in visible_text.split("\n") if line.strip()
                ]
                content_lines = [
                    line
                    for line in lines
                    if len(line) > 20
                    and not line.startswith(
                        (
                            "Skip",
                            "ChatGPT",
                            "Log in",
                            "Sign up",
                            "Attach",
                            "Search",
                            "Create",
                            "Voice",
                            "By messaging",
                            "Cookie",
                            "Terms",
                            "Privacy",
                        )
                    )
                    and "window.__" not in line
                    and "requestAnimationFrame" not in line
                ]

                # If we found substantial content, use it
                if len(content_lines) > 2 and len("\n".join(content_lines)) > 100:
                    # Try to split into messages (alternating user/assistant)
                    fallback_messages = []
                    for idx, line in enumerate(content_lines):
                        # Skip very short lines that might be UI
                        if len(line) < 20:
                            continue
                        fallback_messages.append(
                            {
                                "role": "user" if idx % 2 == 0 else "assistant",
                                "text": line,
                                "index": len(fallback_messages),
                            }
                        )

                    if fallback_messages and (
                        not conversation_data.get("messages")
                        or len(conversation_data["messages"]) == 0
                    ):
                        conversation_data["messages"] = fallback_messages
                        print(
                            f"Using fallback text extraction: found {len(fallback_messages)} message blocks"
                        )

            browser.close()

            # If we got data from API, use it; otherwise use DOM extraction
            if conversation_from_api:
                # Convert API format to our expected format
                if "mapping" in conversation_from_api:
                    # Already in the right format
                    return {
                        "title": conversation_data.get("title", "ChatGPT Conversation"),
                        "messages": _extract_messages_from_mapping(
                            conversation_from_api
                        ),
                        "url": share_url,
                        "raw_data": conversation_from_api,
                    }
                elif "messages" in conversation_from_api:
                    return {
                        "title": conversation_data.get("title", "ChatGPT Conversation"),
                        "messages": conversation_from_api["messages"],
                        "url": share_url,
                    }

            return conversation_data

        except Exception as e:
            browser.close()
            raise Exception(f"Playwright scraping failed: {e}")


def scrape_with_apify(share_url: str, api_token: str | None = None) -> dict[str, Any]:
    """
    Scrape conversation using Apify's ChatGPT Conversation Scraper.
    
    Args:
        share_url: ChatGPT share URL
        api_token: Apify API token (optional, will try env var or 1Password)
        
    Returns:
        Dictionary with conversation data
        
    Raises:
        ImportError: If apify-client not installed
        ValueError: If API token not provided or found
        ValueError: If Apify scraping fails
    """
    global APIFY_AVAILABLE
    
    # Ensure apify-client is installed
    if not APIFY_AVAILABLE:
        if not ensure_package_installed("apify-client", "apify_client"):
            raise ImportError(
                "apify-client not installed and installation failed. "
                "Install manually with: pip install apify-client"
            )
        # Re-import after installation
        try:
            from apify_client import ApifyClient
            APIFY_AVAILABLE = True
        except ImportError:
            raise ImportError("apify-client installed but import failed")
    
    # Import after ensuring it's available
    from apify_client import ApifyClient

    # Get API token: try parameter, then env var, then 1Password
    if not api_token:
        api_token = os.getenv("APIFY_API_TOKEN")
    
    if not api_token:
        api_token = get_apify_token_from_1password()
    
    if not api_token:
        raise ValueError(
            "APIFY_API_TOKEN required. Set env var, pass api_token parameter, "
            "or configure in 1Password item 'Apify' with field 'API token'"
        )

    client = ApifyClient(api_token)

    print(f"Running Apify actor for: {share_url}")

    # Use the ChatGPT Conversation Scraper actor
    # Actor ID: straightforward_understanding/chatgpt-conversation-scraper
    run = client.actor(
        "straightforward_understanding/chatgpt-conversation-scraper"
    ).call(
        run_input={
            "startUrls": [{"url": share_url}],
        },
        timeout_secs=300,
    )

    # Wait for run to finish
    from time import sleep

    while client.run(run["id"]).get()["status"] not in [
        "SUCCEEDED",
        "FAILED",
        "ABORTED",
        "TIMED-OUT",
    ]:
        sleep(2)

    run_info = client.run(run["id"]).get()
    if run_info["status"] != "SUCCEEDED":
        raise ValueError(f"Apify run failed with status: {run_info['status']}")

    # Fetch results
    items = list(client.dataset(run["defaultDatasetId"]).iterate_items())

    if not items:
        raise ValueError("No conversation data extracted by Apify")

    # Apify chatgpt-conversation-scraper returns one dataset item per message
    # (role, content, messageIndex, conversationTitle, url, etc.)
    first = items[0]
    title = first.get("conversationTitle") or first.get("title") or "ChatGPT Conversation"
    messages = []
    for it in sorted(items, key=lambda x: x.get("messageIndex", 0)):
        role = it.get("role", "user")
        content = it.get("content") or it.get("text") or ""
        if content or it.get("messageIndex") is not None:
            messages.append({"role": role, "text": content, "content": content})
    return {"messages": messages, "title": title, "url": share_url}


def scrape_with_requests(share_url: str) -> dict[str, Any]:
    """
    Scrape conversation using requests and BeautifulSoup.
    
    Limited - ChatGPT shared pages are mostly JavaScript-rendered,
    but we can try to extract any server-rendered content.
    
    Args:
        share_url: ChatGPT share URL
        
    Returns:
        Dictionary with conversation data
        
    Raises:
        ImportError: If requests or beautifulsoup4 not installed
    """
    # Ensure packages are installed
    if not REQUESTS_AVAILABLE:
        if not ensure_package_installed("requests", "requests"):
            raise ImportError("requests not installed and installation failed")
    
    if not BEAUTIFULSOUP_AVAILABLE:
        if not ensure_package_installed("beautifulsoup4", "bs4"):
            raise ImportError("beautifulsoup4 not installed and installation failed")

    import requests
    from bs4 import BeautifulSoup

    print(f"Scraping with requests/BeautifulSoup: {share_url}")

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    }

    response = requests.get(share_url, headers=headers, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    # Try to find conversation data in script tags (sometimes pre-rendered)
    messages = []

    # Look for JSON data in script tags
    for script in soup.find_all("script"):
        if script.string:
            # Try to find conversation data
            if (
                "conversation" in script.string.lower()
                or "messages" in script.string.lower()
            ):
                try:
                    # Try to extract JSON
                    json_match = re.search(r'\{[^{}]*"messages"[^{}]*\}', script.string)
                    if json_match:
                        data = json.loads(json_match.group())
                        if "messages" in data:
                            messages.extend(data["messages"])
                except Exception:
                    pass

    # Fallback: extract visible text
    if not messages:
        # Remove script and style elements
        for element in soup(["script", "style", "nav", "header", "footer"]):
            element.decompose()

        # Get text blocks
        text_blocks = soup.find_all(["p", "div"], string=re.compile(r".{50,}"))
        for idx, block in enumerate(text_blocks):
            text = block.get_text(strip=True)
            if len(text) > 50:
                messages.append(
                    {
                        "role": "user" if idx % 2 == 0 else "assistant",
                        "text": text,
                        "index": idx,
                    }
                )

    return {
        "messages": messages,
        "title": soup.title.string if soup.title else "ChatGPT Conversation",
        "url": share_url,
    }


def convert_to_export_format(
    scraped_data: dict[str, Any], share_id: str
) -> dict[str, Any]:
    """
    Convert scraped data to ChatGPT export JSON format.
    
    Expected format has a 'mapping' structure with nodes containing messages.
    
    Args:
        scraped_data: Raw scraped data
        share_id: ChatGPT share ID
        
    Returns:
        Formatted conversation data in ChatGPT export format
    """
    # Handle different input formats
    messages = scraped_data.get("messages", [])

    # If we have raw_data with mapping, extract from that
    if "raw_data" in scraped_data and "mapping" in scraped_data["raw_data"]:
        messages = _extract_messages_from_mapping(scraped_data["raw_data"])
    elif "mapping" in scraped_data:
        messages = _extract_messages_from_mapping(scraped_data)

    # Create mapping structure
    mapping = {}
    current_time = int(time.time())

    for idx, msg in enumerate(messages):
        role = msg.get("role", "user")
        text = msg.get("text", "") or msg.get("content", "")

        if not text or len(text.strip()) < 1:
            continue

        # Create node ID
        node_id = f"node_{idx}"

        # Calculate timestamp (approximate - use current time minus offset for ordering)
        create_time = current_time - (len(messages) - idx) * 60  # 1 minute per message

        # Create message structure matching ChatGPT export format
        mapping[node_id] = {
            "id": node_id,
            "message": {
                "id": f"msg_{idx}",
                "author": {
                    "role": role,
                },
                "create_time": create_time,
                "content": {
                    "content_type": "text",
                    "parts": [text],
                },
            },
            "parent": f"node_{idx - 1}" if idx > 0 else None,
            "children": [f"node_{idx + 1}"] if idx < len(messages) - 1 else [],
        }

    # Find root node (first message)
    root_node_id = "node_0" if messages else None

    return {
        "title": scraped_data.get("title", "ChatGPT Conversation"),
        "create_time": current_time - len(messages) * 60 if messages else current_time,
        "update_time": current_time,
        "mapping": mapping,
        "current_node": root_node_id,
        "share_id": share_id,
    }


def save_conversation_json(data: dict[str, Any], output_path: Path) -> None:
    """
    Save conversation data to JSON file.
    
    Args:
        data: Conversation data to save
        output_path: Path to output file
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Saved conversation to: {output_path}")
