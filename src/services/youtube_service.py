"""
YouTube Service
Searches for YouTube videos and gets video IDs for music playback
Uses YouTube Data API v3 for accurate video search
Caches video IDs in database to avoid repeated API calls
"""

import os
import requests
from typing import Optional, Dict, List
import re
import json
import logging
import random
import time
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_

from src.database.models import Song, SessionLocal

# For fuzzy string matching
import difflib

logger = logging.getLogger(__name__)

# Try to import Google API client
try:
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    YOUTUBE_API_AVAILABLE = True
except ImportError:
    YOUTUBE_API_AVAILABLE = False
    logger.warning("google-api-python-client not available. YouTube API features disabled.")


class YouTubeService:
    """Service for finding YouTube videos for songs using YouTube Data API v3
    Supports multiple API keys with automatic rotation on quota exceeded errors
    """
    
    def __init__(self):
        logger.info("=" * 60)
        logger.info("Initializing YouTube Service...")
        logger.info(f"YOUTUBE_API_AVAILABLE: {YOUTUBE_API_AVAILABLE}")
        
        # Load multiple API keys from environment
        self.api_keys = self._load_api_keys()
        logger.info(f"Found {len(self.api_keys)} API key(s) to initialize")
        
        self.current_key_index = 0
        self.exhausted_keys = set()  # Track keys that have hit quota limits
        self.youtube_apis = {}  # Cache API client instances
        
        # Initialize API clients for all available keys
        if self.api_keys and YOUTUBE_API_AVAILABLE:
            logger.info(f"Attempting to initialize {len(self.api_keys)} API client(s)...")
            for i, key in enumerate(self.api_keys):
                try:
                    logger.debug(f"Initializing API client {i+1} with key: {key[:10]}...{key[-4:] if len(key) > 14 else ''}")
                    api_client = build('youtube', 'v3', developerKey=key)
                    self.youtube_apis[i] = api_client
                    logger.info(f"✓ YouTube API key {i+1}/{len(self.api_keys)} initialized successfully")
                except Exception as e:
                    logger.error(f"✗ Could not initialize YouTube API key {i+1}: {e}")
                    logger.error(f"  Key preview: {key[:10]}...{key[-4:] if len(key) > 14 else ''}")
                    logger.error(f"  Error type: {type(e).__name__}")
                    import traceback
                    logger.debug(f"  Full traceback: {traceback.format_exc()}")
                    self.exhausted_keys.add(i)
            
            if self.youtube_apis:
                logger.info(f"✓ YouTube API ready with {len(self.youtube_apis)} active key(s)")
            else:
                logger.error("✗ No YouTube API clients initialized - all keys failed")
                logger.error("  This could mean:")
                logger.error("  1. API keys are invalid")
                logger.error("  2. Network connectivity issues")
                logger.error("  3. API key format is incorrect")
        else:
            if not self.api_keys:
                logger.warning("⚠ No YouTube API keys found in environment. YouTube API features disabled. Falling back to web scraping.")
                logger.warning("   To enable: Set YOUTUBE_API_KEY in your .env file")
                # Show what we checked
                checked_vars = ["YOUTUBE_API_KEY", "YOUTUBE_API_KEY_1", "YOUTUBE_API_KEY_2", "YOUTUBE_API_KEY_3", "YOUTUBE_API_KEYS"]
                logger.warning(f"   Checked variables: {', '.join(checked_vars)}")
            elif not YOUTUBE_API_AVAILABLE:
                logger.warning("⚠ google-api-python-client library not installed. YouTube API features disabled. Falling back to web scraping.")
                logger.warning("   Install with: pip install google-api-python-client")
        
        logger.info("=" * 60)
        
        # Fallback: HTTP session for scraping (if API not available)
        self.session = requests.Session()
        self._randomize_session_headers()
    
    def _load_api_keys(self) -> List[str]:
        """Load multiple YouTube API keys from environment variables"""
        keys = []
        
        # Try to ensure .env is loaded (in case service is initialized before main.py loads it)
        try:
            from dotenv import load_dotenv
            from pathlib import Path
            # Try to load .env if not already loaded
            env_paths = [
                Path.cwd() / ".env",
                Path(__file__).parent.parent.parent / ".env",
            ]
            for env_path in env_paths:
                if env_path.exists():
                    load_dotenv(env_path, override=False)  # Don't override if already set
                    break
        except ImportError:
            pass  # dotenv not available, continue anyway
        except Exception as e:
            logger.debug(f"Could not load .env in YouTube service: {e}")
        
        # Try YOUTUBE_API_KEY (single key for backward compatibility)
        single_key = os.getenv("YOUTUBE_API_KEY", "").strip()
        if single_key and single_key not in ["", "your_youtube_api_key_here"]:
            keys.append(single_key)
            logger.info(f"✓ Found YOUTUBE_API_KEY: {single_key[:10]}...{single_key[-4:] if len(single_key) > 14 else ''}")
        
        # Try YOUTUBE_API_KEY_1, YOUTUBE_API_KEY_2, YOUTUBE_API_KEY_3
        for i in range(1, 4):
            key = os.getenv(f"YOUTUBE_API_KEY_{i}", "").strip()
            if key and key not in keys and key not in ["", "your_youtube_api_key_here", f"your_{'first' if i==1 else 'second' if i==2 else 'third'}_youtube_api_key_here"]:
                keys.append(key)
                logger.info(f"✓ Found YOUTUBE_API_KEY_{i}: {key[:10]}...{key[-4:] if len(key) > 14 else ''}")
        
        # Also try comma-separated list
        keys_env = os.getenv("YOUTUBE_API_KEYS", "").strip()
        if keys_env:
            for key in keys_env.split(','):
                key = key.strip()
                if key and key not in keys:
                    keys.append(key)
                    logger.info(f"✓ Found key from YOUTUBE_API_KEYS: {key[:10]}...{key[-4:] if len(key) > 14 else ''}")
        
        if keys:
            logger.info(f"✓ Loaded {len(keys)} YouTube API key(s) from environment")
        else:
            logger.warning("⚠ No valid YouTube API keys found in environment variables")
            logger.warning("   Checked: YOUTUBE_API_KEY, YOUTUBE_API_KEY_1/2/3, YOUTUBE_API_KEYS")
            logger.warning("   Make sure .env file exists and contains valid API keys")
            # Debug: Show what environment variables are actually set
            all_env_keys = [k for k in os.environ.keys() if "YOUTUBE" in k.upper()]
            if all_env_keys:
                logger.warning(f"   Found these YOUTUBE-related env vars: {', '.join(all_env_keys)}")
            else:
                logger.warning("   No YOUTUBE-related environment variables found at all")
        
        return keys
    
    def _randomize_session_headers(self):
        """Randomize HTTP headers to avoid detection"""
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15',
        ]
        
        accept_languages = [
            'en-US,en;q=0.9',
            'en-US,en;q=0.8',
            'en-GB,en;q=0.9',
            'en,en-US;q=0.9',
        ]
        
        self.session.headers.update({
            'User-Agent': random.choice(user_agents),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': random.choice(accept_languages),
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Cache-Control': 'max-age=0',
        })
    
    def _get_current_api_client(self):
        """Get the current active API client, rotating if needed"""
        if not self.youtube_apis:
            return None
        
        # Find next available key
        attempts = 0
        while attempts < len(self.api_keys):
            if self.current_key_index not in self.exhausted_keys and self.current_key_index in self.youtube_apis:
                return self.youtube_apis[self.current_key_index]
            
            # Move to next key
            self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)
            attempts += 1
        
        # All keys exhausted
        logger.error("All YouTube API keys have been exhausted")
        return None
    
    def _rotate_to_next_key(self):
        """Rotate to the next available API key"""
        if not self.api_keys:
            return False
        
        old_index = self.current_key_index
        self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)
        
        if self.current_key_index == old_index:
            # All keys exhausted
            logger.error("All YouTube API keys exhausted, cannot rotate")
            return False
        
        logger.info(f"Rotated to YouTube API key {self.current_key_index + 1}/{len(self.api_keys)}")
        return True
    
    def _is_valid_video_id(self, video_id: str) -> bool:
        """Validate that a video ID looks correct"""
        if not video_id or len(video_id) != 11:
            return False
        # YouTube video IDs are alphanumeric with hyphens and underscores
        if not re.match(r'^[a-zA-Z0-9_-]{11}$', video_id):
            return False
        # Filter out common invalid patterns
        invalid_patterns = ['AAAAAAAAAAA', 'undefined', 'null', 'true', 'false']
        if video_id in invalid_patterns:
            return False
        return True
    
    def _extract_video_ids_from_json(self, text: str) -> List[str]:
        """Extract video IDs from YouTube's initial data JSON"""
        video_ids = []
        try:
            # Find ytInitialData JSON object
            match = re.search(r'var ytInitialData = ({.+?});', text)
            if match:
                data = json.loads(match.group(1))
                # Navigate through the JSON structure to find video IDs
                contents = data.get('contents', {})
                two_column_search = contents.get('twoColumnSearchResultsRenderer', {})
                primary_contents = two_column_search.get('primaryContents', {})
                section_list = primary_contents.get('sectionListRenderer', {})
                contents_list = section_list.get('contents', [])
                
                for content in contents_list:
                    item_section = content.get('itemSectionRenderer', {})
                    items = item_section.get('contents', [])
                    for item in items:
                        video_renderer = item.get('videoRenderer', {})
                        if video_renderer:
                            video_id = video_renderer.get('videoId')
                            if video_id and self._is_valid_video_id(video_id):
                                video_ids.append(video_id)
        except Exception as e:
            logger.debug(f"Error extracting from JSON: {e}")
        
        return video_ids
    
    def _normalize_song_key(self, title: str, artists: list) -> str:
        """Generate a normalized key for song lookup"""
        title_clean = title.strip().lower()
        artists_clean = [a.strip().lower() for a in artists if a.strip()] if artists else []
        artists_str = " ".join(sorted(artists_clean[:2]))  # Use first 2 artists, sorted for consistency
        return f"{title_clean}|{artists_str}"
    
    def normalize_metadata(self, song_title: str, artists: list) -> Dict[str, any]:
        """
        Music metadata normalizer.
        Generates YouTube search queries that reliably return OFFICIAL audio or music video.
        
        Rules:
        - Remove parentheses, movie names, soundtrack info, and censored words
        - Remove "From", "feat.", "ft.", remix/version labels unless artist disambiguation is required
        - Prefer official audio over fan uploads
        - Do NOT hallucinate artists
        
        Returns JSON with normalized metadata and search queries.
        """
        # Normalize title
        normalized_title = song_title.strip()
        
        # Remove parentheses and their contents (movie names, soundtrack info, etc.)
        normalized_title = re.sub(r'\([^)]*\)', '', normalized_title)
        normalized_title = re.sub(r'\[[^\]]*\]', '', normalized_title)
        
        # Remove common soundtrack/movie prefixes
        patterns_to_remove = [
            r'^From\s+"[^"]*"\s*',  # "From "Movie Name""
            r'^From\s+[^:]*:\s*',  # "From Movie:"
            r'\(From\s+"[^"]*"\)',  # (From "Movie")
            r'\(From\s+[^)]*\)',  # (From Movie)
            r'\[From\s+"[^"]*"\]',  # [From "Movie"]
            r'\[From\s+[^\]]*\]',  # [From Movie]
            r'\(Soundtrack\)',  # (Soundtrack)
            r'\[Soundtrack\]',  # [Soundtrack]
            r'\(OST\)',  # (OST)
            r'\[OST\]',  # [OST]
        ]
        
        for pattern in patterns_to_remove:
            normalized_title = re.sub(pattern, '', normalized_title, flags=re.IGNORECASE)
        
        # Remove censored words (common patterns like "B*****s" or "F***")
        normalized_title = re.sub(r'\b\w*\*+\w*\b', '', normalized_title)
        
        # Remove "feat.", "ft.", "featuring" and featured artist names from title
        # But keep main artist names in the artists list
        feat_patterns = [
            r'\s+feat\.?\s+[^(]+',  # "feat. Artist"
            r'\s+ft\.?\s+[^(]+',  # "ft. Artist"
            r'\s+featuring\s+[^(]+',  # "featuring Artist"
            r'\s+\(feat\.?\s+[^)]+\)',  # "(feat. Artist)"
            r'\s+\(ft\.?\s+[^)]+\)',  # "(ft. Artist)"
        ]
        
        for pattern in feat_patterns:
            normalized_title = re.sub(pattern, '', normalized_title, flags=re.IGNORECASE)
        
        # Remove remix/version labels
        remix_patterns = [
            r'\s+\([^)]*remix[^)]*\)',  # (Remix)
            r'\s+\[[^\]]*remix[^\]]*\]',  # [Remix]
            r'\s+\([^)]*version[^)]*\)',  # (Version)
            r'\s+\[[^\]]*version[^\]]*\]',  # [Version]
            r'\s+\([^)]*edit[^)]*\)',  # (Edit)
            r'\s+\[[^\]]*edit[^\]]*\]',  # [Edit]
        ]
        
        for pattern in remix_patterns:
            normalized_title = re.sub(pattern, '', normalized_title, flags=re.IGNORECASE)
        
        # Clean up extra whitespace
        normalized_title = re.sub(r'\s+', ' ', normalized_title).strip()
        
        # Normalize artists list
        normalized_artists = []
        if artists:
            for artist in artists:
                artist_clean = artist.strip()
                if artist_clean:
                    # Remove common prefixes/suffixes
                    artist_clean = re.sub(r'^feat\.?\s+', '', artist_clean, flags=re.IGNORECASE)
                    artist_clean = re.sub(r'^ft\.?\s+', '', artist_clean, flags=re.IGNORECASE)
                    artist_clean = artist_clean.strip()
                    if artist_clean and artist_clean not in normalized_artists:
                        normalized_artists.append(artist_clean)
        
        # Generate optimized search queries
        artist_str = " ".join(normalized_artists[:2]) if normalized_artists else ""
        
        queries = []
        if normalized_title and artist_str:
            queries.append(f"{normalized_title} {artist_str}")
        elif normalized_title:
            # Fallback if no artist
            queries.append(f"{normalized_title} official audio")
            queries.append(f"{normalized_title} official")
            queries.append(normalized_title)
            
        # Add high-confidence "lyrics" query as fallback
        if normalized_title and artist_str:
            queries.append(f"{normalized_title} {artist_str} lyrics")
        
        return {
            "original_title": song_title,
            "normalized_title": normalized_title,
            "original_artists": artists,
            "normalized_artists": normalized_artists,
            "search_queries": queries
        }

    def _calculate_similarity(self, s1: str, s2: str) -> float:
        """Calculate string similarity using SequenceMatcher"""
        return difflib.SequenceMatcher(None, s1.lower(), s2.lower()).ratio()

    def _validate_result(self, 
                        video_title: str, 
                        channel_title: str,
                        duration_iso: Optional[str],
                        target_title: str, 
                        target_artists: List[str],
                        target_duration_ms: Optional[int] = None) -> float:
        """
        Validate a search result and return a confidence score (0.0 to 1.0).
        """
        score = 0.0
        video_title_lower = video_title.lower()
        channel_lower = channel_title.lower() if channel_title else ""
        
        # 1. Channel Validation (Boost for official channels)
        official_channels = ['vevo', 'official', 'topic', 'artist']
        if any(c in channel_lower for c in official_channels):
            score += 0.2
            
        # Check if channel name contains artist name
        if target_artists:
            if any(artist.lower() in channel_lower for artist in target_artists):
                score += 0.15

        # 2. Negative Filtering (Ban words)
        # If original title doesn't say "cover", "live", "remix", penalize video that does
        target_lower = target_title.lower()
        ban_words = ['cover', 'live', 'remix', 'karaoke', 'instrumental', 'concert']
        
        for word in ban_words:
            if word in video_title_lower and word not in target_lower:
                return 0.0  # Hard reject unwanted variants
                
        # 3. Title Similarity (Main Factor)
        # Check normalized titles
        sim_score = self._calculate_similarity(target_title, video_title)
        
        # Check if target title is contained in video title (common for 'Song Name - Artist')
        if target_title.lower() in video_title_lower:
            score += 0.4
        elif sim_score > 0.6:
            score += 0.4 * sim_score
        else:
            return 0.0 # Reject if titles are too different
            
        # 4. Duration Check (if available)
        if target_duration_ms and duration_iso:
            try:
                # Parse ISO 8601 duration (PT#M#S) to seconds
                # Simple parser for commonly returned format
                # Note: isodate library is better but avoiding new deps
                import re
                dur_match = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', duration_iso)
                if dur_match:
                    hours = int(dur_match.group(1) or 0)
                    minutes = int(dur_match.group(2) or 0)
                    seconds = int(dur_match.group(3) or 0)
                    total_seconds = hours * 3600 + minutes * 60 + seconds
                    
                    target_seconds = target_duration_ms / 1000
                    diff = abs(total_seconds - target_seconds)
                    
                    if diff < 10: # Exact match
                        score += 0.3
                    elif diff < 30: # Close match
                        score += 0.15
                    elif diff > 60: # Way off
                        score -= 0.3
            except:
                pass

        return min(1.0, score)
    
    def _get_cached_video_id(self, song_title: str, artists: list) -> Optional[str]:
        """
        Check database for cached YouTube video ID.
        Returns video ID if found, None otherwise.
        """
        db: Session = SessionLocal()
        try:
            title_lower = song_title.strip().lower()
            artists_lower = [a.strip().lower() for a in artists if a.strip()] if artists else []
            
            # Try exact title match first
            song = db.query(Song).filter(
                func.lower(Song.title) == title_lower
            ).first()
            
            if song and song.youtube_video_id:
                # Verify artists match (fuzzy match - at least one artist should match)
                if not artists_lower:
                    logger.info(f"Found cached video ID for '{song_title}' (no artist check)")
                    return song.youtube_video_id
                
                song_artists_lower = [a.lower() for a in (song.artists or [])]
                if any(artist in song_artists_lower for artist in artists_lower):
                    logger.info(f"Found cached video ID for '{song_title}' by {artists}")
                    return song.youtube_video_id
            
            # Try broader search - title contains and artist matches
            if artists_lower:
                songs = db.query(Song).filter(
                    func.lower(Song.title).contains(title_lower)
                ).all()
                
                for s in songs:
                    if s.youtube_video_id:
                        song_artists_lower = [a.lower() for a in (s.artists or [])]
                        if any(artist in song_artists_lower for artist in artists_lower):
                            logger.info(f"Found cached video ID for '{song_title}' by {artists} (fuzzy match)")
                            return s.youtube_video_id
            
            logger.debug(f"No cached video ID found for '{song_title}' by {artists}")
            return None
        except Exception as e:
            logger.error(f"Error checking cache for '{song_title}': {e}")
            return None
        finally:
            db.close()
    
    def _save_video_id_to_cache(self, song_title: str, artists: list, video_id: str) -> bool:
        """
        Save YouTube video ID to database cache.
        Returns True if saved successfully, False otherwise.
        """
        if not video_id or not self._is_valid_video_id(video_id):
            return False
        
        db: Session = SessionLocal()
        try:
            title_lower = song_title.strip().lower()
            artists_list = [a.strip() for a in artists if a.strip()] if artists else []
            
            # Try to find existing song
            song = db.query(Song).filter(
                func.lower(Song.title) == title_lower
            ).first()
            
            if song:
                # Update existing song with video ID if not already set
                if not song.youtube_video_id:
                    song.youtube_video_id = video_id
                    song.last_updated = datetime.utcnow()
                    db.commit()
                    logger.info(f"Cached video ID for existing song '{song_title}'")
                    return True
            else:
                # Create new song entry for caching
                import secrets
                song_id = f"song_{secrets.token_hex(12)}"
                song = Song(
                    song_id=song_id,
                    title=song_title.strip(),
                    artists=artists_list,
                    youtube_video_id=video_id,
                    platform="youtube_cache",
                    created_at=datetime.utcnow(),
                    last_updated=datetime.utcnow()
                )
                db.add(song)
                db.commit()
                logger.info(f"Cached video ID for new song '{song_title}'")
                return True
        except Exception as e:
            logger.error(f"Error saving video ID to cache for '{song_title}': {e}")
            db.rollback()
            return False
        finally:
            db.close()
    
    def search_video_id(self, song_title: str, artists: list) -> Optional[str]:
        """
        Search for YouTube video ID for a song.
        First checks database cache, then uses YouTube API if needed.
        Falls back to web scraping if API is not available.
        Caches results in database to avoid repeated API calls.
        
        Args:
            song_title: Song title
            artists: List of artist names
            
        Returns:
            YouTube video ID or None
        """
        if not song_title or not song_title.strip():
            logger.warning("Empty song title provided")
            return None
        
        # Step 1: Check database cache first
        cached_id = self._get_cached_video_id(song_title, artists)
        if cached_id:
            logger.info(f"Using cached video ID for '{song_title}' by {artists}")
            return cached_id
        
        # Step 2: Search using API or scraping (only if not in cache)
        logger.info(f"Video ID not in cache, searching for '{song_title}' by {artists}")
        video_id = None
        
        # Use YouTube Data API v3 if available
        if self.youtube_apis:
            video_id = self._search_with_api(song_title, artists)
        else:
            # Fallback to web scraping
            logger.warning("YouTube API not available, falling back to web scraping")
            video_id = self._search_with_scraping(song_title, artists)
        
        # Step 3: Cache the result if found
        if video_id:
            self._save_video_id_to_cache(song_title, artists, video_id)
        
        return video_id
    
    def _search_with_api(self, song_title: str, artists: list) -> Optional[str]:
        """
        Search for video using YouTube Data API v3 with automatic key rotation.
        Uses normalized metadata for better search results.
        """
        # Normalize metadata first
        normalized = self.normalize_metadata(song_title, artists)
        normalized_title = normalized["normalized_title"]
        normalized_artists = normalized["normalized_artists"]
        base_queries = normalized["search_queries"]
        
        # Add fallback queries if normalized queries exist
        if base_queries:
            artist_str = " ".join(normalized_artists[:2]) if normalized_artists else ""
            # Add music keyword variant
            if normalized_title and artist_str:
                base_queries.append(f"{normalized_title} {artist_str} music")
        else:
            # Fallback to original if normalization failed
            artist_str = " ".join(artists[:2]) if artists else ""
            base_queries = [
                f"{song_title} {artist_str} official audio",
                f"{song_title} {artist_str} official",
                f"{song_title} {artist_str}",
                f"{song_title} {artist_str} music"
            ]
        
        # Randomize query order to vary request patterns
        queries = random.sample(base_queries, len(base_queries)) if len(base_queries) > 1 else base_queries
        
        max_retries = len(self.api_keys) if self.api_keys else 1
        retry_count = 0
        
        while retry_count < max_retries:
            api_client = self._get_current_api_client()
            if not api_client:
                logger.warning("No available YouTube API clients")
                break
            
            current_key_num = self.current_key_index + 1
            
            for search_query in queries:
                try:
                    # Add small random delay to vary request timing
                    if retry_count > 0:
                        time.sleep(random.uniform(0.1, 0.5))
                    
                    # Randomize maxResults slightly to vary request patterns
                    max_results = random.choice([3, 4, 5])
                    
                    # Call YouTube Data API v3 search with randomized parameters
                    request = api_client.search().list(
                        part='id,snippet',
                        q=search_query,
                        type='video',
                        maxResults=max_results,
                        videoCategoryId='10',  # Music category
                        order='relevance',
                        safeSearch='none'  # Don't filter content
                    )
                    response = request.execute()
                    
                    if 'items' in response and len(response['items']) > 0:
                        # Filter results to find best match
                        for item in response['items']:
                            video_id = item['id']['videoId']
                            snippet = item.get('snippet', {})
                            title = snippet.get('title', '')
                            channel_title = snippet.get('channelTitle', '')
                            description = snippet.get('description', '')
                            # Note: contentDetails with duration requires an extra API call or different part
                            # For search 'part=snippet', we don't get duration. We'd need 'contentDetails' on video lookup.
                            # Skipping duration check for initial search result to save quota.
                            
                            # Validate video ID
                            if not self._is_valid_video_id(video_id):
                                continue

                            # Calculate Confidence Score
                            confidence = self._validate_result(
                                video_title=title,
                                channel_title=channel_title,
                                duration_iso=None, # Not available in search snippet
                                target_title=normalized_title or song_title,
                                target_artists=normalized_artists,
                                target_duration_ms=None # Need to pass this through if available
                            )
                            
                            logger.info(f"Checking video: {video_id} | Title: {title} | Score: {confidence:.2f}")

                            if confidence > 0.6:
                                logger.info(f"Found high confidence match ({confidence:.2f}): {video_id}")
                                return video_id
                            

                        
                        # If no perfect match, return first result
                        if response['items']:
                            video_id = response['items'][0]['id']['videoId']
                            if self._is_valid_video_id(video_id):
                                logger.info(f"Found video via API (key {current_key_num}, first result): {video_id} for {song_title}")
                                return video_id
                
                except HttpError as e:
                    if e.resp.status == 403:
                        error_content = str(e)
                        # Check if it's a quota error
                        if 'quota' in error_content.lower() or 'quotaExceeded' in error_content or 'dailyLimitExceeded' in error_content:
                            logger.warning(f"YouTube API key {current_key_num} quota exceeded, rotating to next key")
                            self.exhausted_keys.add(self.current_key_index)
                            
                            # Try next key
                            if self._rotate_to_next_key():
                                retry_count += 1
                                break  # Break from query loop, retry with new key
                            else:
                                logger.error("All API keys exhausted")
                                return None
                        else:
                            logger.error(f"YouTube API key {current_key_num} error (403): {error_content}")
                            # Mark as exhausted if it's an auth error
                            self.exhausted_keys.add(self.current_key_index)
                            if self._rotate_to_next_key():
                                retry_count += 1
                                break
                            else:
                                return None
                    else:
                        logger.warning(f"YouTube API error (key {current_key_num}) for query '{search_query}': {e}")
                        continue
                except Exception as e:
                    logger.debug(f"Error with YouTube API query '{search_query}' (key {current_key_num}): {e}")
                    continue
            
            # If we get here, all queries failed with current key, try next
            if retry_count < max_retries - 1:
                logger.warning(f"All queries failed with key {current_key_num}, trying next key")
                self.exhausted_keys.add(self.current_key_index)
                if self._rotate_to_next_key():
                    retry_count += 1
                else:
                    break
            else:
                break
        
        logger.error(f"Failed to find video after trying {retry_count + 1} API key(s)")
        return None
    
    def _search_with_scraping(self, song_title: str, artists: list) -> Optional[str]:
        """
        Fallback method: Search using web scraping.
        Used when YouTube API is not available.
        Randomizes headers and request patterns to avoid detection.
        """
        if not song_title or not song_title.strip():
            logger.warning("Empty song title provided for YouTube scraping")
            return None
        
        try:
            artist_str = " ".join(artists[:2]) if artists else ""
            
            queries = [
                f"{song_title} {artist_str} official audio",
                f"{song_title} {artist_str} official",
                f"{song_title} {artist_str} music",
                f"{song_title} {artist_str}"
            ]
            
            # Randomize query order
            queries = random.sample(queries, len(queries))
            
            logger.info(f"Scraping YouTube for: '{song_title}' by {artists}")
            
            for search_query in queries:
                try:
                    search_query = search_query.strip()
                    if not search_query:
                        continue
                    
                    # Randomize headers before each request
                    self._randomize_session_headers()
                    
                    # Add random delay between requests
                    time.sleep(random.uniform(0.5, 1.5))
                    
                    search_url = f"https://www.youtube.com/results?search_query={requests.utils.quote(search_query)}"
                    logger.debug(f"Trying search URL: {search_url}")
                    
                    response = self.session.get(search_url, timeout=15)
                    
                    if response.status_code == 200:
                        text = response.text
                        
                        # Extract from ytInitialData JSON
                        video_ids = self._extract_video_ids_from_json(text)
                        if video_ids:
                            logger.info(f"Found {len(video_ids)} video IDs from JSON for '{search_query}'")
                            for vid_id in video_ids:
                                if self._is_valid_video_id(vid_id):
                                    logger.info(f"Found valid video ID via scraping: {vid_id} for '{song_title}'")
                                    return vid_id
                        
                        # Extract from watch URLs
                        watch_pattern = r'/watch\?v=([a-zA-Z0-9_-]{11})'
                        watch_matches = re.findall(watch_pattern, text)
                        if watch_matches:
                            logger.info(f"Found {len(watch_matches)} video IDs from URLs for '{search_query}'")
                            for vid_id in watch_matches:
                                if self._is_valid_video_id(vid_id):
                                    logger.info(f"Found valid video ID via URL scraping: {vid_id} for '{song_title}'")
                                    return vid_id
                    else:
                        logger.warning(f"YouTube search returned status {response.status_code} for '{search_query}'")
                
                except requests.exceptions.Timeout:
                    logger.warning(f"YouTube search timeout for: '{search_query}'")
                    continue
                except Exception as e:
                    logger.debug(f"Error searching YouTube for '{search_query}': {e}")
                    continue
        
        except Exception as e:
            logger.error(f"YouTube scraping error for '{song_title}': {e}")
        
        logger.warning(f"Could not find YouTube video via scraping for '{song_title}' by {artists}")
        return None
    
    def get_embed_url(self, video_id: str) -> str:
        """
        Get YouTube embed URL for a video ID with ad-blocking parameters.
        Uses youtube-nocookie.com domain which has significantly fewer ads.
        """
        # Use youtube-nocookie.com domain (fewer ads, no cookies)
        # Add aggressive ad-blocking parameters
        params = [
            'autoplay=0',
            'enablejsapi=1',
            'origin=' + requests.utils.quote('http://localhost:8000'),
            'rel=0',  # Don't show related videos
            'modestbranding=1',  # Minimal branding
            'iv_load_policy=3',  # Don't show annotations
            'fs=0',  # Disable fullscreen
            'playsinline=1',
            'controls=0',  # Hide controls (we use our own)
            'disablekb=1',  # Disable keyboard controls
            'cc_load_policy=0',  # Don't load captions
            'loop=0',  # Don't loop
            'mute=0',  # Don't mute
            'start=0',  # Start at beginning
        ]
        # Use youtube-nocookie.com instead of youtube.com (fewer ads)
        return f"https://www.youtube-nocookie.com/embed/{video_id}?{'&'.join(params)}"
    
    def get_watch_url(self, video_id: str) -> str:
        """Get YouTube watch URL for a video ID"""
        return f"https://www.youtube.com/watch?v={video_id}"


# Singleton instance
_youtube_service = None

def get_youtube_service() -> YouTubeService:
    """Get singleton instance of YouTubeService"""
    global _youtube_service
    if _youtube_service is None:
        logger.info("=" * 60)
        logger.info("Creating YouTube Service instance...")
        _youtube_service = YouTubeService()
        # Log final status
        if _youtube_service.youtube_apis:
            logger.info(f"✓ YouTube Service ready with {len(_youtube_service.youtube_apis)} API client(s)")
        else:
            logger.warning("⚠ YouTube Service initialized but no API clients available - using web scraping fallback")
            if _youtube_service.api_keys:
                logger.warning(f"  Found {len(_youtube_service.api_keys)} key(s) but all failed to initialize")
                logger.warning("  Check the error messages above for details")
            else:
                logger.warning("  No API keys found - check your .env file")
            if not YOUTUBE_API_AVAILABLE:
                logger.warning("  google-api-python-client library not installed")
        logger.info("=" * 60)
    return _youtube_service

