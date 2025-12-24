"""
Song Search Service
Searches for songs and retrieves metadata including images
"""

import requests
import json
from typing import List, Dict, Optional
from urllib.parse import quote
import time
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SongSearchService:
    """Service for searching songs and getting metadata"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def search_songs(self, query: str, limit: int = 20) -> List[Dict]:
        """
        Search for songs using multiple sources
        
        Args:
            query: Search query (song title, artist, etc.)
            limit: Maximum number of results
            
        Returns:
            List of song dictionaries with metadata
        """
        if not query or len(query.strip()) < 1:
            logger.warning("Empty search query provided")
            return []
        
        query = query.strip()
        results = []
        
        # Primary source: iTunes API (free, no auth, reliable)
        try:
            logger.info(f"Searching iTunes for: '{query}'")
            itunes_results = self._search_itunes(query, limit)
            if itunes_results:
                results.extend(itunes_results)
                logger.info(f"Found {len(itunes_results)} results from iTunes for query: {query}")
            else:
                logger.warning(f"No iTunes results for query: {query}")
        except Exception as e:
            logger.error(f"iTunes search failed: {e}", exc_info=True)
        
        # Fallback: Try Last.fm if iTunes didn't return enough
        if len(results) < limit:
            try:
                logger.info(f"Searching Last.fm for additional results: '{query}'")
                lastfm_results = self._search_lastfm(query, limit - len(results))
                if lastfm_results:
                    results.extend(lastfm_results)
                    logger.info(f"Found {len(lastfm_results)} additional results from Last.fm")
            except Exception as e:
                logger.error(f"Last.fm search failed: {e}", exc_info=True)
        
        # Remove duplicates based on title + artist
        seen = set()
        unique_results = []
        for song in results:
            title = song.get('title', '').lower().strip()
            artist = (song.get('artists', [''])[0] if song.get('artists') else '').lower().strip()
            key = (title, artist)
            if key not in seen and key != ('', '') and title:
                seen.add(key)
                unique_results.append(song)
                if len(unique_results) >= limit:
                    break
        
        logger.info(f"Total unique results: {len(unique_results)} for query: '{query}'")
        return unique_results[:limit]
    
    def _search_lastfm(self, query: str, limit: int) -> List[Dict]:
        """Search using Last.fm API"""
        try:
            # Last.fm API - removed API key requirement (not needed for basic search)
            url = "https://ws.audioscrobbler.com/2.0/"
            params = {
                'method': 'track.search',
                'track': query,
                'format': 'json',
                'limit': min(limit, 30)  # Last.fm limit
            }
            
            response = self.session.get(url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                tracks = data.get('results', {}).get('trackmatches', {}).get('track', [])
                
                if not tracks:
                    logger.info(f"No Last.fm results for query: {query}")
                    return []
                
                results = []
                for track in tracks[:limit]:
                    track_name = track.get('name', '').strip()
                    artist_name = track.get('artist', '').strip()
                    
                    if not track_name:
                        continue
                    
                    # Get track info for image (non-blocking, don't wait if slow)
                    try:
                        track_info = self._get_lastfm_track_info(artist_name, track_name)
                        image = track_info.get('image', '')
                    except:
                        image = ''
                    
                    results.append({
                        'title': track_name,
                        'artists': [artist_name] if artist_name else ['Unknown Artist'],
                        'image': image,
                        'genre': [],
                        'platform_id': track.get('mbid', ''),
                        'source': 'lastfm'
                    })
                
                logger.info(f"Last.fm search successful: {len(results)} results")
                return results
            else:
                logger.warning(f"Last.fm API returned status {response.status_code}")
        except requests.exceptions.Timeout:
            logger.warning("Last.fm search timeout")
        except Exception as e:
            logger.error(f"Last.fm error: {e}", exc_info=True)
        
        return []
    
    def _get_lastfm_track_info(self, artist: str, track: str) -> Dict:
        """Get detailed track info including image (non-blocking, quick timeout)"""
        try:
            if not artist or not track:
                return {'image': '', 'genre': []}
            
            url = "https://ws.audioscrobbler.com/2.0/"
            params = {
                'method': 'track.getInfo',
                'artist': artist,
                'track': track,
                'format': 'json'
            }
            
            # Quick timeout - don't block search if this is slow
            response = self.session.get(url, params=params, timeout=3)
            if response.status_code == 200:
                data = response.json()
                track_data = data.get('track', {})
                album = track_data.get('album', {})
                
                # Get largest image
                images = album.get('image', [])
                image_url = ''
                if images:
                    # Last.fm provides images in different sizes, get the largest
                    for img in reversed(images):
                        if img.get('#text'):
                            image_url = img.get('#text')
                            break
                
                return {
                    'image': image_url,
                    'genre': [tag.get('name', '') for tag in track_data.get('toptags', {}).get('tag', [])[:3]]
                }
        except requests.exceptions.Timeout:
            # Timeout is OK - return empty, don't block search
            pass
        except Exception as e:
            logger.debug(f"Last.fm track info error: {e}")
        
        return {'image': '', 'genre': []}
    
    def _search_itunes(self, query: str, limit: int) -> List[Dict]:
        """Search using iTunes API (free, no auth)"""
        try:
            url = "https://itunes.apple.com/search"
            params = {
                'term': query,
                'media': 'music',
                'limit': limit,
                'entity': 'song'
            }
            
            # Add retry logic for reliability
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    response = self.session.get(url, params=params, timeout=15)
                    if response.status_code == 200:
                        data = response.json()
                        results = []
                        
                        # Check if we got results
                        items = data.get('results', [])
                        if not items:
                            logger.warning(f"No iTunes results for query: {query}")
                            return []
                        
                        for item in items:
                            # Get high-quality artwork
                            artwork_url = item.get('artworkUrl100', '')
                            if artwork_url:
                                # Try to get higher quality (600x600)
                                artwork_url = artwork_url.replace('100x100bb', '600x600bb')
                                # Fallback to 300x300 if 600x600 doesn't work
                                if '100x100bb' in artwork_url:
                                    artwork_url = artwork_url.replace('100x100bb', '300x300bb')
                            
                            # Only add if we have a title
                            track_name = item.get('trackName', '').strip()
                            if track_name:
                                results.append({
                                    'title': track_name,
                                    'artists': [item.get('artistName', 'Unknown Artist')],
                                    'image': artwork_url,
                                    'genre': [item.get('primaryGenreName', '')] if item.get('primaryGenreName') else [],
                                    'platform_id': str(item.get('trackId', '')),
                                    'album': item.get('collectionName', ''),
                                    'source': 'itunes'
                                })
                        
                        logger.info(f"iTunes search successful: {len(results)} results for '{query}'")
                        return results
                    elif response.status_code == 429:
                        # Rate limited - wait and retry
                        wait_time = (attempt + 1) * 2
                        logger.warning(f"iTunes rate limited, waiting {wait_time}s before retry...")
                        time.sleep(wait_time)
                        continue
                    else:
                        logger.error(f"iTunes API returned status {response.status_code}")
                        break
                except requests.exceptions.Timeout:
                    if attempt < max_retries - 1:
                        logger.warning(f"iTunes search timeout, retrying... (attempt {attempt + 1}/{max_retries})")
                        time.sleep(1)
                        continue
                    else:
                        logger.error("iTunes search timeout - request took too long after retries")
                        break
                except requests.exceptions.RequestException as e:
                    if attempt < max_retries - 1:
                        logger.warning(f"iTunes network error, retrying... (attempt {attempt + 1}/{max_retries}): {e}")
                        time.sleep(1)
                        continue
                    else:
                        logger.error(f"iTunes search network error: {e}")
                        break
        except Exception as e:
            logger.error(f"iTunes search error: {e}", exc_info=True)
        
        return []
    
    def search_by_spotify_id(self, spotify_id: str) -> Optional[Dict]:
        """Get song info by Spotify ID (requires Spotify API)"""
        # Placeholder - would need Spotify API credentials
        return None
    
    def get_song_image_fallback(self, title: str, artist: str) -> str:
        """Fallback method to get song image using web scraping"""
        try:
            # Try to get image from Last.fm
            track_info = self._get_lastfm_track_info(artist, title)
            if track_info.get('image'):
                return track_info['image']
        except:
            pass
        
        return ''


# Singleton instance
_song_search_service = None

def get_song_search_service() -> SongSearchService:
    """Get singleton instance of SongSearchService"""
    global _song_search_service
    if _song_search_service is None:
        _song_search_service = SongSearchService()
    return _song_search_service

