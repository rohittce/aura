"""
Taste Profile Service
Manages persistent storage and updates of user taste profiles
"""

from typing import Dict, Optional, List
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import and_
import numpy as np
import logging

from src.database.models import TasteProfile, SessionLocal
from src.services.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)


class TasteProfileService:
    """Service for managing user taste profiles in database"""
    
    def __init__(self):
        self.embedding_service = EmbeddingService()
    
    def save_profile(self, user_id: str, profile_data: Dict) -> bool:
        """
        Save or update taste profile for a user.
        
        Args:
            user_id: User identifier
            profile_data: Profile dictionary with taste_vector, seed_songs, etc.
            
        Returns:
            True if saved successfully
        """
        db: Session = SessionLocal()
        try:
            # Check if profile exists
            existing = db.query(TasteProfile).filter(
                TasteProfile.user_id == user_id
            ).first()
            
            if existing:
                # Update existing profile
                existing.profile_data = profile_data
                existing.song_count = profile_data.get("song_count", len(profile_data.get("seed_songs", [])))
                existing.last_updated = datetime.utcnow()
            else:
                # Create new profile
                new_profile = TasteProfile(
                    user_id=user_id,
                    profile_data=profile_data,
                    song_count=profile_data.get("song_count", len(profile_data.get("seed_songs", []))),
                    created_at=datetime.utcnow(),
                    last_updated=datetime.utcnow()
                )
                db.add(new_profile)
            
            db.commit()
            logger.info(f"Saved taste profile for user {user_id}")
            return True
        except Exception as e:
            logger.error(f"Error saving taste profile: {e}")
            db.rollback()
            return False
        finally:
            db.close()
    
    def load_profile(self, user_id: str) -> Optional[Dict]:
        """
        Load taste profile for a user.
        
        Args:
            user_id: User identifier
            
        Returns:
            Profile dictionary or None if not found
        """
        db: Session = SessionLocal()
        try:
            profile = db.query(TasteProfile).filter(
                TasteProfile.user_id == user_id
            ).first()
            
            if profile:
                return profile.profile_data
            return None
        except Exception as e:
            logger.error(f"Error loading taste profile: {e}")
            return None
        finally:
            db.close()
    
    def update_profile_with_new_songs(
        self,
        user_id: str,
        new_songs: List[Dict],
        weight: float = 0.3
    ) -> Optional[Dict]:
        """
        Update existing taste profile by adding new songs incrementally.
        Uses weighted average to blend new songs with existing profile.
        
        Args:
            user_id: User identifier
            new_songs: List of new songs to add
            weight: Weight for new songs (0.0-1.0), rest goes to existing profile
            
        Returns:
            Updated profile dictionary or None if update failed
        """
        db: Session = SessionLocal()
        try:
            # Load existing profile
            existing_profile = db.query(TasteProfile).filter(
                TasteProfile.user_id == user_id
            ).first()
            
            if not existing_profile:
                logger.warning(f"No existing profile found for user {user_id}, creating new one")
                # Create new profile from new songs
                return self._create_profile_from_songs(user_id, new_songs)
            
            profile_data = existing_profile.profile_data
            existing_seed_songs = profile_data.get("seed_songs", [])
            existing_taste_vector = np.array(profile_data.get("taste_vector", []))
            
            # Generate embeddings for new songs
            new_embeddings = self.embedding_service.embed_songs_batch(new_songs)
            
            if not new_embeddings:
                logger.warning(f"No embeddings generated for new songs")
                return profile_data
            
            # Compute average embedding for new songs
            new_avg_embedding = np.mean([emb[0] for emb in new_embeddings], axis=0)
            
            # Blend with existing taste vector using weighted average
            if len(existing_taste_vector) > 0 and len(existing_taste_vector) == len(new_avg_embedding):
                # Weighted average: (1-weight) * existing + weight * new
                updated_taste_vector = (
                    (1 - weight) * existing_taste_vector + 
                    weight * new_avg_embedding
                )
            else:
                # If dimensions don't match or existing is empty, use new
                updated_taste_vector = new_avg_embedding
            
            # Merge seed songs (avoid duplicates)
            seen_songs = {
                (s.get("title", "").lower(), 
                 "|".join([a.lower() for a in s.get("artists", [])]))
                for s in existing_seed_songs
            }
            
            merged_seed_songs = existing_seed_songs.copy()
            for new_song in new_songs:
                song_key = (
                    new_song.get("title", "").lower(),
                    "|".join([a.lower() for a in new_song.get("artists", [])])
                )
                if song_key not in seen_songs:
                    merged_seed_songs.append(new_song)
                    seen_songs.add(song_key)
            
            # Update profile data
            updated_profile = {
                "user_id": user_id,
                "seed_songs": merged_seed_songs,
                "taste_vector": updated_taste_vector.tolist(),
                "song_count": len(merged_seed_songs),
                "status": "complete",
                "last_updated": datetime.utcnow().isoformat()
            }
            
            # Save updated profile
            existing_profile.profile_data = updated_profile
            existing_profile.song_count = len(merged_seed_songs)
            existing_profile.last_updated = datetime.utcnow()
            
            db.commit()
            logger.info(f"Updated taste profile for user {user_id} with {len(new_songs)} new songs")
            
            return updated_profile
            
        except Exception as e:
            logger.error(f"Error updating taste profile: {e}")
            db.rollback()
            return None
        finally:
            db.close()
    
    def _create_profile_from_songs(self, user_id: str, songs: List[Dict]) -> Optional[Dict]:
        """Create a new profile from songs"""
        try:
            # Generate embeddings
            embeddings = self.embedding_service.embed_songs_batch(songs)
            
            if not embeddings:
                return None
            
            # Compute average embedding
            avg_embedding = np.mean([emb[0] for emb in embeddings], axis=0)
            
            profile_data = {
                "user_id": user_id,
                "seed_songs": songs,
                "taste_vector": avg_embedding.tolist(),
                "song_count": len(songs),
                "status": "complete",
                "created_at": datetime.utcnow().isoformat(),
                "last_updated": datetime.utcnow().isoformat()
            }
            
            # Save to database
            self.save_profile(user_id, profile_data)
            
            return profile_data
        except Exception as e:
            logger.error(f"Error creating profile from songs: {e}")
            return None
    
    def delete_profile(self, user_id: str) -> bool:
        """Delete taste profile for a user"""
        db: Session = SessionLocal()
        try:
            profile = db.query(TasteProfile).filter(
                TasteProfile.user_id == user_id
            ).first()
            
            if profile:
                db.delete(profile)
                db.commit()
                logger.info(f"Deleted taste profile for user {user_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error deleting taste profile: {e}")
            db.rollback()
            return False
        finally:
            db.close()


# Singleton instance
_taste_profile_service = None

def get_taste_profile_service() -> TasteProfileService:
    """Get singleton instance of TasteProfileService"""
    global _taste_profile_service
    if _taste_profile_service is None:
        _taste_profile_service = TasteProfileService()
    return _taste_profile_service

