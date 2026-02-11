"""
Metacast podcast scraper plugin using Playwright.
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
    """Extract episode identifier from Metacast URL."""
    # Support formats:
    # https://metacast.app/podcast/hard-fork/r6XOQDHi/jonathan-haidt-strikes-again-what-you-vibecoded-an-update-on-the-forkiverse/s9ddEA9t
    # Extract the episode ID (last segment) or use full path as ID
    match = re.search(r"metacast\.app/podcast/[^/]+/[^/]+/([^/]+)/([^/]+)", url)
    if match:
        # Use episode slug + ID as unique identifier
        return f"{match.group(1)}_{match.group(2)}"
    
    # Fallback: extract last segment
    match = re.search(r"metacast\.app/podcast/.+/([^/]+)$", url)
    if match:
        return match.group(1)
    
    raise ValueError(f"Invalid Metacast URL format: {url}")


class MetacastScraper(ScraperBase):
    """Scraper for Metacast podcast episodes using Playwright."""
    
    @property
    def source_name(self) -> str:
        return "metacast"
    
    @property
    def supported_methods(self) -> list[str]:
        return ["playwright"]  # Playwright is required for JavaScript-rendered content
    
    def can_handle(self, url: str) -> bool:
        """Check if URL is a Metacast podcast URL."""
        return "metacast.app" in url and "/podcast/" in url
    
    def extract_id(self, url: str) -> str:
        """Extract episode ID from Metacast URL."""
        try:
            return extract_episode_id(url)
        except ValueError as e:
            raise ValueError(f"Invalid Metacast URL: {e}")
    
    def scrape(
        self,
        url: str,
        method: str = "auto",
        credentials: dict[str, str | None] | None = None,
    ) -> dict[str, Any]:
        """Scrape Metacast podcast episode using Playwright."""
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
        
        print(f"Scraping Metacast podcast episode: {url}")
        
        # Run async function in a completely isolated thread with new event loop
        async def _scrape_async():
            async with _async_playwright() as p:
                # Use headless=False initially to see what's happening, then switch to True
                # For now, keep headless=True but add better user agent
                browser = await p.chromium.launch(
                    headless=True,
                    args=['--disable-blink-features=AutomationControlled']
                )
                page = await browser.new_page()
                
                # Set a realistic user agent
                await page.set_extra_http_headers({
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                })
                
                try:
                    # Navigate to Metacast page
                    await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                    
                    # Wait for content to load - Metacast pages need time for React to render
                    await page.wait_for_timeout(8000)
                    
                    # Wait for main content
                    try:
                        await page.wait_for_selector('main', timeout=20000)
                    except:
                        pass
                    
                    # Wait for network to be idle
                    try:
                        await page.wait_for_load_state("networkidle", timeout=20000)
                    except:
                        pass
                    
                    # Additional wait for dynamic content - Metacast needs extra time
                    await page.wait_for_timeout(10000)
                    
                    # Try to wait for transcript section specifically
                    try:
                        await page.wait_for_selector('section:has-text("Transcript"), article', timeout=10000)
                    except:
                        pass
                    
                    await page.wait_for_timeout(3000)
                    
                    # Try to wait for specific Metacast content elements
                    try:
                        # Wait for any content to appear - try multiple selectors
                        selectors_to_wait = [
                            'h1',
                            '[class*="episode"]',
                            '[class*="podcast"]',
                            'main',
                            'article',
                            '[role="main"]',
                            '[data-testid]'
                        ]
                        for selector in selectors_to_wait:
                            try:
                                await page.wait_for_selector(selector, timeout=5000)
                                break
                            except:
                                continue
                    except:
                        pass
                    
                    # Wait for React/hydration to complete
                    try:
                        # Wait for React to hydrate by checking for interactive elements
                        await page.wait_for_function(
                            "document.querySelector('h1, main, article') !== null",
                            timeout=10000
                        )
                    except:
                        pass
                    
                    # Scroll to transcript section specifically
                    try:
                        # Find transcript heading and scroll to it
                        transcript_heading = await page.query_selector('h2:has-text("Transcript"), h3:has-text("Transcript"), [role="heading"]:has-text("Transcript")')
                        if transcript_heading:
                            await transcript_heading.scroll_into_view_if_needed()
                            await page.wait_for_timeout(3000)
                    except:
                        pass
                    
                    # Scroll multiple times to trigger lazy loading
                    for i in range(5):
                        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        await page.wait_for_timeout(2000)
                        await page.evaluate("window.scrollTo(0, 0)")
                        await page.wait_for_timeout(1000)
                    
                    # Try scrolling to middle as well
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
                    await page.wait_for_timeout(3000)
                    
                    # Scroll back to top and wait
                    await page.evaluate("window.scrollTo(0, 0)")
                    await page.wait_for_timeout(2000)
                    
                    # Get page HTML and text for debugging and extraction
                    page_html = await page.content()
                    page_text = await page.locator('body').inner_text()
                    
                    # Save debug info
                    debug_info = {
                        "page_title": await page.title(),
                        "page_text_length": len(page_text) if page_text else 0,
                        "page_html_length": len(page_html) if page_html else 0,
                        "page_text_preview": page_text[:2000] if page_text else None,
                    }
                    
                    # Extract episode title - Metacast has it in main > section > heading
                    # Use JavaScript for more reliable extraction
                    title = None
                    try:
                        title_from_js = await page.evaluate("""
                            () => {
                                // Try to find h1 in first section of main
                                const main = document.querySelector('main');
                                if (main) {
                                    const firstSection = main.querySelector('section');
                                    if (firstSection) {
                                        const h1 = firstSection.querySelector('h1');
                                        if (h1) {
                                            return h1.innerText || h1.textContent;
                                        }
                                    }
                                    // Fallback: any h1 in main
                                    const h1 = main.querySelector('h1');
                                    if (h1) {
                                        return h1.innerText || h1.textContent;
                                    }
                                }
                                return null;
                            }
                        """)
                        if title_from_js and title_from_js.strip():
                            title = title_from_js.strip()
                    except:
                        pass
                    
                    # Fallback to DOM queries
                    if not title:
                        title_selectors = [
                            'main section:first-of-type h1',
                            'main h1',
                            'h1',
                            '[role="heading"][aria-level="1"]'
                        ]
                        for selector in title_selectors:
                            try:
                                title_elem = await page.query_selector(selector)
                                if title_elem:
                                    title = await title_elem.inner_text()
                                    title = title.strip()
                                    # Filter out generic titles
                                    if title and len(title) > 5 and title.lower() not in ['metacast.app', 'metacast', 'podcast']:
                                        break
                            except:
                                continue
                    
                    # Fallback: try to get from page title
                    if not title or title.lower() in ['metacast.app', 'metacast']:
                        page_title = await page.title()
                        if page_title and page_title.lower() not in ['metacast.app', 'metacast']:
                            # Extract from page title (format: "Title | Show - Metacast")
                            if '|' in page_title:
                                title = page_title.split('|')[0].strip()
                            else:
                                title = page_title.split('-')[0].strip() if '-' in page_title else page_title.strip()
                    
                    # Fallback: extract from URL slug
                    if not title or title.lower() in ['metacast.app', 'metacast']:
                        url_match = re.search(r'/([^/]+)/([^/]+)$', url)
                        if url_match:
                            slug = url_match.group(1)
                            # Convert slug to readable title
                            title = slug.replace('-', ' ').title()
                    
                    # Debug: log what we found (these print statements go to stderr, visible in server logs)
                    try:
                        page_title_actual = await page.title()
                        print(f"DEBUG: Page title from browser: {page_title_actual}", file=sys.stderr)
                        print(f"DEBUG: Page text length: {len(page_text) if page_text else 0}", file=sys.stderr)
                        print(f"DEBUG: Page text preview (first 1000 chars): {page_text[:1000] if page_text else 'None'}", file=sys.stderr)
                    except:
                        pass
                    
                    # Extract podcast show name
                    show_name = None
                    show_selectors = [
                        'a[href*="/podcast/"]',
                        '[data-testid="show-name"]',
                        '.podcast-name',
                        '[class*="podcast"]',
                        '[class*="show"]',
                        'h2, h3'
                    ]
                    for selector in show_selectors:
                        try:
                            show_elem = await page.query_selector(selector)
                            if show_elem:
                                show_text = await show_elem.inner_text()
                                show_text = show_text.strip()
                                # Filter out episode titles
                                if show_text and len(show_text) < 100 and show_text != title:
                                    show_name = show_text
                                    break
                        except:
                            continue
                    
                    # Extract episode description
                    description = None
                    description_selectors = [
                        '[data-testid="description"]',
                        '.episode-description',
                        '[class*="description"]',
                        'p[class*="summary"]',
                        'article p'
                    ]
                    for selector in description_selectors:
                        try:
                            desc_elem = await page.query_selector(selector)
                            if desc_elem:
                                description = await desc_elem.inner_text()
                                description = description.strip()
                                if description and len(description) > 50:
                                    break
                        except:
                            continue
                    
                    # Extract transcript - this is the main goal
                    # Metacast has transcript in: main > section with heading "Transcript ✨" > article
                    transcript = None
                    
                    # Method 1: Find the Transcript section and extract the article inside it using JavaScript
                    try:
                        # Use JavaScript to find the transcript section more reliably
                        # Try multiple times as content may load progressively
                        for attempt in range(3):
                            transcript_data = await page.evaluate("""
                                () => {
                                    // Find all sections in main
                                    const sections = document.querySelectorAll('main section');
                                    for (const section of sections) {
                                        // Look for heading with "Transcript" text
                                        const headings = section.querySelectorAll('h2, h3, [role="heading"]');
                                        for (const heading of headings) {
                                            const headingText = heading.textContent || heading.innerText || '';
                                            if (headingText.toLowerCase().includes('transcript')) {
                                                // Found transcript section! Get the article
                                                const article = section.querySelector('article');
                                                if (article) {
                                                    // Simply get all text content from the article
                                                    const text = article.innerText || article.textContent || '';
                                                    if (text && text.length > 200) {
                                                        return text;
                                                    }
                                                }
                                            }
                                        }
                                    }
                                    // Fallback: try to find any article in main that might be transcript
                                    const main = document.querySelector('main');
                                    if (main) {
                                        const articles = main.querySelectorAll('article');
                                        for (const article of articles) {
                                            const text = article.innerText || article.textContent || '';
                                            // Check if it looks like a transcript (has section markers like ¶, is long)
                                            if (text && text.length > 1000 && (text.includes('¶') || text.includes('⁠') || article.querySelectorAll('h2, h3, h4, a[href*="#"]').length > 5)) {
                                                return text;
                                            }
                                        }
                                    }
                                    return null;
                                }
                            """)
                            if transcript_data and len(transcript_data.strip()) > 200:
                                transcript = transcript_data.strip()
                                break
                            # Wait a bit more before next attempt
                            await page.wait_for_timeout(2000)
                    except Exception as e:
                        print(f"DEBUG: Method 1 JS eval error: {e}", file=sys.stderr)
                        pass
                    
                    # Method 1b: Try DOM query if JS eval didn't work
                    if not transcript:
                        try:
                            # Look for section with heading containing "Transcript"
                            sections = await page.query_selector_all('main section')
                            for section in sections:
                                try:
                                    # Check if this section has a "Transcript" heading
                                    heading = await section.query_selector('h2, h3, [role="heading"]')
                                    if heading:
                                        heading_text = await heading.inner_text()
                                        if 'transcript' in heading_text.lower():
                                            # Found transcript section! Extract the article inside
                                            article = await section.query_selector('article')
                                            if article:
                                                transcript = await article.inner_text()
                                                transcript = transcript.strip()
                                                if transcript and len(transcript) > 200:
                                                    break
                                except:
                                    continue
                        except:
                            pass
                    
                    # Method 2: Try all articles in main and find the one with transcript content
                    if not transcript:
                        try:
                            transcript_data = await page.evaluate("""
                                () => {
                                    const main = document.querySelector('main');
                                    if (!main) return null;
                                    
                                    // Get all articles
                                    const articles = main.querySelectorAll('article');
                                    for (const article of articles) {
                                        const text = article.innerText || article.textContent || '';
                                        // Check if it looks like a transcript (has section markers, is long, has headings)
                                        if (text.length > 1000 && (text.includes('¶') || text.includes('⁠') || article.querySelectorAll('h2, h3, h4').length > 5)) {
                                            return text;
                                        }
                                    }
                                    return null;
                                }
                            """)
                            if transcript_data and len(transcript_data.strip()) > 200:
                                transcript = transcript_data.strip()
                        except Exception as e:
                            print(f"DEBUG: Method 2 error: {e}", file=sys.stderr)
                            pass
                    
                    # Method 2b: Try DOM query as fallback
                    if not transcript:
                        try:
                            # Try to find article that's a sibling or child of a heading with "Transcript"
                            sections = await page.query_selector_all('main section')
                            for section in sections:
                                heading = await section.query_selector('h2, h3')
                                if heading:
                                    heading_text = await heading.inner_text()
                                    if 'transcript' in heading_text.lower():
                                        article = await section.query_selector('article')
                                        if article:
                                            transcript = await article.inner_text()
                                            if transcript and len(transcript.strip()) > 200:
                                                transcript = transcript.strip()
                                                break
                        except Exception as e:
                            print(f"DEBUG: Method 2b error: {e}", file=sys.stderr)
                            pass
                    
                    # Method 3: Try specific transcript selectors
                    if not transcript:
                        transcript_selectors = [
                            'section:has-text("Transcript") article',
                            '[role="article"]',
                            '[class*="transcript"] article',
                            'article[class*="transcript"]'
                        ]
                        
                        for selector in transcript_selectors:
                            try:
                                transcript_elem = await page.query_selector(selector)
                                if transcript_elem:
                                    transcript_text = await transcript_elem.inner_text()
                                    transcript_text = transcript_text.strip()
                                    # Check if it's substantial and looks like a transcript
                                    if transcript_text and len(transcript_text) > 500:
                                        # Check for transcript-like patterns (headings, dialogue)
                                        if '¶' in transcript_text or ':' in transcript_text:
                                            transcript = transcript_text
                                            break
                            except:
                                continue
                    
                    # Method 3: Search for transcript in page text
                    if not transcript:
                        try:
                            body_locator = page.locator('body')
                            all_text = await body_locator.inner_text()
                            
                            # Look for "Transcript" heading followed by content
                            patterns = [
                                r'(?:Transcript|Full Transcript|Episode Transcript|Show Transcript)[:\s]*\n(.+?)(?:\n\n[A-Z]|\Z)',
                                r'Transcript\s*\n(.+?)(?=\n\n[A-Z][a-z]+\s*:|$)',
                                r'Show transcript[:\s]*\n(.+?)(?:\n\n|\Z)',
                            ]
                            for pattern in patterns:
                                transcript_match = re.search(pattern, all_text, re.IGNORECASE | re.DOTALL | re.MULTILINE)
                                if transcript_match:
                                    transcript = transcript_match.group(1).strip()
                                    if len(transcript) > 200:
                                        break
                        except:
                            pass
                    
                    # Method 4: Try to find main content area and extract if it looks like a transcript
                    if not transcript:
                        try:
                            main_content = await page.query_selector('main, article, [role="main"], [class*="content"], [class*="episode"]')
                            if main_content:
                                main_text = await main_content.inner_text()
                                # If it's very long and contains dialogue patterns, it might be a transcript
                                if len(main_text) > 2000:
                                    # Check for speaker patterns (common in transcripts)
                                    if re.search(r'[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*:', main_text):
                                        transcript = main_text
                                    # Also check for question/answer patterns
                                    elif '?' in main_text and ':' in main_text and main_text.count(':') > 10:
                                        transcript = main_text
                        except:
                            pass
                    
                    # Method 6: Get all text content and filter for transcript-like content
                    if not transcript:
                        try:
                            # Get all paragraphs and divs with substantial text
                            all_text_elements = await page.query_selector_all('p, div, section, article, span')
                            transcript_parts = []
                            seen_texts = set()
                            
                            for elem in all_text_elements:
                                try:
                                    elem_text = await elem.inner_text()
                                    elem_text = elem_text.strip()
                                    
                                    # Skip if too short or already seen
                                    if not elem_text or len(elem_text) < 50 or elem_text in seen_texts:
                                        continue
                                    
                                    # Check if it looks like transcript content
                                    has_dialogue = ':' in elem_text or '?' in elem_text
                                    has_speaker = re.search(r'[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*:', elem_text)
                                    # Not navigation/UI
                                    is_not_ui = not any(ui_word in elem_text.lower() for ui_word in [
                                        'subscribe', 'log in', 'cookie', 'privacy policy', 'terms',
                                        'skip to', 'menu', 'navigation', 'footer', 'header', 'metacast.app'
                                    ])
                                    
                                    # Check if it's substantial content
                                    if len(elem_text) > 100 and is_not_ui:
                                        # If it has dialogue markers or speaker patterns, it's likely transcript
                                        if has_dialogue and (has_speaker or len(elem_text) > 200):
                                            transcript_parts.append(elem_text)
                                            seen_texts.add(elem_text)
                                except:
                                    continue
                            
                            if transcript_parts:
                                # Join and deduplicate
                                transcript = '\n\n'.join(transcript_parts)
                        except Exception as e:
                            print(f"DEBUG: Error in Method 6: {e}", file=sys.stderr)
                            pass
                    
                    # Method 7: If still no transcript, try to extract from the entire page text
                    if not transcript and page_text:
                        try:
                            # Look for large blocks of text that might be the transcript
                            # Split by double newlines to find sections
                            sections = page_text.split('\n\n')
                            transcript_sections = []
                            
                            for section in sections:
                                section = section.strip()
                                # Look for sections that are substantial and have dialogue patterns
                                if len(section) > 500:
                                    # Check for speaker patterns or dialogue
                                    if re.search(r'[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*:', section) or \
                                       (section.count(':') > 5 and section.count('?') > 2):
                                        # Not UI/navigation
                                        if not any(ui_word in section.lower() for ui_word in [
                                            'subscribe', 'log in', 'cookie', 'privacy', 'terms', 'menu'
                                        ]):
                                            transcript_sections.append(section)
                            
                            if transcript_sections:
                                transcript = '\n\n'.join(transcript_sections)
                        except Exception as e:
                            print(f"DEBUG: Error in Method 7: {e}", file=sys.stderr)
                            pass
                    
                    # Method 5: Look for expandable sections (details/summary)
                    if not transcript:
                        try:
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
                    
                    # Extract episode date
                    date = None
                    date_selectors = [
                        'time[datetime]',
                        '[data-testid="date"]',
                        'time',
                        '[class*="date"]',
                        '[class*="published"]'
                    ]
                    for selector in date_selectors:
                        try:
                            date_elem = await page.query_selector(selector)
                            if date_elem:
                                date = await date_elem.get_attribute('datetime')
                                if not date:
                                    date = await date_elem.inner_text()
                                    date = date.strip()
                                if date:
                                    break
                        except:
                            continue
                    
                    # Extract episode duration
                    duration = None
                    duration_selectors = [
                        '[data-testid="duration"]',
                        '[class*="duration"]',
                        'time[data-duration]',
                        '[class*="length"]'
                    ]
                    for selector in duration_selectors:
                        try:
                            duration_elem = await page.query_selector(selector)
                            if duration_elem:
                                duration = await duration_elem.inner_text()
                                duration = duration.strip()
                                if duration:
                                    break
                        except:
                            continue
                    
                    # Extract audio URL if available
                    audio_url = None
                    audio_selectors = [
                        'audio source[src]',
                        'audio[src]',
                        '[data-testid="audio"] source',
                        '[class*="audio"] source',
                        'a[href*=".mp3"], a[href*=".m4a"], a[href*=".ogg"]'
                    ]
                    for selector in audio_selectors:
                        try:
                            audio_elem = await page.query_selector(selector)
                            if audio_elem:
                                audio_url = await audio_elem.get_attribute('src') or await audio_elem.get_attribute('href')
                                if audio_url:
                                    break
                        except:
                            continue
                    
                    # If we still don't have a good title, try extracting from page text
                    if not title or title.lower() in ['metacast.app', 'metacast']:
                        # Look for the largest heading in the page text
                        lines = page_text.split('\n')
                        for line in lines[:20]:  # Check first 20 lines
                            line = line.strip()
                            if line and len(line) > 10 and len(line) < 200:
                                # Check if it looks like a title (not navigation)
                                if not any(nav_word in line.lower() for nav_word in ['skip', 'menu', 'subscribe', 'log in']):
                                    title = line
                                    break
                    
                    # Final attempt: Get ALL text from main and filter for transcript
                    if not transcript and page_text:
                        try:
                            # Look for text after "Transcript" heading
                            transcript_start = page_text.lower().find('transcript')
                            if transcript_start > 0:
                                # Get text after "Transcript" heading
                                transcript_candidate = page_text[transcript_start:]
                                # Find where transcript section ends (look for next major section or end)
                                # Try to extract up to a reasonable length
                                lines_after_transcript = transcript_candidate.split('\n')
                                transcript_lines = []
                                for line in lines_after_transcript[1:]:  # Skip the "Transcript" heading itself
                                    line = line.strip()
                                    if line:
                                        # Stop if we hit navigation/footer content
                                        if any(stop_word in line.lower() for stop_word in ['learn more', 'open in metacast', 'metacast: podcast', '© 2026']):
                                            break
                                        transcript_lines.append(line)
                                
                                if transcript_lines:
                                    transcript = '\n'.join(transcript_lines)
                                    # Clean up - remove very short lines that are likely UI
                                    transcript = '\n'.join([line for line in transcript.split('\n') if len(line.strip()) > 5])
                        except Exception as e:
                            print(f"DEBUG: Final transcript extraction error: {e}", file=sys.stderr)
                            pass
                    
                    await browser.close()
                    
                    result = {
                        "title": title or "Unknown Episode",
                        "show_name": show_name,
                        "description": description,
                        "date": date,
                        "duration": duration,
                        "transcript": transcript,
                        "audio_url": audio_url,
                        "url": url,
                        "scraped_at": int(time.time()),
                    }
                    
                    # Add debug info to help troubleshoot
                    result.update(debug_info)
                    
                    return result
                    
                except Exception as e:
                    await browser.close()
                    raise ValueError(f"Failed to scrape Metacast episode: {str(e)}")
        
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
        """Normalize Metacast data to common format."""
        normalized = {
            "source": "metacast",
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
            "raw_data": scraped_data,  # Keep original for reference (includes all debug fields)
        }
        
        # Include debug fields if present
        if "page_text_preview" in scraped_data:
            normalized["page_text_preview"] = scraped_data["page_text_preview"]
        if "page_title" in scraped_data:
            normalized["page_title"] = scraped_data["page_title"]
        if "page_text_length" in scraped_data:
            normalized["page_text_length"] = scraped_data["page_text_length"]
        
        return normalized
    
    def get_storage_path(self, source_id: str, data_dir: Path) -> Path:
        """Get storage path for Metacast episode."""
        return data_dir / "imports" / "metacast" / f"episode_{source_id}.json"
