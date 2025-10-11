#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Simple Spotify Song Downloader (yt-dlp only)
Falls back to direct yt-dlp search if spotdl doesn't work.

This version doesn't require FFmpeg to be in PATH for the metadata fetch.
"""

import sys
import os
import subprocess
import json
import urllib.parse
from pathlib import Path

# Force UTF-8 encoding for stdout/stderr to handle emojis on Windows
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

def extract_track_info_from_api(spotify_url):
    """
    Extract track info using the local API endpoint (which uses Spotify Web API).
    This gives us accurate track and artist names for better YouTube search.
    """
    try:
        import urllib.request
        import json as json_lib
        
        # Call our local API endpoint
        api_url = f"http://localhost:3000/api/spotify/track-metadata?url={urllib.parse.quote(spotify_url)}"
        
        with urllib.request.urlopen(api_url, timeout=15) as response:
            data = json_lib.loads(response.read().decode('utf-8'))
            
            if 'error' in data:
                print(f"API error: {data['error']}", file=sys.stderr)
                return None
            
            track_name = data.get('name', 'Unknown')
            artists = data.get('artists', ['Unknown Artist'])
            
            return {
                'name': track_name,
                'artists': artists,
                'search_query': data.get('searchQuery', f"{track_name} {artists[0]}")
            }
    except Exception as e:
        print(f"Failed to fetch from API: {e}", file=sys.stderr)
        return None

def extract_track_info_from_url(spotify_url):
    """
    Extract basic info from Spotify URL without using spotdl.
    Uses Spotify's oEmbed API (no auth required) as fallback.
    """
    track_id = None
    
    # Extract track ID from URL
    if "/track/" in spotify_url:
        track_id = spotify_url.split("/track/")[1].split("?")[0]
    elif "spotify:track:" in spotify_url:
        track_id = spotify_url.split("spotify:track:")[1]
    
    if not track_id:
        return None
    
    try:
        import urllib.request
        import json as json_lib
        
        # Use Spotify's oEmbed API (public, no auth needed)
        oembed_url = f"https://open.spotify.com/oembed?url=https://open.spotify.com/track/{track_id}"
        
        with urllib.request.urlopen(oembed_url, timeout=10) as response:
            data = json_lib.loads(response.read().decode('utf-8'))
            
            # Parse title - Try different formats
            # Spotify oEmbed returns formats like:
            # - "Song Name" (without quotes sometimes)
            # - Song Name - Artist Name
            # - Song Name by Artist Name  
            title = data.get('title', '')
            
            # Try to extract from different title formats
            track_name = 'Unknown'
            artist = 'Unknown Artist'
            
            if '" - ' in title:
                # Format: "Song Name" - Artist Name
                parts = title.split('" - ')
                track_name = parts[0].strip('"')
                artist = parts[1] if len(parts) > 1 else 'Unknown Artist'
            elif ' - ' in title:
                # Format: Song Name - Artist Name
                parts = title.split(' - ')
                track_name = parts[0]
                artist = parts[1] if len(parts) > 1 else 'Unknown Artist'
            elif ' by ' in title:
                # Format: Song Name by Artist Name
                parts = title.split(' by ')
                track_name = parts[0]
                artist = parts[1] if len(parts) > 1 else 'Unknown Artist'
            else:
                # Use whole title
                track_name = title
            
            return {
                'name': track_name,
                'artists': [artist],
                'search_query': f"{track_name} {artist}"
            }
    except Exception as e:
        print(f"Failed to fetch from Spotify oEmbed: {e}", file=sys.stderr)
        return None

def download_with_ytdlp(search_query, output_dir, use_consistent_naming=False):
    """
    Download using yt-dlp from YouTube Music exclusively.
    Uses direct YouTube Music search URL: https://music.youtube.com/search?q=<query>
    Prefers m4a format (AAC audio) for better quality.
    Downloads best audio without conversion - NO FFmpeg needed!
    """
    try:
        # Determine output template
        if use_consistent_naming:
            # Use consistent naming: rename previous latest to previous, download new as latest
            output_template = os.path.join(output_dir, 'temp_download.%(ext)s')
        else:
            output_template = os.path.join(output_dir, '%(title)s.%(ext)s')
        
        # yt-dlp options - download best audio from YouTube Music
        # Use the YouTube Music extractor directly with a search URL
        # Format: https://music.youtube.com/search?q=<query>
        music_search_url = f"https://music.youtube.com/search?q={urllib.parse.quote(search_query)}"
        
        cmd = [
            sys.executable, '-m', 'yt_dlp',
            '-f', 'bestaudio[ext=m4a]/bestaudio',  # Prefer m4a (better quality than webm)
            '--no-post-overwrites',
            '--no-warnings',  # Suppress warning messages
            '--no-playlist',  # Don't download playlists (in case URL is a playlist)
            '--quiet',  # Quiet mode - suppress all output except errors
            '--progress',  # But still show progress (optional, remove if you want completely silent)
            '--playlist-items', '1',  # Only download first result
            '-o', output_template,
            music_search_url  # Direct YouTube Music search URL
        ]
        
        print(f"Downloading via yt-dlp (YouTube Music): {search_query}", file=sys.stderr)
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=180
        )
        
        if result.returncode == 0:
            # Find the downloaded file (might be .webm, .m4a, .opus, etc.)
            audio_extensions = ['.webm', '.m4a', '.opus', '.mp3', '.aac']
            
            if use_consistent_naming:
                # Find the temp file
                temp_files = [f for f in os.listdir(output_dir) 
                            if f.startswith('temp_download') and any(f.endswith(ext) for ext in audio_extensions)]
                if temp_files:
                    temp_file = temp_files[0]
                    file_ext = os.path.splitext(temp_file)[1]
                    
                    # Rename previous latest to previous
                    for ext in audio_extensions:
                        latest_path = os.path.join(output_dir, f'latest{ext}')
                        previous_path = os.path.join(output_dir, f'previous{ext}')
                        
                        if os.path.exists(latest_path):
                            # Remove old previous if exists
                            if os.path.exists(previous_path):
                                os.remove(previous_path)
                            # Rename latest to previous
                            os.rename(latest_path, previous_path)
                            print(f"Moved {os.path.basename(latest_path)} to previous{ext}", file=sys.stderr)
                    
                    # Rename temp to latest
                    latest_path = os.path.join(output_dir, f'latest{file_ext}')
                    temp_path = os.path.join(output_dir, temp_file)
                    os.rename(temp_path, latest_path)
                    print(f"Saved as latest{file_ext}", file=sys.stderr)
                    
                    return {
                        'success': True,
                        'file': f'latest{file_ext}',
                        'path': latest_path
                    }
            else:
                files = [f for f in os.listdir(output_dir) 
                        if any(f.endswith(ext) for ext in audio_extensions)]
                if files:
                    return {
                        'success': True,
                        'file': files[-1],  # Most recent file
                        'path': os.path.join(output_dir, files[-1])
                    }
        
        return {
            'success': False,
            'error': 'Download failed',
            'details': result.stderr
        }
    except subprocess.TimeoutExpired:
        print("yt-dlp timed out after 180 seconds", file=sys.stderr)
        return {
            'success': False,
            'error': 'Download timed out (>180s)'
        }
    except Exception as e:
        print(f"yt-dlp exception: {str(e)}", file=sys.stderr)
        return {
            'success': False,
            'error': f'Download error: {str(e)}'
        }

def main():
    if len(sys.argv) < 3:
        print(json.dumps({
            "success": False,
            "error": "Usage: python download_spotify_song_simple.py <spotify_url> <output_folder> [use_consistent_naming]"
        }))
        sys.exit(1)
    
    spotify_url = sys.argv[1]
    output_folder = sys.argv[2]
    use_consistent_naming = len(sys.argv) > 3 and sys.argv[3].lower() == 'true'
    
    # Create output folder
    os.makedirs(output_folder, exist_ok=True)
    
    # Get track info - Try API first for accurate data, fallback to oEmbed
    print("Fetching track information...", file=sys.stderr)
    track_info = extract_track_info_from_api(spotify_url)
    
    if not track_info:
        print("API fetch failed, trying oEmbed fallback...", file=sys.stderr)
        track_info = extract_track_info_from_url(spotify_url)
    
    if not track_info:
        print(json.dumps({
            "success": False,
            "error": "Could not fetch track information from Spotify"
        }))
        sys.exit(1)
    
    track_name = track_info.get('name', 'Unknown')
    artists = track_info.get('artists', ['Unknown'])
    search_query = track_info.get('search_query', f"{track_name} {artists[0]}")
    
    print(f"Track: {track_name}", file=sys.stderr)
    print(f"Artist: {artists[0]}", file=sys.stderr)
    print(f"Search: {search_query}", file=sys.stderr)
    if use_consistent_naming:
        print("Using consistent naming (latest/previous)", file=sys.stderr)
    
    # Download with yt-dlp
    download_result = download_with_ytdlp(search_query, output_folder, use_consistent_naming)
    
    # Check if download was successful
    if download_result.get('success'):
        print(json.dumps({
            "success": True,
            "message": "Download successful via yt-dlp",
            "fileName": download_result['file'],
            "filePath": download_result['path'],
            "trackName": track_name,
            "artists": artists,
            "method": "ytdlp"
        }))
        sys.exit(0)
    else:
        print(json.dumps({
            "success": False,
            "error": download_result.get('error', 'Download failed'),
            "trackName": track_name,
            "artists": artists,
            "details": download_result.get('details', 'Unknown error')[:500] if download_result.get('details') else 'Unknown error'
        }))
        sys.exit(1)

if __name__ == "__main__":
    main()
