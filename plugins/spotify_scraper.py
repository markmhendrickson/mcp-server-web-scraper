"""
Spotify scraper plugin using Playwright.
"""

import json
import re
import sys
import time
from pathlib import Path
from typing import Any

# Try to import playwright
PLAYWRIGHT_AVAILABLE = False
try:
    from playwright.sync_api import sync_playwright
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


def extract_playlist_id(url: str) -> str:
    """Extract playlist ID from Spotify URL."""
    # Support formats:
    # https://open.spotify.com/playlist/3i0FY58V7n8XIUyWDm3AYA
    # https://open.spotify.com/playlist/3i0FY58V7n8XIUyWDm3AYA?si=...
    match = re.search(r"open\.spotify\.com/playlist/([a-zA-Z0-9]+)", url)
    if not match:
        raise ValueError(f"Invalid Spotify playlist URL format: {url}")
    return match.group(1)


class SpotifyScraper(ScraperBase):
    """Scraper for Spotify playlists using Playwright."""
    
    @property
    def source_name(self) -> str:
        return "spotify"
    
    @property
    def supported_methods(self) -> list[str]:
        return ["playwright"]  # Playwright is required for JavaScript-rendered content
    
    def can_handle(self, url: str) -> bool:
        """Check if URL is a Spotify playlist URL."""
        return "open.spotify.com/playlist/" in url
    
    def extract_id(self, url: str) -> str:
        """Extract playlist ID from Spotify URL."""
        try:
            return extract_playlist_id(url)
        except ValueError as e:
            raise ValueError(f"Invalid Spotify URL: {e}")
    
    def scrape(
        self,
        url: str,
        method: str = "auto",
        credentials: dict[str, str | None] | None = None,
    ) -> dict[str, Any]:
        """Scrape Spotify playlist using Playwright."""
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
                from playwright.sync_api import sync_playwright as _sync_playwright
                PLAYWRIGHT_AVAILABLE = True
            except ImportError:
                raise ImportError("playwright installed but import failed")
        else:
            from playwright.sync_api import sync_playwright as _sync_playwright
        
        print(f"Scraping Spotify playlist: {url}")
        
        with _sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            # Intercept network responses to find playlist data API
            api_responses = []
            
            def handle_response(response):
                url_resp = response.url
                # Look for Spotify API endpoints that might contain playlist data
                if any(
                    keyword in url_resp.lower()
                    for keyword in ["api.spotify.com", "spclient.wg.spotify.com", "playlist", "v1"]
                ):
                    try:
                        # Try to get JSON response
                        content_type = response.headers.get("content-type", "")
                        if "application/json" in content_type or "text/json" in content_type:
                            try:
                                api_responses.append({"url": url_resp, "data": response.json()})
                            except Exception:
                                pass
                    except Exception:
                        pass
            
            page.on("response", handle_response)
            
            try:
                # Navigate to playlist page
                page.goto(url, wait_until="networkidle", timeout=60000)
                
                # Wait a bit for API calls to complete
                page.wait_for_timeout(3000)
                
                # Try to get total track count from the page
                total_tracks_from_page = None
                try:
                    # Look for track count in various places
                    count_selectors = [
                        'span:has-text("songs")',
                        'span:has-text("tracks")',
                        '[data-testid="entityTitle"] + div span',
                        'button[aria-label*="song"]',
                        'button[aria-label*="track"]'
                    ]
                    for selector in count_selectors:
                        elem = page.query_selector(selector)
                        if elem:
                            text = elem.inner_text()
                            # Extract number from text like "25 songs" or "1,234 tracks"
                            import re
                            match = re.search(r'([\d,]+)', text.replace(',', ''))
                            if match:
                                total_tracks_from_page = int(match.group(1))
                                print(f"  Found total track count on page: {total_tracks_from_page}")
                                break
                except Exception as e:
                    print(f"  Could not extract total track count: {e}")
                
                # Scroll to load all tracks (Spotify uses lazy loading)
                print("Scrolling to load all tracks...")
                
                # Try to find and scroll the tracklist container specifically
                tracklist_selectors = [
                    'div[data-testid="playlist-tracklist"]',
                    'div[role="grid"]',
                    'div[data-testid="tracklist"]',
                    'main section[aria-label*="track"]',
                    'div[role="listbox"]'
                ]
                
                tracklist_container = None
                for selector in tracklist_selectors:
                    tracklist_container = page.query_selector(selector)
                    if tracklist_container:
                        print(f"  Found tracklist container: {selector}")
                        break
                
                scroll_attempts = 0
                max_scroll_attempts = 200  # Allow more attempts for long playlists
                last_track_count = 0
                no_change_count = 0
                api_responses_before = len(api_responses)
                
                while scroll_attempts < max_scroll_attempts:
                    # Try multiple scrolling strategies
                    if tracklist_container:
                        # Strategy 1: Scroll incrementally (more gradual)
                        current_scroll = tracklist_container.evaluate("element => element.scrollTop")
                        scroll_height = tracklist_container.evaluate("element => element.scrollHeight")
                        client_height = tracklist_container.evaluate("element => element.clientHeight")
                        
                        # Scroll down by viewport height each time
                        new_scroll = min(current_scroll + client_height, scroll_height)
                        tracklist_container.evaluate(f"element => element.scrollTop = {new_scroll}")
                        
                        # Strategy 2: Also try keyboard events to trigger loading
                        if scroll_attempts % 5 == 0:  # Every 5th attempt
                            tracklist_container.focus()
                            page.keyboard.press("PageDown")
                            page.wait_for_timeout(500)
                            page.keyboard.press("End")
                    else:
                        # Fallback: Scroll page incrementally
                        current_scroll = page.evaluate("window.pageYOffset || document.documentElement.scrollTop")
                        page_height = page.evaluate("document.body.scrollHeight")
                        viewport_height = page.evaluate("window.innerHeight")
                        new_scroll = min(current_scroll + viewport_height, page_height)
                        page.evaluate(f"window.scrollTo(0, {new_scroll})")
                    
                    # Wait for content to load
                    page.wait_for_timeout(1500)
                    
                    # Count visible tracks using multiple selectors
                    track_count_selectors = [
                        'div[data-testid="tracklist-row"]',
                        'div[role="row"][aria-rowindex]',
                        'div[data-testid="entity-row"]'
                    ]
                    
                    current_track_count = 0
                    for selector in track_count_selectors:
                        track_rows = page.query_selector_all(selector)
                        if track_rows:
                            current_track_count = len(track_rows)
                            break
                    
                    # Check if new API responses came in
                    if len(api_responses) > api_responses_before:
                        api_responses_before = len(api_responses)
                        no_change_count = 0  # Reset counter if new API data arrived
                    
                    if current_track_count == last_track_count:
                        no_change_count += 1
                        if no_change_count >= 5:
                            # No new tracks loaded after 5 attempts, we're done
                            print(f"  No new tracks after {no_change_count} attempts, stopping")
                            break
                    else:
                        no_change_count = 0
                        last_track_count = current_track_count
                        if scroll_attempts % 10 == 0:  # Print every 10 attempts
                            print(f"  Loaded {current_track_count} tracks so far...")
                    
                    scroll_attempts += 1
                
                print(f"Finished scrolling after {scroll_attempts} attempts, found {last_track_count} tracks")
                
                # Wait a bit more for any final API calls
                page.wait_for_timeout(2000)
                
                # Try to extract from API responses first
                playlist_data = None
                all_tracks_from_api = []
                
                for resp in api_responses:
                    data = resp.get("data", {})
                    # Look for playlist structure in API responses
                    if isinstance(data, dict):
                        # Check for common Spotify API response structures
                        if "tracks" in data or "items" in data:
                            if not playlist_data:
                                playlist_data = data.copy()
                            # Collect tracks from this response
                            tracks_in_resp = data.get("tracks", {}).get("items", []) if isinstance(data.get("tracks"), dict) else []
                            if not tracks_in_resp:
                                tracks_in_resp = data.get("items", [])
                            all_tracks_from_api.extend(tracks_in_resp)
                        # Check nested structures
                        for key in ["playlist", "playlists", "content", "data"]:
                            if key in data and isinstance(data[key], dict):
                                nested = data[key]
                                if "tracks" in nested or "items" in nested:
                                    if not playlist_data:
                                        playlist_data = nested.copy()
                                    tracks_in_resp = nested.get("tracks", {}).get("items", []) if isinstance(nested.get("tracks"), dict) else []
                                    if not tracks_in_resp:
                                        tracks_in_resp = nested.get("items", [])
                                    all_tracks_from_api.extend(tracks_in_resp)
                
                # If we found tracks from API, use them
                if all_tracks_from_api and playlist_data:
                    # Deduplicate tracks by ID
                    seen_ids = set()
                    unique_tracks = []
                    for track_item in all_tracks_from_api:
                        track_obj = track_item.get("track", track_item) if isinstance(track_item, dict) else {}
                        track_id = track_obj.get("id") if isinstance(track_obj, dict) else None
                        if track_id and track_id not in seen_ids:
                            seen_ids.add(track_id)
                            unique_tracks.append(track_item)
                    all_tracks_from_api = unique_tracks
                    # Update playlist_data with all tracks
                    if isinstance(playlist_data.get("tracks"), dict):
                        playlist_data["tracks"]["items"] = all_tracks_from_api
                    else:
                        playlist_data["items"] = all_tracks_from_api
                
                # Fallback to DOM extraction if API data not found
                if not playlist_data:
                    # Wait for playlist content to load
                    try:
                        page.wait_for_selector('div[data-testid="entityTitle"], h1', timeout=10000)
                    except Exception:
                        pass
                    
                    # Extract playlist title
                    title_elem = page.query_selector('div[data-testid="entityTitle"], h1')
                    playlist_title = title_elem.inner_text() if title_elem else "Unknown Playlist"
                    
                    # Extract owner/creator - try multiple selectors
                    owner = "Unknown"
                    for selector in ['a[href*="/user/"]', 'a[href*="/artist/"]', 'span:has-text("By") + a']:
                        owner_elem = page.query_selector(selector)
                        if owner_elem:
                            owner = owner_elem.inner_text()
                            break
                    
                    # Extract tracks from DOM
                    tracks = []
                    try:
                        # Try multiple selectors for track rows
                        track_selectors = [
                            'div[data-testid="tracklist-row"]',
                            'div[role="row"]',
                            'div[data-testid="entity-row"]'
                        ]
                        
                        track_rows = []
                        for selector in track_selectors:
                            track_rows = page.query_selector_all(selector)
                            if track_rows:
                                break
                        
                        for row in track_rows:
                            try:
                                # Try to extract track name - multiple selectors
                                track_name = "Unknown Track"
                                for name_sel in [
                                    'div[data-testid="entityTitle"]',
                                    'a[href*="/track/"]',
                                    'span[dir="auto"]'
                                ]:
                                    name_elem = row.query_selector(name_sel)
                                    if name_elem:
                                        track_name = name_elem.inner_text().strip()
                                        if track_name and track_name != "Unknown Track":
                                            break
                                
                                # Extract artist(s) - try multiple approaches
                                artists = ["Unknown Artist"]
                                artist_elems = row.query_selector_all('a[href*="/artist/"]')
                                if artist_elems:
                                    artists = [elem.inner_text().strip() for elem in artist_elems if elem.inner_text().strip()]
                                else:
                                    # Try to find artist text in row
                                    artist_text = row.query_selector('span:has-text("•")')
                                    if artist_text:
                                        artists = [artist_text.inner_text().strip().replace("•", "").strip()]
                                
                                # Extract album
                                album = None
                                album_elem = row.query_selector('a[href*="/album/"]')
                                if album_elem:
                                    album = album_elem.inner_text().strip()
                                
                                # Extract track URL
                                track_url = None
                                track_link = row.query_selector('a[href*="/track/"]')
                                if track_link:
                                    track_url = track_link.get_attribute('href')
                                    if track_url and not track_url.startswith('http'):
                                        track_url = f"https://open.spotify.com{track_url}"
                                
                                # Extract duration
                                duration = None
                                duration_elem = row.query_selector('span[data-testid="duration"]')
                                if duration_elem:
                                    duration = duration_elem.inner_text().strip()
                                
                                if track_name != "Unknown Track" or artists != ["Unknown Artist"]:
                                    tracks.append({
                                        "name": track_name,
                                        "artists": artists,
                                        "album": album,
                                        "url": track_url,
                                        "duration": duration,
                                    })
                            except Exception as e:
                                print(f"Warning: Could not extract track data: {e}")
                                continue
                    
                    except Exception as e:
                        print(f"Warning: Could not extract tracks from DOM: {e}")
                
                # If we got data from API, use it instead of DOM extraction
                # Also check if we need to scroll more based on total track count
                current_visible_tracks = last_track_count if 'last_track_count' in locals() else (len(all_tracks_from_api) if all_tracks_from_api else 25)
                if total_tracks_from_page and total_tracks_from_page > current_visible_tracks:
                    print(f"  Page shows {total_tracks_from_page} tracks, but we only have {current_visible_tracks}. Continuing to scroll...")
                    # Continue scrolling if we haven't loaded all tracks
                    additional_scrolls = 0
                    max_additional = 300  # Increased for longer playlists
                    no_progress_count = 0
                    last_count = current_visible_tracks
                    
                    while additional_scrolls < max_additional and current_visible_tracks < total_tracks_from_page:
                        if tracklist_container:
                            # Get current scroll position
                            current_scroll = tracklist_container.evaluate("element => element.scrollTop")
                            scroll_height = tracklist_container.evaluate("element => element.scrollHeight")
                            client_height = tracklist_container.evaluate("element => element.clientHeight")
                            
                            # More aggressive scrolling - scroll by smaller increments more frequently
                            scroll_increment = client_height * 0.5  # Scroll 50% of viewport
                            new_scroll = min(current_scroll + scroll_increment, scroll_height)
                            tracklist_container.evaluate(f"element => element.scrollTop = {new_scroll}")
                            
                            # Also try keyboard events more frequently
                            if additional_scrolls % 5 == 0:
                                tracklist_container.focus()
                                page.keyboard.press("ArrowDown")
                                page.wait_for_timeout(100)
                                # Try multiple arrow downs
                                for _ in range(3):
                                    page.keyboard.press("ArrowDown")
                                    page.wait_for_timeout(50)
                        else:
                            page.evaluate("window.scrollBy(0, window.innerHeight * 0.5)")
                        
                        page.wait_for_timeout(800)  # Wait for lazy loading
                        
                        # Re-check track count
                        track_rows = page.query_selector_all('div[data-testid="tracklist-row"]')
                        new_count = len(track_rows)
                        
                        if new_count > current_visible_tracks:
                            current_visible_tracks = new_count
                            no_progress_count = 0
                            last_count = new_count
                            if additional_scrolls % 15 == 0:
                                print(f"    Progress: {current_visible_tracks}/{total_tracks_from_page} tracks loaded...")
                        elif new_count >= total_tracks_from_page:
                            current_visible_tracks = new_count
                            break
                        else:
                            # No progress - try different scrolling strategy
                            no_progress_count += 1
                            if no_progress_count >= 10:
                                # Try scrolling to bottom directly
                                if tracklist_container:
                                    tracklist_container.evaluate("element => element.scrollTop = element.scrollHeight")
                                    page.wait_for_timeout(2000)
                                    track_rows = page.query_selector_all('div[data-testid="tracklist-row"]')
                                    new_count = len(track_rows)
                                    if new_count > current_visible_tracks:
                                        current_visible_tracks = new_count
                                        no_progress_count = 0
                                        print(f"    Jumped to bottom, found {current_visible_tracks} tracks")
                                    else:
                                        # Still no progress, might be at the end
                                        break
                                no_progress_count = 0
                        
                        additional_scrolls += 1
                    
                    print(f"  Additional scrolling complete after {additional_scrolls} attempts, now have {current_visible_tracks} visible tracks")
                    last_track_count = current_visible_tracks
                
                if playlist_data:
                    playlist_title = playlist_data.get("name", playlist_title)
                    owner_data = playlist_data.get("owner", {})
                    if isinstance(owner_data, dict):
                        owner = owner_data.get("display_name", owner_data.get("id", owner))
                    # Extract tracks from API data
                    api_tracks = playlist_data.get("tracks", {}).get("items", []) if isinstance(playlist_data.get("tracks"), dict) else []
                    if not api_tracks:
                        api_tracks = playlist_data.get("items", [])
                    
                    if api_tracks:
                        tracks = []
                        for item in api_tracks:
                            track_obj = item.get("track", item) if isinstance(item, dict) else {}
                            if track_obj:
                                track_name = track_obj.get("name", "Unknown Track")
                                artists_data = track_obj.get("artists", [])
                                artists = [a.get("name", "Unknown") for a in artists_data if isinstance(a, dict)]
                                if not artists:
                                    artists = ["Unknown Artist"]
                                
                                album_data = track_obj.get("album", {})
                                album = album_data.get("name") if isinstance(album_data, dict) else None
                                
                                track_id = track_obj.get("id", "")
                                track_url = f"https://open.spotify.com/track/{track_id}" if track_id else None
                                
                                duration_ms = track_obj.get("duration_ms", 0)
                                duration = None
                                if duration_ms:
                                    minutes = duration_ms // 60000
                                    seconds = (duration_ms % 60000) // 1000
                                    duration = f"{minutes}:{seconds:02d}"
                                
                                tracks.append({
                                    "name": track_name,
                                    "artists": artists,
                                    "album": album,
                                    "url": track_url,
                                    "duration": duration,
                                })
                
                playlist_title = playlist_title if playlist_title else "Unknown Playlist"
                
                # Extract description (if available)
                description_elem = page.query_selector('[data-testid="playlist-description"]')
                description = description_elem.inner_text() if description_elem else None
                
                # Extract follower count (if available)
                follower_elem = page.query_selector('[data-testid="followers-count"]')
                followers = follower_elem.inner_text() if follower_elem else None
                
                # After all scrolling, re-extract from DOM if we don't have all tracks
                if total_tracks_from_page and len(tracks) < total_tracks_from_page:
                    print(f"  Re-extracting from DOM after scrolling (have {len(tracks)}, need {total_tracks_from_page})...")
                    # Re-extract tracks from DOM
                    track_rows = page.query_selector_all('div[data-testid="tracklist-row"]')
                    if len(track_rows) > len(tracks):
                        print(f"  Found {len(track_rows)} tracks in DOM, re-extracting...")
                        tracks = []  # Reset and re-extract
                        for row in track_rows:
                            try:
                                # Extract track name
                                track_name = "Unknown Track"
                                name_elem = row.query_selector('div[data-testid="entityTitle"] a, a[href*="/track/"]')
                                if name_elem:
                                    track_name = name_elem.inner_text().strip()
                                
                                # Extract artist(s)
                                artists = ["Unknown Artist"]
                                artist_elems = row.query_selector_all('a[href*="/artist/"]')
                                if artist_elems:
                                    artists = [elem.inner_text().strip() for elem in artist_elems if elem.inner_text().strip()]
                                
                                # Extract album
                                album = None
                                album_elem = row.query_selector('a[href*="/album/"]')
                                if album_elem:
                                    album = album_elem.inner_text().strip()
                                
                                # Extract track URL
                                track_url = None
                                track_link = row.query_selector('a[href*="/track/"]')
                                if track_link:
                                    track_url = track_link.get_attribute('href')
                                    if track_url and not track_url.startswith('http'):
                                        track_url = f"https://open.spotify.com{track_url}"
                                
                                # Extract duration
                                duration = None
                                duration_elem = row.query_selector('span[data-testid="duration"]')
                                if duration_elem:
                                    duration = duration_elem.inner_text().strip()
                                
                                if track_name != "Unknown Track" or artists != ["Unknown Artist"]:
                                    tracks.append({
                                        "name": track_name,
                                        "artists": artists,
                                        "album": album,
                                        "url": track_url,
                                        "duration": duration,
                                    })
                            except Exception as e:
                                continue
                        print(f"  Re-extracted {len(tracks)} tracks from DOM")
                
                # Extract total tracks count
                total_tracks = len(tracks)
                
                browser.close()
                
                return {
                    "title": playlist_title,
                    "owner": owner,
                    "description": description,
                    "followers": followers,
                    "total_tracks": total_tracks,
                    "tracks": tracks,
                    "url": url,
                    "scraped_at": int(time.time()),
                }
                
            except Exception as e:
                browser.close()
                raise ValueError(f"Failed to scrape Spotify playlist: {str(e)}")
    
    def normalize_output(
        self,
        scraped_data: dict[str, Any],
        source_id: str,
    ) -> dict[str, Any]:
        """Normalize Spotify playlist data to common format."""
        return {
            "source": "spotify",
            "playlist_id": source_id,
            "title": scraped_data.get("title", "Unknown Playlist"),
            "owner": scraped_data.get("owner", "Unknown"),
            "description": scraped_data.get("description"),
            "followers": scraped_data.get("followers"),
            "total_tracks": scraped_data.get("total_tracks", 0),
            "tracks": scraped_data.get("tracks", []),
            "url": scraped_data.get("url", ""),
            "scraped_at": scraped_data.get("scraped_at", int(time.time())),
            "raw_data": scraped_data,  # Keep original for reference
        }
    
    def get_storage_path(self, source_id: str, data_dir: Path) -> Path:
        """Get storage path for Spotify playlist."""
        return data_dir / "imports" / "spotify" / f"playlist_{source_id}.json"
