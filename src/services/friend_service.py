"""
Friend Service
Handles friend requests, friendships, and user search by username
"""

from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from typing import List, Optional, Dict
from datetime import datetime
import logging

from src.database.models import User, FriendRequest, Friendship, SessionLocal

logger = logging.getLogger(__name__)


class FriendService:
    """Service for managing friendships and friend requests"""
    
    def __init__(self):
        """Initialize friend service"""
        pass
    
    def search_user_by_username(self, username: str, limit: int = 20) -> List[Dict]:
        """
        Search for users by username.
        
        Args:
            username: Username to search for (case-insensitive partial match)
            limit: Maximum number of results
            
        Returns:
            List of user dictionaries with user_id, username, name, email
        """
        db: Session = SessionLocal()
        try:
            username_lower = username.lower().strip()
            if not username_lower:
                return []
            
            # Search for users with matching username (case-insensitive)
            users = db.query(User).filter(
                User.username.ilike(f"%{username_lower}%")
            ).limit(limit).all()
            
            results = []
            for user in users:
                results.append({
                    "user_id": user.user_id,
                    "username": user.username,
                    "name": user.name,
                    "email": user.email  # Only return email for search results
                })
            
            return results
        except Exception as e:
            logger.error(f"Error searching users: {e}")
            return []
        finally:
            db.close()
    
    def get_user_by_username(self, username: str) -> Optional[Dict]:
        """
        Get user by exact username match.
        
        Args:
            username: Exact username
            
        Returns:
            User dictionary or None
        """
        db: Session = SessionLocal()
        try:
            user = db.query(User).filter(
                User.username.ilike(username.strip())
            ).first()
            
            if not user:
                return None
            
            return {
                "user_id": user.user_id,
                "username": user.username,
                "name": user.name,
                "email": user.email
            }
        except Exception as e:
            logger.error(f"Error getting user by username: {e}")
            return None
        finally:
            db.close()
    
    def send_friend_request(self, sender_id: str, receiver_username: str) -> Dict:
        """
        Send a friend request.
        
        Args:
            sender_id: User ID of sender
            receiver_username: Username of receiver
            
        Returns:
            Dictionary with status and request info
        """
        db: Session = SessionLocal()
        try:
            # Validate sender
            sender = db.query(User).filter(User.user_id == sender_id).first()
            if not sender:
                raise ValueError("Sender not found")
            
            # Find receiver by username
            receiver = db.query(User).filter(
                User.username.ilike(receiver_username.strip())
            ).first()
            
            if not receiver:
                raise ValueError("User not found")
            
            if receiver.user_id == sender_id:
                raise ValueError("Cannot send friend request to yourself")
            
            # Check if already friends
            existing_friendship = db.query(Friendship).filter(
                or_(
                    and_(Friendship.user1_id == sender_id, Friendship.user2_id == receiver.user_id),
                    and_(Friendship.user1_id == receiver.user_id, Friendship.user2_id == sender_id)
                )
            ).first()
            
            if existing_friendship:
                raise ValueError("Already friends with this user")
            
            # Check for existing pending request
            existing_request = db.query(FriendRequest).filter(
                or_(
                    and_(FriendRequest.sender_id == sender_id, FriendRequest.receiver_id == receiver.user_id),
                    and_(FriendRequest.sender_id == receiver.user_id, FriendRequest.receiver_id == sender_id)
                ),
                FriendRequest.status == "pending"
            ).first()
            
            if existing_request:
                if existing_request.sender_id == sender_id:
                    raise ValueError("Friend request already sent")
                else:
                    # Receiver already sent a request - auto-accept
                    return self.accept_friend_request(receiver.user_id, sender_id)
            
            # Create new friend request
            friend_request = FriendRequest(
                sender_id=sender_id,
                receiver_id=receiver.user_id,
                status="pending",
                created_at=datetime.utcnow()
            )
            
            db.add(friend_request)
            db.commit()
            db.refresh(friend_request)
            
            logger.info(f"Friend request sent: {sender_id} -> {receiver.user_id}")
            
            return {
                "status": "sent",
                "request_id": friend_request.id,
                "receiver": {
                    "user_id": receiver.user_id,
                    "username": receiver.username,
                    "name": receiver.name
                }
            }
        except ValueError:
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Error sending friend request: {e}")
            raise ValueError(f"Failed to send friend request: {str(e)}")
        finally:
            db.close()
    
    def accept_friend_request(self, receiver_id: str, sender_id: str) -> Dict:
        """
        Accept a friend request.
        
        Args:
            receiver_id: User ID of the person accepting (receiver)
            sender_id: User ID of the person who sent the request
            
        Returns:
            Dictionary with status and friendship info
        """
        db: Session = SessionLocal()
        try:
            # Find the friend request
            friend_request = db.query(FriendRequest).filter(
                FriendRequest.sender_id == sender_id,
                FriendRequest.receiver_id == receiver_id,
                FriendRequest.status == "pending"
            ).first()
            
            if not friend_request:
                raise ValueError("Friend request not found")
            
            # Update request status
            friend_request.status = "accepted"
            friend_request.responded_at = datetime.utcnow()
            
            # Create friendship (bidirectional)
            # Store with lower user_id first for consistency
            user1_id = min(sender_id, receiver_id)
            user2_id = max(sender_id, receiver_id)
            
            friendship = Friendship(
                user1_id=user1_id,
                user2_id=user2_id,
                created_at=datetime.utcnow()
            )
            
            db.add(friendship)
            db.commit()
            
            logger.info(f"Friend request accepted: {sender_id} <-> {receiver_id}")
            
            # Get sender info
            sender = db.query(User).filter(User.user_id == sender_id).first()
            
            return {
                "status": "accepted",
                "friendship": {
                    "user1_id": user1_id,
                    "user2_id": user2_id,
                    "created_at": friendship.created_at.isoformat()
                },
                "friend": {
                    "user_id": sender.user_id,
                    "username": sender.username,
                    "name": sender.name
                }
            }
        except ValueError:
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Error accepting friend request: {e}")
            raise ValueError(f"Failed to accept friend request: {str(e)}")
        finally:
            db.close()
    
    def reject_friend_request(self, receiver_id: str, sender_id: str) -> Dict:
        """
        Reject a friend request.
        
        Args:
            receiver_id: User ID of the person rejecting (receiver)
            sender_id: User ID of the person who sent the request
            
        Returns:
            Dictionary with status
        """
        db: Session = SessionLocal()
        try:
            friend_request = db.query(FriendRequest).filter(
                FriendRequest.sender_id == sender_id,
                FriendRequest.receiver_id == receiver_id,
                FriendRequest.status == "pending"
            ).first()
            
            if not friend_request:
                raise ValueError("Friend request not found")
            
            friend_request.status = "rejected"
            friend_request.responded_at = datetime.utcnow()
            
            db.commit()
            
            logger.info(f"Friend request rejected: {sender_id} -> {receiver_id}")
            
            return {
                "status": "rejected"
            }
        except ValueError:
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Error rejecting friend request: {e}")
            raise ValueError(f"Failed to reject friend request: {str(e)}")
        finally:
            db.close()
    
    def get_friend_requests(self, user_id: str, type: str = "received") -> List[Dict]:
        """
        Get friend requests for a user.
        
        Args:
            user_id: User ID
            type: "sent" or "received" (default: "received")
            
        Returns:
            List of friend request dictionaries
        """
        db: Session = SessionLocal()
        try:
            if type == "sent":
                requests = db.query(FriendRequest).filter(
                    FriendRequest.sender_id == user_id,
                    FriendRequest.status == "pending"
                ).order_by(FriendRequest.created_at.desc()).all()
                
                # Get receiver info
                results = []
                for req in requests:
                    receiver = db.query(User).filter(User.user_id == req.receiver_id).first()
                    if receiver:
                        results.append({
                            "request_id": req.id,
                            "user": {
                                "user_id": receiver.user_id,
                                "username": receiver.username,
                                "name": receiver.name
                            },
                            "status": req.status,
                            "created_at": req.created_at.isoformat()
                        })
            else:  # received
                requests = db.query(FriendRequest).filter(
                    FriendRequest.receiver_id == user_id,
                    FriendRequest.status == "pending"
                ).order_by(FriendRequest.created_at.desc()).all()
                
                # Get sender info
                results = []
                for req in requests:
                    sender = db.query(User).filter(User.user_id == req.sender_id).first()
                    if sender:
                        results.append({
                            "request_id": req.id,
                            "user": {
                                "user_id": sender.user_id,
                                "username": sender.username,
                                "name": sender.name
                            },
                            "status": req.status,
                            "created_at": req.created_at.isoformat()
                        })
            
            return results
        except Exception as e:
            logger.error(f"Error getting friend requests: {e}")
            return []
        finally:
            db.close()
    
    def get_friends(self, user_id: str) -> List[Dict]:
        """
        Get all friends of a user.
        
        Args:
            user_id: User ID
            
        Returns:
            List of friend dictionaries
        """
        db: Session = SessionLocal()
        try:
            # Get friendships where user is either user1 or user2
            friendships = db.query(Friendship).filter(
                or_(
                    Friendship.user1_id == user_id,
                    Friendship.user2_id == user_id
                )
            ).all()
            
            friends = []
            for friendship in friendships:
                # Get the other user
                other_user_id = friendship.user2_id if friendship.user1_id == user_id else friendship.user1_id
                other_user = db.query(User).filter(User.user_id == other_user_id).first()
                
                if other_user:
                    friends.append({
                        "user_id": other_user.user_id,
                        "username": other_user.username,
                        "name": other_user.name,
                        "friendship_created_at": friendship.created_at.isoformat()
                    })
            
            return friends
        except Exception as e:
            logger.error(f"Error getting friends: {e}")
            return []
        finally:
            db.close()
    
    def remove_friend(self, user_id: str, friend_id: str) -> Dict:
        """
        Remove a friend (delete friendship).
        
        Args:
            user_id: User ID
            friend_id: Friend's user ID to remove
            
        Returns:
            Dictionary with status
        """
        db: Session = SessionLocal()
        try:
            # Find friendship
            user1_id = min(user_id, friend_id)
            user2_id = max(user_id, friend_id)
            
            friendship = db.query(Friendship).filter(
                Friendship.user1_id == user1_id,
                Friendship.user2_id == user2_id
            ).first()
            
            if not friendship:
                raise ValueError("Friendship not found")
            
            db.delete(friendship)
            db.commit()
            
            logger.info(f"Friendship removed: {user_id} <-> {friend_id}")
            
            return {
                "status": "removed"
            }
        except ValueError:
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Error removing friend: {e}")
            raise ValueError(f"Failed to remove friend: {str(e)}")
        finally:
            db.close()
    
    def are_friends(self, user1_id: str, user2_id: str) -> bool:
        """
        Check if two users are friends.
        
        Args:
            user1_id: First user ID
            user2_id: Second user ID
            
        Returns:
            True if friends, False otherwise
        """
        db: Session = SessionLocal()
        try:
            user1_id_sorted = min(user1_id, user2_id)
            user2_id_sorted = max(user1_id, user2_id)
            
            friendship = db.query(Friendship).filter(
                Friendship.user1_id == user1_id_sorted,
                Friendship.user2_id == user2_id_sorted
            ).first()
            
            return friendship is not None
        except Exception as e:
            logger.error(f"Error checking friendship: {e}")
            return False
        finally:
            db.close()


# Singleton instance
_friend_service = None

def get_friend_service() -> FriendService:
    """Get singleton instance of FriendService"""
    global _friend_service
    if _friend_service is None:
        _friend_service = FriendService()
    return _friend_service

