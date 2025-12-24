"""
Listening History Service
Tracks songs users listen to and uses them for analysis - Database version
"""

from typing import List, Dict, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, and_
from collections import defaultdict

from src.database.models import (
    ListeningHistory, Song, UserSong, SessionLocal
)
import secrets


class ListeningHistoryService:
    """Service for tracking and analyzing user listening history"""
    
    def __init__(self):
        """Initialize listening history service"""
        pass
    
    def _get_or_create_song(self, db: Session, title: str, artists: List[str], 
                           genre: Optional[List[str]] = None,
                           album: Optional[str] = None,
                           image: Optional[str] = None,
                           platform: Optional[str] = None,
                           platform_id: Optional[str] = None) -> Song:
        """Get existing song or create new one"""
        # Create a unique key for the song
        title_lower = title.lower().strip()
        artists_key = "|".join(sorted([a.lower().strip() for a in artists]))
        
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
                genre=genre or [],
                album=album or "",
                image=image or "",
                platform=platform or "unknown",
                platform_id=platform_id,
                created_at=datetime.utcnow(),
                last_updated=datetime.utcnow()
            )
            db.add(song)
            db.commit()
            db.refresh(song)
        
        return song
    
    def track_song(
        self,
        user_id: str,
        song_title: str,
        artists: List[str],
        source: str = "recommendation",
        platform: Optional[str] = None,
        metadata: Optional[Dict] = None,
        duration_seconds: Optional[float] = None,
        completed: bool = False
    ):
        """
        Track a song that a user listened to.
        
        Args:
            user_id: User identifier
            song_title: Song title
            artists: List of artist names
            source: Where the song came from (recommendation, search, etc.)
            platform: Platform used (spotify, youtube_music)
            metadata: Additional metadata (genre, album, etc.)
            duration_seconds: How long they listened
            completed: Did they listen to the full song?
        """
        db: Session = SessionLocal()
        try:
            # Get or create song
            song = self._get_or_create_song(
                db=db,
                title=song_title,
                artists=artists,
                genre=metadata.get("genre", []) if metadata else None,
                album=metadata.get("album", "") if metadata else None,
                image=metadata.get("image", "") if metadata else None,
                platform=platform,
                platform_id=metadata.get("platform_id") if metadata else None
            )
            
            # Create listening history entry
            entry = ListeningHistory(
                user_id=user_id,
                song_id=song.song_id,
                song_title=song_title,
                artists=artists,
                timestamp=datetime.utcnow(),
                source=source,
                platform=platform,
                duration_seconds=duration_seconds,
                completed=completed,
                extra_data=metadata or {}
            )
            
            db.add(entry)
            
            # Update or create user_song entry
            user_song = db.query(UserSong).filter(
                and_(
                    UserSong.user_id == user_id,
                    UserSong.song_id == song.song_id
                )
            ).first()
            
            if user_song:
                user_song.play_count += 1
                user_song.last_played = datetime.utcnow()
            else:
                user_song = UserSong(
                    user_id=user_id,
                    song_id=song.song_id,
                    source=source,
                    added_at=datetime.utcnow(),
                    play_count=1,
                    last_played=datetime.utcnow()
                )
                db.add(user_song)
            
            db.commit()
        finally:
            db.close()
    
    def get_user_history(
        self,
        user_id: str,
        limit: Optional[int] = None,
        days: Optional[int] = None
    ) -> List[Dict]:
        """
        Get listening history for a user.
        
        Args:
            user_id: User identifier
            limit: Maximum number of entries to return
            days: Only return entries from last N days
            
        Returns:
            List of listening history entries
        """
        db: Session = SessionLocal()
        try:
            query = db.query(ListeningHistory).filter(
                ListeningHistory.user_id == user_id
            )
            
            # Filter by days if specified
            if days:
                cutoff = datetime.utcnow() - timedelta(days=days)
                query = query.filter(ListeningHistory.timestamp >= cutoff)
            
            # Sort by timestamp (newest first)
            query = query.order_by(desc(ListeningHistory.timestamp))
            
            # Apply limit
            if limit:
                query = query.limit(limit)
            
            entries = query.all()
            
            result = [
                {
                    "song_title": entry.song_title,
                    "artists": entry.artists,
                    "timestamp": entry.timestamp.isoformat(),
                    "source": entry.source,
                    "platform": entry.platform,
                    "metadata": entry.extra_data or {},
                    "duration_seconds": entry.duration_seconds,
                    "completed": entry.completed
                }
                for entry in entries
            ]
            return result
        finally:
            db.close()
    
    def get_listened_songs(self, user_id: str, days: Optional[int] = None) -> List[Dict]:
        """
        Get unique songs a user has listened to.
        
        Args:
            user_id: User identifier
            days: Only consider songs from last N days
            
        Returns:
            List of unique songs with play counts
        """
        db: Session = SessionLocal()
        try:
            query = db.query(
                ListeningHistory.song_title,
                ListeningHistory.artists,
                func.count(ListeningHistory.id).label('play_count'),
                func.min(ListeningHistory.timestamp).label('first_played'),
                func.max(ListeningHistory.timestamp).label('last_played')
            ).filter(
                ListeningHistory.user_id == user_id
            )
            
            if days:
                cutoff = datetime.utcnow() - timedelta(days=days)
                query = query.filter(ListeningHistory.timestamp >= cutoff)
            
            results = query.group_by(
                ListeningHistory.song_title,
                ListeningHistory.artists
            ).order_by(desc('play_count')).all()
            
            return [
                {
                    "title": result.song_title,
                    "artists": result.artists,
                    "play_count": result.play_count,
                    "first_played": result.first_played.isoformat() if result.first_played else None,
                    "last_played": result.last_played.isoformat() if result.last_played else None
                }
                for result in results
            ]
        finally:
            db.close()
    
    def get_listening_stats(self, user_id: str, days: Optional[int] = None) -> Dict:
        """
        Get listening statistics for a user.
        
        Args:
            user_id: User identifier
            days: Only consider songs from last N days
            
        Returns:
            Dictionary with statistics
        """
        db: Session = SessionLocal()
        try:
            query = db.query(ListeningHistory).filter(
                ListeningHistory.user_id == user_id
            )
            
            if days:
                cutoff = datetime.utcnow() - timedelta(days=days)
                query = query.filter(ListeningHistory.timestamp >= cutoff)
            
            history = query.all()
            listened_songs = self.get_listened_songs(user_id, days=days)
            
            # Count by platform
            platform_counts = defaultdict(int)
            for entry in history:
                if entry.platform:
                    platform_counts[entry.platform] += 1
            
            # Count by source
            source_counts = defaultdict(int)
            for entry in history:
                source_counts[entry.source or "unknown"] += 1
            
            # Get most played artists
            artist_counts = defaultdict(int)
            for entry in history:
                for artist in entry.artists:
                    artist_counts[artist] += 1
            
            top_artists = sorted(artist_counts.items(), key=lambda x: x[1], reverse=True)[:10]
            
            return {
                "total_plays": len(history),
                "unique_songs": len(listened_songs),
                "platforms": dict(platform_counts),
                "sources": dict(source_counts),
                "top_artists": [{"artist": a, "plays": c} for a, c in top_artists],
                "most_played_songs": listened_songs[:10],
                "days_analyzed": days or "all"
            }
        finally:
            db.close()
    
    def get_songs_for_analysis(self, user_id: str, min_plays: int = 1, days: Optional[int] = 30) -> List[Dict]:
        """
        Get songs suitable for taste analysis.
        Filters out songs with low play counts and returns recent favorites.
        
        Args:
            user_id: User identifier
            min_plays: Minimum number of plays to include
            days: Only consider songs from last N days
            
        Returns:
            List of songs formatted for taste analysis
        """
        db: Session = SessionLocal()
        try:
            # Get listened songs with their song_ids to fetch genre from Song table
            query = db.query(
                ListeningHistory.song_id,
                ListeningHistory.song_title,
                ListeningHistory.artists,
                func.count(ListeningHistory.id).label('play_count')
            ).filter(
                ListeningHistory.user_id == user_id
            )
            
            if days:
                cutoff = datetime.utcnow() - timedelta(days=days)
                query = query.filter(ListeningHistory.timestamp >= cutoff)
            
            results = query.group_by(
                ListeningHistory.song_id,
                ListeningHistory.song_title,
                ListeningHistory.artists
            ).having(
                func.count(ListeningHistory.id) >= min_plays
            ).order_by(desc('play_count')).all()
            
            # Fetch genres from Song table
            analysis_songs = []
            for result in results:
                genre = []
                if result.song_id:
                    song = db.query(Song).filter(Song.song_id == result.song_id).first()
                    if song and song.genre:
                        genre = song.genre
                
                analysis_songs.append({
                    "title": result.song_title,
                    "artists": result.artists,
                    "genre": genre,
                    "play_count": result.play_count,
                    "weight": min(result.play_count / 5.0, 1.0)  # Weight based on plays (max 1.0)
                })
            
            return analysis_songs
        finally:
            db.close()


# Singleton instance
_listening_history_service = None

def get_listening_history_service() -> ListeningHistoryService:
    """Get singleton instance of ListeningHistoryService"""
    global _listening_history_service
    if _listening_history_service is None:
        _listening_history_service = ListeningHistoryService()
    return _listening_history_service
