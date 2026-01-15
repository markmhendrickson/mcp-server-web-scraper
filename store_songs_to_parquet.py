#!/usr/bin/env python3
"""
Store Spotify playlist tracks as songs in parquet via MCP server.
"""

import asyncio
import json
import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def call_parquet_tool(tool_name: str, arguments: dict) -> dict:
    """Call a tool on the parquet MCP server."""
    # Find parquet server
    script_dir = Path(__file__).parent.parent
    parquet_server_path = script_dir / "parquet" / "parquet_mcp_server.py"
    
    if not parquet_server_path.exists():
        raise RuntimeError(f"Parquet MCP server not found at {parquet_server_path}")
    
    python_cmd = os.getenv("PARQUET_MCP_PYTHON", "python3")
    
    async with stdio_client(
        StdioServerParameters(
            command=python_cmd,
            args=[str(parquet_server_path)],
            env=os.environ.copy(),
        )
    ) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
            # Parse the text content from the result
            if result.content and len(result.content) > 0:
                return json.loads(result.content[0].text)
            return {}


async def main():
    # Read the playlist JSON
    playlist_file = Path(__file__).parent / "imports" / "spotify" / "playlist_3i0FY58V7n8XIUyWDm3AYA.json"
    
    if not playlist_file.exists():
        print(f"Error: Playlist file not found: {playlist_file}")
        sys.exit(1)
    
    with open(playlist_file) as f:
        playlist_data = json.load(f)
    
    tracks = playlist_data.get("tracks", [])
    print(f"Found {len(tracks)} tracks to store")
    
    # Check if songs data type exists
    data_types = await call_parquet_tool("list_data_types", {})
    available_types = data_types.get("data_types", [])
    
    if "songs" not in available_types:
        print("'songs' data type not found. Available types:", available_types)
        print("Creating songs data type...")
        # We'll need to create the schema first - for now, let's try to add records
        # and see if the schema gets created automatically or we get an error
        print("Note: If schema doesn't exist, you may need to create it first")
    
    # Store each track as a song with favorite=True
    stored_count = 0
    error_count = 0
    
    for i, track in enumerate(tracks, 1):
        try:
            # Prepare song record
            song_record = {
                "title": track.get("name", "Unknown"),
                "artist": ", ".join(track.get("artists", ["Unknown Artist"])),
                "album": track.get("album"),
                "spotify_url": track.get("url"),
                "favorite": True,  # Mark as favorite
                "source": "spotify",
                "playlist_id": playlist_data.get("playlist_id"),
            }
            
            # Use upsert to avoid duplicates (match on spotify_url if available, otherwise title+artist)
            filters = {}
            if track.get("url"):
                filters["spotify_url"] = track.get("url")
            else:
                filters["title"] = track.get("name")
                filters["artist"] = ", ".join(track.get("artists", []))
            
            result = await call_parquet_tool("upsert_record", {
                "data_type": "songs",
                "filters": filters,
                "record": song_record
            })
            
            if result.get("error"):
                print(f"  Error storing track {i} ({track.get('name', 'Unknown')}): {result.get('error')}")
                error_count += 1
            else:
                action = result.get("action", "unknown")
                print(f"  {i}/{len(tracks)}: {track.get('name', 'Unknown')} - {action}")
                stored_count += 1
                
        except Exception as e:
            print(f"  Exception storing track {i} ({track.get('name', 'Unknown')}): {e}")
            error_count += 1
    
    print(f"\n✅ Stored {stored_count} songs")
    if error_count > 0:
        print(f"❌ {error_count} errors")


if __name__ == "__main__":
    asyncio.run(main())
