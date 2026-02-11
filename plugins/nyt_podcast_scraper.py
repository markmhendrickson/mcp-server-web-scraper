"""
New York Times podcast scraper plugin using Playwright.
"""

import asyncio
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

# Try to import playwright async API
PLAYWRIGHT_AVAILABLE = False
try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    pass

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from scraper_base import ScraperBase

# Try to import ensure_package_installed from scraper.py
try:
    from scraper import ensure_package_installed
except ImportError:
    # Fallback if scraper.py not available
    def ensure_package_installed(package_name: str, import_name: str | None = None) -> bool:
        """Fallback: just try to import."""
        if import_name is None:
            import_name = package_name
        try:
            __import__(import_name)
            return True
        except ImportError:
            return False


def extract_episode_id(url: str) -> str:
    """Extract episode identifier from NYT podcast URL."""
    # Support formats:
    # https://www.nytimes.com/2026/01/16/podcasts/jonathan-haidt-strikes-again-what-you-vibecoded-an-update-on-the-forkiverse.html
    # Extract the slug (last part before .html) or use full path as ID
    match = re.search(r"nytimes\.com/(\d{4}/\d{2}/\d{2}/podcasts/[^/]+)", url)
    if match:
        # Use date + slug as unique identifier
        return match.group(1).replace("/", "-")
    
    # Fallback: extract slug from URL
    match = re.search(r"podcasts/([^/]+)\.html", url)
    if match:
        return match.group(1)
    
    raise ValueError(f"Invalid NYT podcast URL format: {url}")


class NYTPodcastScraper(ScraperBase):
    """Scraper for New York Times podcast episodes using Playwright."""
    
    @property
    def source_name(self) -> str:
        return "nyt_podcast"
    
    @property
    def supported_methods(self) -> list[str]:
        return ["playwright"]  # Playwright is required for JavaScript-rendered content
    
    def can_handle(self, url: str) -> bool:
        """Check if URL is a NYT podcast URL."""
        return "nytimes.com" in url and "/podcasts/" in url
    
    def extract_id(self, url: str) -> str:
        """Extract episode ID from NYT podcast URL."""
        try:
            return extract_episode_id(url)
        except ValueError as e:
            raise ValueError(f"Invalid NYT podcast URL: {e}")
    
    def scrape(
        self,
        url: str,
        method: str = "auto",
        credentials: dict[str, str | None] | None = None,
    ) -> dict[str, Any]:
        """Scrape NYT podcast episode using Playwright."""
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
                from playwright.async_api import async_playwright as _async_playwright
                PLAYWRIGHT_AVAILABLE = True
            except ImportError:
                raise ImportError("playwright installed but import failed")
        else:
            from playwright.async_api import async_playwright as _async_playwright
        
        print(f"Scraping NYT podcast episode: {url}")
        
        # Run async Playwright in a new event loop (in a thread)
        async def _scrape_async():
            async with _async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                
                try:
                    # Navigate to podcast page
                    await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                    
                    # Wait for content to load - NYT pages need time for React to render
                    await page.wait_for_timeout(5000)
                    
                    # Try to wait for main content
                    try:
                        await page.wait_for_selector('article, main, h1, body', timeout=10000)
                    except:
                        pass
                    
                    # Wait for network to be idle (content loaded)
                    try:
                        await page.wait_for_load_state("networkidle", timeout=10000)
                    except:
                        pass
                    
                    # Wait a bit more for dynamic content
                    await page.wait_for_timeout(3000)
                    
                    # Check if page is behind paywall or has login prompt
                    page_text = await page.locator('body').inner_text()
                    is_paywalled = any(
                        phrase in page_text.lower() 
                        for phrase in ['subscribe', 'log in', 'create account', 'paywall', 'you\'ve reached your article limit']
                    )
                    
                    # Get page HTML for more thorough parsing
                    page_html = await page.content()
                    
                    # Save page HTML for debugging (first 10000 chars)
                    debug_html = page_html[:10000] if len(page_html) > 10000 else page_html
                    
                    # Extract episode title - try multiple strategies
                    title = None
                    title_selectors = [
                        'h1[data-testid="headline"]',
                        'h1[itemprop="headline"]',
                        'h1',
                        '[data-testid="headline"]',
                        'article h1',
                        'header h1',
                        'main h1',
                        '.headline',
                        '[class*="headline"]'
                    ]
                    for selector in title_selectors:
                        try:
                            title_elem = await page.query_selector(selector)
                            if title_elem:
                                title = await title_elem.inner_text()
                                title = title.strip()
                                # Filter out generic titles
                                if title and title not in ["The New York Times", "Podcasts", "Hard Fork"] and len(title) > 10:
                                    break
                        except:
                            continue
                    
                    # Fallback: try to get title from page title
                    if not title or title == "Unknown Episode":
                        page_title = await page.title()
                        if page_title:
                            # Extract from page title like "Hard Fork: Episode Title | The New York Times"
                            title_match = re.search(r'Hard Fork[:\s]+(.+?)\s*\||Hard Fork[:\s]+(.+?)$', page_title)
                            if title_match:
                                title = (title_match.group(1) or title_match.group(2)).strip()
                            elif page_title and page_title != "The New York Times":
                                # Use page title as fallback
                                title = page_title.split('|')[0].strip()
                    
                    # Fallback: extract from URL slug
                    if not title or title == "Unknown Episode":
                        url_match = re.search(r'podcasts/([^/]+)\.html', url)
                        if url_match:
                            slug = url_match.group(1)
                            # Convert slug to readable title
                            title = slug.replace('-', ' ').title()
                    
                    # Extract episode description/summary
                    description = None
                    description_selectors = [
                        '[data-testid="article-summary"]',
                        'p[data-testid="article-summary"]',
                        'article p',
                        '.summary',
                        '[class*="summary"]'
                    ]
                    for selector in description_selectors:
                        desc_elem = await page.query_selector(selector)
                        if desc_elem:
                            description = await desc_elem.inner_text()
                            description = description.strip()
                            if description and len(description) > 50:  # Ensure it's substantial
                                break
                    
                    # Extract publication date
                    date = None
                    date_selectors = [
                        'time[datetime]',
                        '[data-testid="timestamp"]',
                        'time',
                        '[class*="date"]',
                        '[class*="timestamp"]'
                    ]
                    for selector in date_selectors:
                        date_elem = await page.query_selector(selector)
                        if date_elem:
                            # Try to get datetime attribute first
                            date = await date_elem.get_attribute('datetime')
                            if not date:
                                date = await date_elem.inner_text()
                                date = date.strip()
                            if date:
                                break
                    
                    # Extract transcript - this is the main goal
                    transcript = None
                    transcript_selectors = [
                        '[data-testid="transcript"]',
                        '[class*="transcript"]',
                        '[id*="transcript"]',
                        'article section[aria-label*="transcript"]',
                        'div[class*="Transcript"]',
                        'section[class*="transcript"]'
                    ]
                    
                    # Method 1: Try specific transcript selectors
                    for selector in transcript_selectors:
                        try:
                            transcript_elem = await page.query_selector(selector)
                            if transcript_elem:
                                transcript = await transcript_elem.inner_text()
                                transcript = transcript.strip()
                                if transcript and len(transcript) > 100:  # Ensure it's substantial
                                    break
                        except:
                            continue
                    
                    # Method 2: Look for transcript button/link and click it if needed
                    if not transcript:
                        try:
                            transcript_button = await page.query_selector('button:has-text("Transcript"), a:has-text("Transcript"), [aria-label*="transcript" i]')
                            if transcript_button:
                                await transcript_button.click()
                                await page.wait_for_timeout(2000)
                                # Try selectors again after clicking
                                for selector in transcript_selectors:
                                    transcript_elem = await page.query_selector(selector)
                                    if transcript_elem:
                                        transcript = await transcript_elem.inner_text()
                                        transcript = transcript.strip()
                                        if transcript and len(transcript) > 100:
                                            break
                        except:
                            pass
                    
                    # Method 3: Search for transcript section by text in page content
                    if not transcript:
                        try:
                            body_locator = page.locator('body')
                            all_text = await body_locator.inner_text()
                            # Look for "Transcript" heading followed by content
                            # Try multiple patterns
                            patterns = [
                                r'(?:Transcript|Full Transcript|Episode Transcript)[:\s]*\n(.+?)(?:\n\n[A-Z]|\Z)',
                                r'(?:Show transcript|View transcript|Read transcript)[:\s]*\n(.+?)(?:\n\n|\Z)',
                                r'Transcript\s*\n(.+?)(?=\n\n[A-Z][a-z]+\s*:|$)',
                            ]
                            for pattern in patterns:
                                transcript_match = re.search(pattern, all_text, re.IGNORECASE | re.DOTALL | re.MULTILINE)
                                if transcript_match:
                                    transcript = transcript_match.group(1).strip()
                                    if len(transcript) > 200:  # Ensure it's substantial
                                        break
                        except:
                            pass
                    
                    # Method 4: Try to find article body and extract if it looks like a transcript
                    if not transcript:
                        try:
                            article_body = await page.query_selector('article, [role="article"], main, [class*="article"]')
                            if article_body:
                                body_text = await article_body.inner_text()
                                # If body text is very long and contains dialogue-like patterns, it might be a transcript
                                if len(body_text) > 2000:
                                    # Check for speaker patterns (common in transcripts)
                                    if re.search(r'[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*:', body_text):
                                        transcript = body_text
                                    # Also check for question/answer patterns
                                    elif '?' in body_text and ':' in body_text:
                                        # Might be interview/transcript format
                                        transcript = body_text
                        except:
                            pass
                    
                    # Method 5: Try to find transcript in expandable sections or details elements
                    if not transcript:
                        try:
                            # Look for details/summary elements that might contain transcript
                            details_elements = await page.query_selector_all('details, [class*="expand"], [class*="collapse"]')
                            for details in details_elements:
                                details_text = await details.inner_text()
                                if 'transcript' in details_text.lower() and len(details_text) > 500:
                                    # Try to expand it
                                    try:
                                        await details.click()
                                        await page.wait_for_timeout(1000)
                                        details_text = await details.inner_text()
                                    except:
                                        pass
                                    if len(details_text) > 500:
                                        transcript = details_text
                                        break
                        except:
                            pass
                    
                    # Extract audio player URL if available
                    audio_url = None
                    audio_selectors = [
                        'audio source[src]',
                        'audio[src]',
                        '[data-testid="audio-player"] source',
                        '[class*="audio"] source'
                    ]
                    for selector in audio_selectors:
                        audio_elem = await page.query_selector(selector)
                        if audio_elem:
                            audio_url = await audio_elem.get_attribute('src')
                            if audio_url:
                                break
                    
                    # Extract podcast show name
                    show_name = None
                    show_selectors = [
                        '[data-testid="podcast-show"]',
                        'a[href*="/podcasts/"]',
                        '[class*="podcast"]',
                        '[class*="show"]'
                    ]
                    for selector in show_selectors:
                        show_elem = await page.query_selector(selector)
                        if show_elem:
                            show_name = await show_elem.inner_text()
                            show_name = show_name.strip()
                            if show_name and len(show_name) < 100:  # Reasonable length
                                break
                    
                    # Extract episode duration if available
                    duration = None
                    duration_selectors = [
                        '[data-testid="duration"]',
                        '[class*="duration"]',
                        'time[data-duration]'
                    ]
                    for selector in duration_selectors:
                        duration_elem = await page.query_selector(selector)
                        if duration_elem:
                            duration = await duration_elem.inner_text()
                            duration = duration.strip()
                            if duration:
                                break
                    
                    # Extract any available text content as fallback for transcript
                    if not transcript:
                        try:
                            # Get all text from main content area
                            main_content = await page.query_selector('main, article, [role="main"], [class*="article"]')
                            if main_content:
                                main_text = await main_content.inner_text()
                                # If it's substantial and looks like content (not just navigation)
                                if len(main_text) > 500:
                                    # Filter out navigation and UI elements
                                    filtered_text = '\n'.join([
                                        line for line in main_text.split('\n')
                                        if line.strip() 
                                        and not line.strip().startswith('Skip')
                                        and not line.strip().startswith('Subscribe')
                                        and len(line.strip()) > 20
                                    ])
                                    if len(filtered_text) > 500:
                                        transcript = filtered_text
                        except:
                            pass
                    
                    # If still no transcript, try getting all visible text
                    if not transcript:
                        try:
                            # Get all paragraphs and divs with substantial text
                            all_paragraphs = await page.query_selector_all('p, div[class*="text"], div[class*="content"]')
                            transcript_parts = []
                            for para in all_paragraphs:
                                try:
                                    para_text = await para.inner_text()
                                    if para_text and len(para_text.strip()) > 50:
                                        # Check if it's not navigation/UI
                                        if not any(ui_word in para_text.lower() for ui_word in ['subscribe', 'log in', 'cookie', 'privacy policy']):
                                            transcript_parts.append(para_text.strip())
                                except:
                                    continue
                            if transcript_parts:
                                transcript = '\n\n'.join(transcript_parts)
                        except:
                            pass
                    
                    # Extract show name from URL or page if not found
                    if not show_name:
                        # Try to extract from URL path
                        show_match = re.search(r'/podcasts/([^/]+)/', url)
                        if show_match:
                            show_slug = show_match.group(1)
                            # Common NYT podcast names
                            if 'hard-fork' in show_slug or 'hardfork' in url.lower():
                                show_name = "Hard Fork"
                            else:
                                show_name = show_slug.replace('-', ' ').title()
                    
                    # Extract date from URL if not found
                    if not date:
                        date_match = re.search(r'/(\d{4})/(\d{2})/(\d{2})/', url)
                        if date_match:
                            date = f"{date_match.group(1)}-{date_match.group(2)}-{date_match.group(3)}"
                    
                    await browser.close()
                    
                    return {
                        "title": title or "Unknown Episode",
                        "show_name": show_name,
                        "description": description,
                        "date": date,
                        "duration": duration,
                        "transcript": transcript,
                        "audio_url": audio_url,
                        "url": url,
                        "scraped_at": int(time.time()),
                        "is_paywalled": is_paywalled,
                        "page_text_preview": page_text[:1000] if page_text else None,  # First 1000 chars for debugging
                        "page_html_preview": debug_html,  # HTML preview for debugging
                    }
                    
                except Exception as e:
                    await browser.close()
                    raise ValueError(f"Failed to scrape NYT podcast episode: {str(e)}")
        
        # Run async function in a completely isolated thread with new event loop
        def _run_async_in_thread():
            # This function runs in a separate thread with no event loop
            # Create a brand new event loop for this thread
            import asyncio
            import threading
            
            # Get the current thread's event loop (should be None in a new thread)
            try:
                existing_loop = asyncio.get_event_loop()
                if existing_loop.is_running():
                    # This shouldn't happen in a new thread, but handle it
                    raise RuntimeError("Event loop already running in thread")
            except RuntimeError:
                # No event loop exists - this is what we want
                pass
            
            # Create and set a new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                # Run the async scrape function
                return loop.run_until_complete(_scrape_async())
            finally:
                # Clean up
                try:
                    # Cancel any remaining tasks
                    pending = asyncio.all_tasks(loop)
                    for task in pending:
                        task.cancel()
                    # Run until all tasks are cancelled
                    if pending:
                        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                except:
                    pass
                finally:
                    loop.close()
                    asyncio.set_event_loop(None)
        
        # Check if we're in an async context
        try:
            # If we can get a running loop, we're in async context - use thread
            asyncio.get_running_loop()
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(_run_async_in_thread)
                return future.result(timeout=120)  # 2 minute timeout
        except RuntimeError:
            # No event loop running - can run directly
            return _run_async_in_thread()
    
    def normalize_output(
        self,
        scraped_data: dict[str, Any],
        source_id: str,
    ) -> dict[str, Any]:
        """Normalize NYT podcast data to common format."""
        return {
            "source": "nyt_podcast",
            "episode_id": source_id,
            "title": scraped_data.get("title", "Unknown Episode"),
            "show_name": scraped_data.get("show_name"),
            "description": scraped_data.get("description"),
            "date": scraped_data.get("date"),
            "duration": scraped_data.get("duration"),
            "transcript": scraped_data.get("transcript"),
            "audio_url": scraped_data.get("audio_url"),
            "url": scraped_data.get("url", ""),
            "scraped_at": scraped_data.get("scraped_at", int(time.time())),
            "has_transcript": bool(scraped_data.get("transcript")),
            "is_paywalled": scraped_data.get("is_paywalled", False),
            "page_text_preview": scraped_data.get("page_text_preview"),
            "raw_data": scraped_data,  # Keep original for reference
        }
    
    def get_storage_path(self, source_id: str, data_dir: Path) -> Path:
        """Get storage path for NYT podcast episode."""
        return data_dir / "imports" / "nyt_podcast" / f"episode_{source_id}.json"
