"""
Song Storage Service
Manages persistent storage of songs using database
"""

from typing import List, Dict, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_
import logging
import secrets

from src.database.models import Song, UserSong, SessionLocal

logger = logging.getLogger(__name__)


class SongStorageService:
    """Service for storing and retrieving songs from database"""
    
    def __init__(self):
        """Initialize song storage service"""
        pass
    
    def _get_or_create_song(self, db: Session, song_data: Dict) -> Song:
        """Get existing song or create new one"""
        title = song_data.get("title", "").strip()
        artists = [a.strip() for a in song_data.get("artists", [])]
        title_lower = title.lower()
        
        # Try to find existing song
        song = db.query(Song).filter(
            func.lower(Song.title) == title_lower
        ).first()
        
        if not song:
            # Create new song
            song_id = f"song_{secrets.token_hex(12)}"
            song = Song(
                song_id=song_id,
                title=title,
                artists=artists,
                genre=song_data.get("genre", []),
                album=song_data.get("album", ""),
                image=song_data.get("image", ""),
                platform=song_data.get("platform", "unknown"),
                platform_id=song_data.get("platform_id"),
                youtube_video_id=song_data.get("youtube_video_id"),
                created_at=datetime.utcnow(),
                last_updated=datetime.utcnow(),
                extra_data=song_data.get("metadata", {})
            )
            db.add(song)
            db.commit()
            db.refresh(song)
        else:
            # Update existing song if new data provided
            if song_data.get("image") and not song.image:
                song.image = song_data.get("image")
            if song_data.get("youtube_video_id") and not song.youtube_video_id:
                song.youtube_video_id = song_data.get("youtube_video_id")
            if song_data.get("album") and not song.album:
                song.album = song_data.get("album")
            song.last_updated = datetime.utcnow()
            db.commit()
        
        return song
    
    def add_song(self, song: Dict, user_id: Optional[str] = None) -> bool:
        """
        Add a song to storage.
        
        Args:
            song: Song dictionary with title, artists, genre, etc.
            user_id: Optional user ID to associate song with user
            
        Returns:
            True if added, False if already exists
        """
        db: Session = SessionLocal()
        try:
            # Normalize song data
            normalized_song = {
                "title": song.get("title", "").strip(),
                "artists": [a.strip() for a in song.get("artists", [])],
                "genre": [g.strip() for g in song.get("genre", [])] if song.get("genre") else [],
                "album": song.get("album", "").strip(),
                "image": song.get("image", ""),
                "platform": song.get("platform", "unknown"),
                "platform_id": song.get("platform_id"),
                "youtube_video_id": song.get("youtube_video_id"),
                "metadata": song.get("metadata", {})
            }
            
            # Get or create song
            db_song = self._get_or_create_song(db, normalized_song)
            
            # Add to user songs if user_id provided
            if user_id:
                self.add_song_to_user(user_id, db_song.song_id, db, source="manual")
            
            return True
        except Exception as e:
            logger.error(f"Error adding song: {e}")
            db.rollback()
            return False
        finally:
            db.close()
    
    def add_song_to_user(self, user_id: str, song_id: str, db: Optional[Session] = None, source: str = "manual"):
        """Add song to user's collection"""
        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True
        
        try:
            # Check if already exists
            user_song = db.query(UserSong).filter(
                and_(
                    UserSong.user_id == user_id,
                    UserSong.song_id == song_id
                )
            ).first()
            
            if not user_song:
                user_song = UserSong(
                    user_id=user_id,
                    song_id=song_id,
                    source=source,
                    added_at=datetime.utcnow()
                )
                db.add(user_song)
                db.commit()
        except Exception as e:
            logger.error(f"Error adding song to user: {e}")
            db.rollback()
        finally:
            if should_close:
                db.close()
    
    def get_user_songs(self, user_id: str) -> Dict:
        """
        Get all songs for a user.
        
        Returns:
            Dictionary with seed_songs, listened_songs, favorite_songs
        """
        db: Session = SessionLocal()
        try:
            user_songs = db.query(UserSong).filter(
                UserSong.user_id == user_id
            ).all()
            
            seed_songs = []
            favorite_songs = []
            
            for user_song in user_songs:
                song = user_song.song
                song_dict = {
                    "title": song.title,
                    "artists": song.artists,
                    "album": song.album,
                    "image": song.image,
                    "genre": song.genre,
                    "platform": song.platform,
                    "platform_id": song.platform_id,
                    "youtube_video_id": song.youtube_video_id,
                    "added_at": user_song.added_at.isoformat() if user_song.added_at else None,
                    "source": user_song.source,
                    "play_count": user_song.play_count
                }
                
                seed_songs.append(song_dict)
                
                if user_song.is_favorite:
                    favorite_songs.append(song_dict)
            
            return {
                "seed_songs": seed_songs,
                "listened_songs": [],  # This comes from listening history
                "favorite_songs": favorite_songs
            }
        finally:
            db.close()
    
    def get_user_seed_songs(self, user_id: str) -> List[Dict]:
        """Get user's seed songs for analysis"""
        user_data = self.get_user_songs(user_id)
        return user_data.get("seed_songs", [])
    
    def get_all_songs(self) -> List[Dict]:
        """Get all stored songs"""
        db: Session = SessionLocal()
        try:
            songs = db.query(Song).all()
            return [
                {
                    "title": song.title,
                    "artists": song.artists,
                    "album": song.album,
                    "image": song.image,
                    "genre": song.genre,
                    "platform": song.platform,
                    "platform_id": song.platform_id,
                    "youtube_video_id": song.youtube_video_id,
                    "created_at": song.created_at.isoformat() if song.created_at else None,
                    "last_updated": song.last_updated.isoformat() if song.last_updated else None
                }
                for song in songs
            ]
        finally:
            db.close()
    
    def search_songs(self, query: str, limit: int = 20) -> List[Dict]:
        """
        Search songs by title, artist, or genre.
        
        Args:
            query: Search query
            limit: Maximum results
            
        Returns:
            List of matching songs
        """
        db: Session = SessionLocal()
        try:
            query_lower = query.lower()
            
            # Search in title (works for both SQLite and PostgreSQL)
            songs = db.query(Song).filter(
                func.lower(Song.title).contains(query_lower)
            ).limit(limit).all()
            
            # Also search in artists and genre by checking JSON arrays
            # This works for both SQLite and PostgreSQL
            additional_songs = db.query(Song).filter(
                Song.song_id.notin_([s.song_id for s in songs])  # Exclude already found
            ).all()
            
            # Filter by checking if query appears in artists or genre
            for song in additional_songs:
                if len(songs) >= limit:
                    break
                # Check artists
                artists_str = " ".join(song.artists or []).lower()
                genre_str = " ".join(song.genre or []).lower()
                if query_lower in artists_str or query_lower in genre_str:
                    songs.append(song)
            
            return [
                {
                    "title": song.title,
                    "artists": song.artists,
                    "album": song.album,
                    "image": song.image,
                    "genre": song.genre,
                    "platform": song.platform,
                    "platform_id": song.platform_id,
                    "youtube_video_id": song.youtube_video_id
                }
                for song in songs[:limit]
            ]
        finally:
            db.close()
    
    def get_songs_for_analysis(self, user_id: str) -> List[Dict]:
        """
        Get all songs for a user that should be used in analysis.
        Combines seed songs and listened songs.
        
        Returns:
            List of songs formatted for analysis
        """
        user_data = self.get_user_songs(user_id)
        seed_songs = user_data.get("seed_songs", [])
        
        # Get listened songs from listening history service
        from src.services.listening_history_service import get_listening_history_service
        history_service = get_listening_history_service()
        listened_songs = history_service.get_listened_songs(user_id, days=30)
        
        # Combine and format
        all_songs = []
        seen = set()
        
        for song in seed_songs:
            key = (song.get("title", "").lower(), "|".join([a.lower() for a in song.get("artists", [])]))
            if key not in seen:
                all_songs.append({
                    "title": song.get("title", ""),
                    "artists": song.get("artists", []),
                    "genre": song.get("genre", [])
                })
                seen.add(key)
        
        for song in listened_songs:
            key = (song.get("title", "").lower(), "|".join([a.lower() for a in song.get("artists", [])]))
            if key not in seen:
                all_songs.append({
                    "title": song.get("title", ""),
                    "artists": song.get("artists", []),
                    "genre": song.get("genre", [])
                })
                seen.add(key)
        
        return all_songs
    
    def clear_user_songs(self, user_id: str):
        """Clear all songs for a user"""
        db: Session = SessionLocal()
        try:
            db.query(UserSong).filter(
                UserSong.user_id == user_id
            ).delete()
            db.commit()
        except Exception as e:
            logger.error(f"Error clearing user songs: {e}")
            db.rollback()
        finally:
            db.close()


# Singleton instance
_song_storage_service = None

def get_song_storage_service() -> SongStorageService:
    """Get singleton instance of SongStorageService"""
    global _song_storage_service
    if _song_storage_service is None:
        _song_storage_service = SongStorageService()
    return _song_storage_service
