#!/usr/bin/env python3
"""
Standalone script to scrape a Spotify playlist.
Can be used directly or via the MCP server after restart.
"""

import json
import sys
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from plugins.spotify_scraper import SpotifyScraper


def main():
    if len(sys.argv) < 2:
        print("Usage: python scrape_spotify_playlist.py <playlist_url> [output_path]")
        sys.exit(1)
    
    url = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None
    
    scraper = SpotifyScraper()
    
    if not scraper.can_handle(url):
        print(f"Error: {url} is not a valid Spotify playlist URL")
        sys.exit(1)
    
    try:
        # Extract playlist ID
        playlist_id = scraper.extract_id(url)
        print(f"Scraping playlist: {playlist_id}")
        
        # Scrape the playlist
        scraped_data = scraper.scrape(url, method="playwright")
        
        # Normalize output
        normalized_data = scraper.normalize_output(scraped_data, playlist_id)
        
        # Determine output path
        if output_path:
            output_file = Path(output_path)
        else:
            # Use DATA_DIR if available, otherwise current directory
            data_dir = Path(os.getenv("DATA_DIR", "."))
            output_file = scraper.get_storage_path(playlist_id, data_dir)
        
        # Create output directory if needed
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Save to file
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(normalized_data, f, indent=2, ensure_ascii=False)
        
        print(f"\n✅ Successfully scraped playlist: {normalized_data['title']}")
        print(f"   Owner: {normalized_data['owner']}")
        print(f"   Tracks: {normalized_data['total_tracks']}")
        print(f"   Saved to: {output_file}")
        
        # Print track list
        print(f"\nTracks ({len(normalized_data['tracks'])}):")
        for i, track in enumerate(normalized_data['tracks'], 1):
            artists = ", ".join(track.get('artists', ['Unknown']))
            print(f"  {i}. {track.get('name', 'Unknown')} - {artists}")
        
    except Exception as e:
        print(f"Error scraping playlist: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    import os
    main()
