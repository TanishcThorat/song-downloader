#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Simple FastAPI Song Downloader using yt-dlp
Frontend-compatible endpoint that returns audio blob directly.
Based on download_spotify_song_simple.py approach.
"""

import asyncio
import json
import os
import sys
import tempfile
import urllib.parse
import urllib.request
import io
import shutil
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional, Dict, Any, Union
import traceback
import time

# Import yt-dlp directly for better performance
import yt_dlp
from yt_dlp.utils import DownloadError, ExtractorError

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from mangum import Mangum

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Force UTF-8 encoding for stdout/stderr to handle emojis on Windows
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Application lifespan manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting Song Downloader API...")
    yield
    # Shutdown
    logger.info("Shutting down Song Downloader API...")

app = FastAPI(
    title="Song Downloader API", 
    description="Download songs from Spotify URLs using yt-dlp",
    version="2.0.0",
    lifespan=lifespan
)

# Add CORS middleware for frontend compatibility
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Error handling middleware
@app.middleware("http")
async def error_handling_middleware(request: Request, call_next):
    """Global error handling middleware"""
    start_time = time.time()
    
    try:
        response = await call_next(request)
        process_time = time.time() - start_time
        response.headers["X-Process-Time"] = str(process_time)
        return response
    except Exception as e:
        process_time = time.time() - start_time
        logger.error(f"Unhandled error in {request.method} {request.url}: {str(e)}\n{traceback.format_exc()}")
        
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal server error",
                "message": str(e),
                "timestamp": time.time(),
                "process_time": process_time
            }
        )

class DownloadRequest(BaseModel):
    # Core fields
    spotify_url: Optional[str] = Field(None, description="Spotify track URL")
    song_url: Optional[str] = Field(None, description="Alternative field for Spotify URL")
    url: Optional[str] = Field(None, description="Frontend compatibility URL field")
    trackUrl: Optional[str] = Field(None, description="Frontend compatibility track URL")
    trackId: Optional[str] = Field(None, description="Spotify track ID")
    use_consistent_naming: bool = Field(False, description="Use consistent file naming")
    
    # Additional metadata fields
    title: Optional[str] = Field(None, description="Track title")
    track_name: Optional[str] = Field(None, description="Track name")
    artist: Optional[str] = Field(None, description="Artist name")
    artist_name: Optional[str] = Field(None, description="Artist name alternative")
    album: Optional[str] = Field(None, description="Album name")
    duration: Optional[str] = Field(None, description="Track duration")
    track_id: Optional[str] = Field(None, description="Track ID alternative")
    search_query: Optional[str] = Field(None, description="Custom search query")
    
    # Frontend metadata format
    metadata: Optional[Dict[str, Any]] = Field(None, description="Frontend metadata object")
    
    def get_spotify_url(self) -> str:
        """Get the Spotify URL from any available field"""
        url = self.spotify_url or self.song_url or self.url or self.trackUrl
        # If no URL but trackId provided, construct URL
        if not url and self.trackId:
            url = f"https://open.spotify.com/track/{self.trackId}"
        return url
    
    def get_track_name(self) -> str:
        """Get track name from any available field"""
        # Check metadata first (frontend format)
        if self.metadata and self.metadata.get('name'):
            return self.metadata.get('name')
        
        return self.title or self.track_name or "Unknown"
    
    def get_artist_name(self) -> str:
        """Get artist name from any available field"""
        # Check metadata first (frontend format)
        if self.metadata and self.metadata.get('artist'):
            return self.metadata.get('artist')
        
        return self.artist or self.artist_name or "Unknown Artist"
    
    def get_search_query(self) -> str:
        """Generate search query from available metadata"""
        # Check metadata first (frontend format)
        if self.metadata and self.metadata.get('searchQuery'):
            return self.metadata.get('searchQuery')
        
        if self.search_query:
            return self.search_query
        
        track = self.get_track_name()
        artist = self.get_artist_name()
        
        # Clean up artist field (might contain multiple artists)
        if artist and "," in artist:
            # Take first artist for search
            artist = artist.split(",")[0].strip()
        
        return f"{track} {artist}".strip()

class TrackInfo(BaseModel):
    name: str
    artists: list[str]
    search_query: str
    album: Optional[str] = None
    duration: Optional[str] = None

class DownloadResult(BaseModel):
    success: bool
    file_path: Optional[str] = None
    file_name: Optional[str] = None
    file_size: Optional[int] = None
    content_type: Optional[str] = None
    error: Optional[str] = None


class SpotifyTrackExtractor:
    """Handles Spotify track metadata extraction with multiple fallback methods"""
    
    @staticmethod
    async def extract_from_api(spotify_url: str) -> Optional[TrackInfo]:
        """Extract track info using local API endpoint with timeout"""
        try:
            # Fallback to urllib if aiohttp is not available
            try:
                import aiohttp
                api_url = f"http://localhost:3000/api/spotify/track-metadata?url={urllib.parse.quote(spotify_url)}"
                
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                    async with session.get(api_url) as response:
                        if response.status == 200:
                            data = await response.json()
                            
                            if 'error' not in data:
                                return TrackInfo(
                                    name=data.get('name', 'Unknown'),
                                    artists=data.get('artists', ['Unknown Artist']),
                                    search_query=data.get('searchQuery', f"{data.get('name', 'Unknown')} {data.get('artists', ['Unknown'])[0]}")
                                )
            except ImportError:
                # Fallback to synchronous urllib
                api_url = f"http://localhost:3000/api/spotify/track-metadata?url={urllib.parse.quote(spotify_url)}"
                
                with urllib.request.urlopen(api_url, timeout=10) as response:
                    data = json.loads(response.read().decode('utf-8'))
                    
                    if 'error' not in data:
                        return TrackInfo(
                            name=data.get('name', 'Unknown'),
                            artists=data.get('artists', ['Unknown Artist']),
                            search_query=data.get('searchQuery', f"{data.get('name', 'Unknown')} {data.get('artists', ['Unknown'])[0]}")
                        )
        except Exception as e:
            logger.warning(f"Failed to fetch from API: {e}")
        return None
    
    @staticmethod
    def extract_from_oembed(spotify_url: str) -> Optional[TrackInfo]:
        """Extract track info using Spotify oEmbed API"""
        track_id = None
        
        # Extract track ID from URL
        if "/track/" in spotify_url:
            track_id = spotify_url.split("/track/")[1].split("?")[0]
        elif "spotify:track:" in spotify_url:
            track_id = spotify_url.split("spotify:track:")[1]
        
        if not track_id:
            return None
        
        try:
            oembed_url = f"https://open.spotify.com/oembed?url=https://open.spotify.com/track/{track_id}"
            
            with urllib.request.urlopen(oembed_url, timeout=10) as response:
                data = json.loads(response.read().decode('utf-8'))
                
                title = data.get('title', '').strip()
                track_name = 'Unknown'
                artist = 'Unknown Artist'
                
                if title:
                    # Enhanced parsing for different Spotify oEmbed title formats
                    if ' · ' in title:
                        parts = title.split(' · ')
                        track_name, artist = parts[0], parts[1] if len(parts) > 1 else 'Unknown Artist'
                    elif '" - ' in title:
                        parts = title.split('" - ')
                        track_name, artist = parts[0].strip('"'), parts[1] if len(parts) > 1 else 'Unknown Artist'
                    elif ' - ' in title:
                        parts = title.split(' - ')
                        track_name, artist = parts[0], parts[1] if len(parts) > 1 else 'Unknown Artist'
                    elif ' by ' in title:
                        parts = title.split(' by ')
                        track_name, artist = parts[0], parts[1] if len(parts) > 1 else 'Unknown Artist'
                    else:
                        track_name = title
                
                # Clean up extracted data
                track_name = track_name if track_name.lower() != 'unknown' else 'Unknown'
                artist = artist if artist.lower() not in ['unknown artist', 'unknown', ''] else 'Unknown Artist'
                
                return TrackInfo(
                    name=track_name,
                    artists=[artist],
                    search_query=f"{track_name} {artist}"
                )
        except Exception as e:
            logger.warning(f"Failed to fetch from Spotify oEmbed: {e}")
        return None


class YtDlpDownloader:
    """Production-ready yt-dlp wrapper with proper error handling and performance optimization"""
    
    def __init__(self):
        self.default_opts = {
            # More flexible format selection with multiple fallbacks
            'format': 'bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best[height<=720]/best',
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
            'no_post_overwrites': True,
            'playlist_items': '1',  # Only download first result
            'socket_timeout': 60,
            'retries': 3,
            'fragment_retries': 3,
            # Enhanced YouTube Music configuration
            'extractor_args': {
                'youtube': {
                    'player_client': ['android_music', 'android', 'web'],
                    'skip': ['dash', 'hls']
                }
            },
            # User agent optimized for YouTube Music
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            },
            'geo_bypass': True,
            'geo_bypass_country': 'US',
        }
    
    async def download_audio(self, search_query: str, output_dir: str) -> DownloadResult:
        """Download audio using yt-dlp Python API with async support"""
        start_time = time.time()
        
        try:
            # Create output template
            output_template = str(Path(output_dir) / '%(title)s.%(ext)s')
            
            # Configure yt-dlp options
            ydl_opts = {
                **self.default_opts,
                'outtmpl': output_template,
            }
            
            # Add progress hook for monitoring
            def progress_hook(d):
                if d['status'] == 'downloading':
                    logger.info(f"Downloading: {d.get('_percent_str', 'N/A')} - {d.get('_speed_str', 'N/A')}")
                elif d['status'] == 'finished':
                    logger.info(f"Download completed: {d['filename']}")
            
            ydl_opts['progress_hooks'] = [progress_hook]
            
            # Use thread executor for non-blocking yt-dlp execution
            loop = asyncio.get_event_loop()
            
            def _download():
                # Determine output template
                use_consistent_naming = False  # Can be made configurable later
                if use_consistent_naming:
                    # Use consistent naming: rename previous latest to previous, download new as latest
                    output_template = os.path.join(output_dir, 'temp_download.%(ext)s')
                else:
                    output_template = os.path.join(output_dir, '%(title)s.%(ext)s')
                
                # Override the output template in ydl_opts
                ydl_opts['outtmpl'] = output_template
                
                # yt-dlp options - download best audio from YouTube Music
                # Use the YouTube Music extractor directly with a search URL
                # Format: https://music.youtube.com/search?q=<query>
                music_search_url = f"https://music.youtube.com/search?q={urllib.parse.quote(search_query)}"
                logger.info(f"Starting YouTube Music search: {music_search_url}")
                
                # Try with the configured format first, then fallback to simpler formats
                format_attempts = [
                    ydl_opts['format'],  # Original format string
                    'bestaudio/best',    # Simpler fallback
                    'best'               # Last resort
                ]
                
                for i, format_option in enumerate(format_attempts):
                    try:
                        current_opts = {**ydl_opts, 'format': format_option}
                        logger.info(f"Attempt {i+1}: Using format '{format_option}'")
                        
                        with yt_dlp.YoutubeDL(current_opts) as ydl:
                            ydl.download([music_search_url])
                            
                            # Find downloaded file
                            audio_extensions = ['.m4a', '.webm', '.opus', '.mp3', '.aac', '.mp4']
                            for file in Path(output_dir).iterdir():
                                if file.is_file() and file.suffix.lower() in audio_extensions:
                                    logger.info(f"Successfully downloaded: {file.name}")
                                    return {
                                        'file_path': str(file),
                                        'file_name': file.name,
                                        'file_size': file.stat().st_size,
                                        'content_type': self._get_content_type(file.suffix)
                                    }
                            
                    except Exception as e:
                        logger.warning(f"Format '{format_option}' failed: {str(e)}")
                        # Clear any partially downloaded files before next attempt
                        for file in Path(output_dir).iterdir():
                            if file.is_file():
                                try:
                                    file.unlink()
                                except:
                                    pass
                        
                        if i < len(format_attempts) - 1:
                            continue
                        else:
                            raise e
                    
                raise Exception("All format attempts failed - no file downloaded")
            
            # Execute with timeout
            result = await asyncio.wait_for(
                loop.run_in_executor(None, _download),
                timeout=120.0
            )
            
            download_time = time.time() - start_time
            logger.info(f"Download completed in {download_time:.2f} seconds")
            
            return DownloadResult(success=True, **result)
            
        except asyncio.TimeoutError:
            error_msg = "Download timed out after 120 seconds"
            logger.error(error_msg)
            return DownloadResult(success=False, error=error_msg)
            
        except DownloadError as e:
            error_msg = f"yt-dlp download error: {str(e)}"
            logger.error(error_msg)
            
            # If it's a 403 error, try alternative approach
            if "403" in str(e) or "Forbidden" in str(e):
                logger.info("Attempting fallback download with relaxed restrictions...")
                try:
                    return await self._fallback_download(search_query, output_dir)
                except Exception as fallback_error:
                    logger.error(f"Fallback download also failed: {fallback_error}")
            
            return DownloadResult(success=False, error=error_msg)
            
        except ExtractorError as e:
            error_msg = f"yt-dlp extractor error: {str(e)}"
            logger.error(error_msg)
            return DownloadResult(success=False, error=error_msg)
            
        except Exception as e:
            error_msg = f"Unexpected download error: {str(e)}"
            logger.error(f"{error_msg}\n{traceback.format_exc()}")
            return DownloadResult(success=False, error=error_msg)
    
    async def _fallback_download(self, search_query: str, output_dir: str) -> DownloadResult:
        """Fallback download method with minimal restrictions"""
        try:
            # Minimal yt-dlp options for fallback - still targeting YouTube Music
            fallback_opts = {
                'format': 'worst[ext=m4a]/worst[ext=webm]/worst',
                'noplaylist': True,
                'quiet': False,
                'no_warnings': False,
                'no_post_overwrites': True,
                'playlist_items': '1',  # Only download first result
                'socket_timeout': 120,
                'retries': 2,
                'outtmpl': str(Path(output_dir) / '%(title)s.%(ext)s'),
                'http_headers': {
                    'User-Agent': 'yt-dlp/2023.07.06'
                },
                'extractor_args': {
                    'youtube': {
                        'player_client': ['android_music', 'android'],
                    }
                },
            }
            
            loop = asyncio.get_event_loop()
            
            def _fallback_download_sync():
                with yt_dlp.YoutubeDL(fallback_opts) as ydl:
                    # Use YouTube Music URL for fallback as well
                    music_search_url = f"https://music.youtube.com/search?q={urllib.parse.quote(search_query)}"
                    logger.info(f"Fallback YouTube Music search: {music_search_url}")
                    ydl.download([music_search_url])
                    
                    # Find downloaded file
                    for file in Path(output_dir).iterdir():
                        if file.is_file() and file.suffix.lower() in ['.m4a', '.webm', '.opus', '.mp3', '.aac']:
                            return {
                                'file_path': str(file),
                                'file_name': file.name,
                                'file_size': file.stat().st_size,
                                'content_type': self._get_content_type(file.suffix)
                            }
                    raise Exception("Fallback download: file not found")
            
            result = await asyncio.wait_for(
                loop.run_in_executor(None, _fallback_download_sync),
                timeout=180.0
            )
            
            return DownloadResult(success=True, **result)
            
        except Exception as e:
            logger.error(f"Fallback download failed: {str(e)}")
            raise e

    @staticmethod
    def _get_content_type(file_extension: str) -> str:
        """Get MIME type for audio file extension"""
        content_type_map = {
            '.m4a': 'audio/mp4',
            '.webm': 'audio/webm',
            '.opus': 'audio/opus',
            '.mp3': 'audio/mpeg',
            '.aac': 'audio/aac',
            '.mp4': 'audio/mp4'
        }
        return content_type_map.get(file_extension.lower(), 'audio/octet-stream')




@app.post("/api/spotify/download-song")
async def download_song_frontend(request: DownloadRequest):
    """
    Production-ready frontend-compatible download endpoint
    Returns audio blob directly with comprehensive error handling and performance optimization
    """
    request_id = f"req_{int(time.time() * 1000)}"
    logger.info(f"[{request_id}] Download request received - trackId: {request.trackId}, url: {request.get_spotify_url()}")
    
    start_time = time.time()
    temp_dir = None
    
    try:
        # Input validation
        spotify_url = request.get_spotify_url()
        has_metadata = (request.get_track_name() != "Unknown") and (request.get_artist_name() != "Unknown Artist")
        
        if not spotify_url and not has_metadata:
            raise HTTPException(
                status_code=400, 
                detail="Either Spotify URL/Track ID or complete track metadata (title + artist) is required"
            )
        
        logger.info(f"[{request_id}] Input validation passed - URL: {spotify_url}, has_metadata: {has_metadata}")
        
        # Create secure temporary directory using OS-appropriate temp location
        temp_base_dir = "/tmp" if sys.platform != "win32" else None  # Use default temp dir on Windows
        temp_dir = tempfile.mkdtemp(prefix=f"song_dl_{request_id}_", dir=temp_base_dir)
        logger.info(f"[{request_id}] Created temp directory: {temp_dir}")
        
        # Initialize services
        extractor = SpotifyTrackExtractor()
        downloader = YtDlpDownloader()
        
        # Get track information
        track_info: Optional[TrackInfo] = None
        
        if has_metadata:
            logger.info(f"[{request_id}] Using provided metadata")
            artists = [a.strip() for a in request.get_artist_name().split(",")] if "," in request.get_artist_name() else [request.get_artist_name()]
            
            track_info = TrackInfo(
                name=request.get_track_name(),
                artists=artists,
                search_query=request.get_search_query(),
                album=request.album,
                duration=request.duration
            )
        else:
            logger.info(f"[{request_id}] Extracting track info from Spotify URL")
            
            # Try API first, then fallback to oEmbed
            try:
                track_info = await extractor.extract_from_api(spotify_url)
            except Exception as e:
                logger.warning(f"[{request_id}] API extraction failed: {e}")
            
            if not track_info:
                logger.info(f"[{request_id}] Falling back to oEmbed extraction")
                track_info = extractor.extract_from_oembed(spotify_url)
            
            if not track_info:
                raise HTTPException(
                    status_code=400, 
                    detail="Could not extract track information from Spotify URL"
                )
        
        logger.info(f"[{request_id}] Track info: {track_info.name} by {', '.join(track_info.artists)}")
        
        # Download audio
        logger.info(f"[{request_id}] Starting download with query: {track_info.search_query}")
        download_result = await downloader.download_audio(track_info.search_query, temp_dir)
        
        if not download_result.success:
            raise HTTPException(
                status_code=500, 
                detail=f"Download failed: {download_result.error}"
            )
        
        # Prepare response
        file_path = Path(download_result.file_path)
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="Downloaded file not found")
        
        # Read file content efficiently
        file_content = file_path.read_bytes()
        
        # Prepare headers
        # Prepare Content-Disposition header with UTF-8 filename support (RFC 5987)
        from urllib.parse import quote
        ascii_filename = (
            download_result.file_name.encode('ascii', 'ignore').decode('ascii')
            if any(ord(c) > 127 for c in download_result.file_name)
            else download_result.file_name
        )
        quoted_filename = quote(download_result.file_name)
        content_disposition = (
            f"attachment; filename=\"{ascii_filename}\"; filename*=UTF-8''{quoted_filename}"
        )
        headers = {
            "Content-Disposition": content_disposition,
            "Content-Length": str(len(file_content)),
            "X-Track-Name": track_info.name,
            "X-Track-Artist": ", ".join(track_info.artists),
            "X-Request-Id": request_id,
            "X-Download-Time": f"{time.time() - start_time:.2f}s"
        }
        
        if track_info.album:
            headers["X-Track-Album"] = track_info.album
        if track_info.duration:
            headers["X-Track-Duration"] = track_info.duration
        
        logger.info(f"[{request_id}] Download completed in {time.time() - start_time:.2f}s - Size: {len(file_content)} bytes")
        
        # Stream response efficiently
        def iter_file_content():
            chunk_size = 8192  # 8KB chunks
            for i in range(0, len(file_content), chunk_size):
                yield file_content[i:i + chunk_size]
        
        return StreamingResponse(
            iter_file_content(),
            media_type=download_result.content_type,
            headers=headers
        )
        
    except HTTPException:
        raise
    except asyncio.TimeoutError:
        error_msg = "Download operation timed out"
        logger.error(f"[{request_id}] {error_msg}")
        raise HTTPException(status_code=504, detail=error_msg)
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        logger.error(f"[{request_id}] {error_msg}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=error_msg)
    finally:
        # Cleanup
        if temp_dir and Path(temp_dir).exists():
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
                logger.info(f"[{request_id}] Cleaned up temp directory")
            except Exception as e:
                logger.warning(f"[{request_id}] Failed to cleanup temp directory: {e}")

@app.get("/api/spotify/track-metadata")
async def get_track_metadata(url: str):
    """
    Get track metadata from Spotify URL with enhanced error handling
    """
    request_id = f"meta_{int(time.time() * 1000)}"
    logger.info(f"[{request_id}] Metadata request for URL: {url}")
    
    try:
        extractor = SpotifyTrackExtractor()
        
        # Try API first
        track_info = await extractor.extract_from_api(url)
        
        # Fallback to oEmbed
        if not track_info:
            track_info = extractor.extract_from_oembed(url)
        
        if not track_info:
            raise HTTPException(status_code=400, detail="Could not extract track metadata from URL")
        
        logger.info(f"[{request_id}] Successfully extracted metadata: {track_info.name}")
        
        return {
            "name": track_info.name,
            "artists": track_info.artists,
            "searchQuery": track_info.search_query,
            "album": track_info.album,
            "duration": track_info.duration
        }
    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"Error extracting metadata: {str(e)}"
        logger.error(f"[{request_id}] {error_msg}")
        raise HTTPException(status_code=500, detail=error_msg)


@app.get("/health")
async def health_check():
    """Enhanced health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "version": "2.0.0",
        "service": "Song Downloader API"
    }


@app.get("/")
async def root():
    """Root endpoint redirect to health check"""
    return await health_check()

# AWS Lambda handler using Mangum
# The 'handler' is the entry point for AWS Lambda
# Set lifespan="off" for faster cold starts if not using background tasks
handler = Mangum(app, lifespan="off")

if __name__ == "__main__":
    import uvicorn
    # Local development server
    uvicorn.run(app, host="0.0.0.0", port=8000)