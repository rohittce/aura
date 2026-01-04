"""
Room Service
Handles music room creation, joining, leaving, and state management
"""

from sqlalchemy.orm import Session
from sqlalchemy import and_
from typing import List, Optional, Dict
from datetime import datetime, timedelta
import secrets
import logging

from src.database.models import MusicRoom, RoomParticipant, User, SessionLocal
from src.services.friend_service import get_friend_service

logger = logging.getLogger(__name__)


class RoomService:
    """Service for managing music rooms"""
    
    def __init__(self):
        """Initialize room service"""
        # In-memory cache for room state (for performance)
        # In production, use Redis for this
        self._room_cache = {}
    
    def create_room(
        self,
        host_id: str,
        name: Optional[str] = None,
        is_friends_only: bool = False
    ) -> Dict:
        """
        Create a new music room.
        
        Args:
            host_id: User ID of the host
            name: Optional room name
            is_friends_only: If True, only friends can join
            
        Returns:
            Room dictionary with room_id and details
        """
        db: Session = SessionLocal()
        try:
            # Validate host
            host = db.query(User).filter(User.user_id == host_id).first()
            if not host:
                raise ValueError("Host user not found")
            
            # Generate unique room ID (simple 6-char code)
            room_id = secrets.token_hex(3).upper()
            
            # Ensure uniqueness
            while db.query(MusicRoom).filter(MusicRoom.room_id == room_id).first():
                room_id = secrets.token_hex(3).upper()
            
            # Create room
            room = MusicRoom(
                room_id=room_id,
                host_id=host_id,
                name=name,
                is_friends_only=is_friends_only,
                playback_state={
                    "playing": False,
                    "position": 0.0,
                    "timestamp": datetime.utcnow().isoformat(),
                    "current_time": 0.0
                },
                created_at=datetime.utcnow(),
                last_activity=datetime.utcnow()
            )
            
            db.add(room)
            
            # Add host as participant
            participant = RoomParticipant(
                room_id=room_id,
                user_id=host_id,
                joined_at=datetime.utcnow(),
                last_seen=datetime.utcnow(),
                is_active=True
            )
            
            db.add(participant)
            db.commit()
            db.refresh(room)
            
            # Update cache
            self._room_cache[room_id] = {
                "room_id": room_id,
                "host_id": host_id,
                "name": name,
                "is_friends_only": is_friends_only,
                "current_song": None,
                "playback_state": room.playback_state,
                "participants": [host_id],
                "created_at": room.created_at.isoformat(),
                "last_activity": room.last_activity.isoformat()
            }
            
            logger.info(f"Room created: {room_id} by {host_id}")
            
            return {
                "room_id": room_id,
                "host_id": host_id,
                "name": name,
                "is_friends_only": is_friends_only,
                "created_at": room.created_at.isoformat()
            }
        except ValueError:
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Error creating room: {e}")
            raise ValueError(f"Failed to create room: {str(e)}")
        finally:
            db.close()
    
    def join_room(self, room_id: str, user_id: str) -> Dict:
        """
        Join a music room.
        
        Args:
            room_id: Room ID
            user_id: User ID joining
            
        Returns:
            Room state dictionary
        """
        db: Session = SessionLocal()
        room_id = room_id.upper() # Standardize to uppercase
        try:
            # Validate user
            user = db.query(User).filter(User.user_id == user_id).first()
            if not user:
                raise ValueError("User not found")
            
            # Get room
            room = db.query(MusicRoom).filter(MusicRoom.room_id == room_id).first()
            if not room:
                raise ValueError("Room not found")
            
            # Check if friends-only and not friends with host
            if room.is_friends_only and room.host_id:
                friend_service = get_friend_service()
                if room.host_id != user_id and not friend_service.are_friends(room.host_id, user_id):
                    raise ValueError("Room is friends-only and you are not friends with the host")
            
            # Check if already a participant
            existing = db.query(RoomParticipant).filter(
                and_(
                    RoomParticipant.room_id == room_id,
                    RoomParticipant.user_id == user_id
                )
            ).first()
            
            if existing:
                # Update last_seen and set active
                existing.last_seen = datetime.utcnow()
                existing.is_active = True
            else:
                # Add new participant
                participant = RoomParticipant(
                    room_id=room_id,
                    user_id=user_id,
                    joined_at=datetime.utcnow(),
                    last_seen=datetime.utcnow(),
                    is_active=True
                )
                db.add(participant)
            
            # Update room activity
            room.last_activity = datetime.utcnow()
            
            db.commit()
            
            # Get all participants
            participants = db.query(RoomParticipant).filter(
                RoomParticipant.room_id == room_id,
                RoomParticipant.is_active == True
            ).all()
            
            participant_ids = [p.user_id for p in participants]
            
            # Update cache
            if room_id in self._room_cache:
                if user_id not in self._room_cache[room_id]["participants"]:
                    self._room_cache[room_id]["participants"].append(user_id)
            
            logger.info(f"User {user_id} joined room {room_id}")
            
            return {
                "room_id": room_id,
                "host_id": room.host_id,
                "name": room.name,
                "is_friends_only": room.is_friends_only,
                "current_song": room.current_song,
                "playback_state": room.playback_state,
                "participants": participant_ids,
                "is_host": room.host_id == user_id
            }
        except ValueError:
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Error joining room: {e}")
            raise ValueError(f"Failed to join room: {str(e)}")
        finally:
            db.close()
    
    def leave_room(self, room_id: str, user_id: str) -> bool:
        """
        Leave a music room.
        
        Args:
            room_id: Room ID
            user_id: User ID
            
        Returns:
            True if successful, False otherwise
        """
        db: Session = SessionLocal()
        room_id = room_id.upper()
        try:
            room = db.query(MusicRoom).filter(MusicRoom.room_id == room_id).first()
            if not room:
                raise ValueError("Room not found")
            
            # Mark participant as inactive
            participant = db.query(RoomParticipant).filter(
                and_(
                    RoomParticipant.room_id == room_id,
                    RoomParticipant.user_id == user_id
                )
            ).first()
            
            if participant:
                participant.is_active = False
                participant.last_seen = datetime.utcnow()
            
            # If host is leaving, transfer to oldest active participant
            if room.host_id == user_id:
                active_participants = db.query(RoomParticipant).filter(
                    and_(
                        RoomParticipant.room_id == room_id,
                        RoomParticipant.is_active == True,
                        RoomParticipant.user_id != user_id
                    )
                ).order_by(RoomParticipant.joined_at.asc()).first()
                
                if active_participants:
                    room.host_id = active_participants.user_id
                    logger.info(f"Host transferred to {active_participants.user_id} in room {room_id}")
                else:
                    # No other participants - mark room for cleanup
                    logger.info(f"Room {room_id} is now empty, will be cleaned up")
            
            room.last_activity = datetime.utcnow()
            db.commit()
            
            # Update cache
            if room_id in self._room_cache:
                if user_id in self._room_cache[room_id]["participants"]:
                    self._room_cache[room_id]["participants"].remove(user_id)
                self._room_cache[room_id]["host_id"] = room.host_id
            
            logger.info(f"User {user_id} left room {room_id}")
            
            return {
                "status": "left",
                "room_id": room_id
            }
        except ValueError:
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Error leaving room: {e}")
            raise ValueError(f"Failed to leave room: {str(e)}")
        finally:
            db.close()
    
    def get_room_state(self, room_id: str) -> Optional[Dict]:
        """
        Get current room state.
        
        Args:
            room_id: Room ID
            
        Returns:
            Room state dictionary or None
        """
        db: Session = SessionLocal()
        room_id = room_id.upper()
        try:
            room = db.query(MusicRoom).filter(MusicRoom.room_id == room_id).first()
            if not room:
                return None
            
            # Get active participants
            participants = db.query(RoomParticipant).filter(
                and_(
                    RoomParticipant.room_id == room_id,
                    RoomParticipant.is_active == True
                )
            ).all()
            
            participant_ids = [p.user_id for p in participants]
            
            return {
                "room_id": room_id,
                "host_id": room.host_id,
                "name": room.name,
                "is_friends_only": room.is_friends_only,
                "current_song": room.current_song,
                "playback_state": room.playback_state,
                "participants": participant_ids,
                "created_at": room.created_at.isoformat(),
                "last_activity": room.last_activity.isoformat()
            }
        except Exception as e:
            logger.error(f"Error getting room state: {e}")
            return None
        finally:
            db.close()
    
    def update_room_state(
        self,
        room_id: str,
        user_id: str,
        current_song: Optional[Dict] = None,
        playback_state: Optional[Dict] = None
    ) -> Dict:
        """
        Update room state (host only).
        
        Args:
            room_id: Room ID
            user_id: User ID (must be host)
            current_song: Optional song metadata
            playback_state: Optional playback state
            
        Returns:
            Updated room state
        """
        db: Session = SessionLocal()
        room_id = room_id.upper()
        try:
            room = db.query(MusicRoom).filter(MusicRoom.room_id == room_id).first()
            if not room:
                raise ValueError("Room not found")
            
            if room.host_id != user_id:
                raise ValueError("Only host can update room state")
            
            if current_song is not None:
                room.current_song = current_song
            
            if playback_state is not None:
                # Update timestamp to server time
                playback_state["timestamp"] = datetime.utcnow().isoformat()
                room.playback_state = playback_state
            
            room.last_activity = datetime.utcnow()
            db.commit()
            db.refresh(room)
            
            # Update cache
            if room_id in self._room_cache:
                if current_song is not None:
                    self._room_cache[room_id]["current_song"] = current_song
                if playback_state is not None:
                    self._room_cache[room_id]["playback_state"] = playback_state
            
            return {
                "room_id": room_id,
                "current_song": room.current_song,
                "playback_state": room.playback_state
            }
        except ValueError:
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Error updating room state: {e}")
            raise ValueError(f"Failed to update room state: {str(e)}")
        finally:
            db.close()
    
    def get_user_rooms(self, user_id: str) -> List[Dict]:
        """
        Get all rooms a user is currently in.
        
        Args:
            user_id: User ID
            
        Returns:
            List of room dictionaries
        """
        db: Session = SessionLocal()
        try:
            # Get active participants
            participants = db.query(RoomParticipant).filter(
                and_(
                    RoomParticipant.user_id == user_id,
                    RoomParticipant.is_active == True
                )
            ).all()
            
            rooms = []
            for participant in participants:
                room = db.query(MusicRoom).filter(
                    MusicRoom.room_id == participant.room_id
                ).first()
                
                if room:
                    rooms.append({
                        "room_id": room.room_id,
                        "host_id": room.host_id,
                        "name": room.name,
                        "is_friends_only": room.is_friends_only,
                        "is_host": room.host_id == user_id,
                        "joined_at": participant.joined_at.isoformat()
                    })
            
            return rooms
        except Exception as e:
            logger.error(f"Error getting user rooms: {e}")
            return []
        finally:
            db.close()
    
    def cleanup_empty_rooms(self, max_age_hours: int = 24) -> int:
        """
        Clean up empty rooms older than max_age_hours.
        
        Args:
            max_age_hours: Maximum age in hours for empty rooms
            
        Returns:
            Number of rooms cleaned up
        """
        db: Session = SessionLocal()
        try:
            cutoff_time = datetime.utcnow() - timedelta(hours=max_age_hours)
            
            # Find rooms with no active participants
            rooms = db.query(MusicRoom).filter(
                MusicRoom.last_activity < cutoff_time
            ).all()
            
            cleaned = 0
            for room in rooms:
                active_count = db.query(RoomParticipant).filter(
                    and_(
                        RoomParticipant.room_id == room.room_id,
                        RoomParticipant.is_active == True
                    )
                ).count()
                
                if active_count == 0:
                    # Remove from cache
                    if room.room_id in self._room_cache:
                        del self._room_cache[room.room_id]
                    
                    db.delete(room)
                    cleaned += 1
            
            db.commit()
            logger.info(f"Cleaned up {cleaned} empty rooms")
            return cleaned
        except Exception as e:
            db.rollback()
            logger.error(f"Error cleaning up rooms: {e}")
            return 0
        finally:
            db.close()


# Singleton instance
_room_service = None

def get_room_service() -> RoomService:
    """Get singleton instance of RoomService"""
    global _room_service
    if _room_service is None:
        _room_service = RoomService()
    return _room_service

