"""
Authentication Service
Handles user registration, login, and authentication using database
"""

import hashlib
import secrets
from typing import Optional, Dict
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_
import logging

from src.database.models import User, Session as SessionModel, SessionLocal

logger = logging.getLogger(__name__)


class AuthService:
    """Service for user authentication and management"""
    
    def __init__(self):
        """Initialize authentication service"""
        pass
    
    def _hash_password(self, password: str) -> str:
        """Hash password using SHA-256 with salt"""
        # In production, use bcrypt or similar
        salt = secrets.token_hex(16)
        hash_obj = hashlib.sha256((password + salt).encode())
        return f"{salt}:{hash_obj.hexdigest()}"
    
    def _verify_password(self, password: str, hashed: str) -> bool:
        """Verify password against hash"""
        try:
            salt, hash_value = hashed.split(':')
            hash_obj = hashlib.sha256((password + salt).encode())
            return hash_obj.hexdigest() == hash_value
        except:
            return False
    
    def register_user(
        self,
        email: str,
        password: str,
        name: Optional[str] = None
    ) -> Dict:
        """
        Register a new user.
        
        Args:
            email: User email
            password: User password
            name: User's full name
            
        Returns:
            Dictionary with user_id and token
        """
        db: Session = SessionLocal()
        try:
            # Check if user already exists
            email_lower = email.lower().strip()
            existing_user = db.query(User).filter(
                User.email.ilike(email_lower)
            ).first()
            
            if existing_user:
                raise ValueError("Email already registered")
            
            # Create new user
            user_id = f"user_{secrets.token_hex(16)}"
            hashed_password = self._hash_password(password)
            
            user = User(
                user_id=user_id,
                email=email,
                name=name or email.split('@')[0],
                password_hash=hashed_password,
                created_at=datetime.utcnow(),
                profile={"preferences": {}, "settings": {}}
            )
            
            db.add(user)
            db.commit()
            db.refresh(user)
            
            # Create session
            token = self._create_session(user_id, db)
            
            logger.info(f"User registered: {email} ({user_id})")
            
            return {
                "user_id": user_id,
                "email": user.email,
                "name": user.name,
                "token": token
            }
        finally:
            db.close()
    
    def login_user(self, email: str, password: str) -> Dict:
        """
        Login a user.
        
        Args:
            email: User email
            password: User password
            
        Returns:
            Dictionary with user_id and token
        """
        db: Session = SessionLocal()
        try:
            email_lower = email.lower().strip()
            
            # Find user by email
            user = db.query(User).filter(
                User.email.ilike(email_lower)
            ).first()
            
            if not user:
                raise ValueError("Invalid email or password")
            
            # Verify password
            if not self._verify_password(password, user.password_hash):
                raise ValueError("Invalid email or password")
            
            # Update last login
            user.last_login = datetime.utcnow()
            db.commit()
            
            # Create session
            token = self._create_session(user.user_id, db)
            
            logger.info(f"User logged in: {email} ({user.user_id})")
            
            return {
                "user_id": user.user_id,
                "email": user.email,
                "name": user.name or "",
                "token": token
            }
        finally:
            db.close()
    
    def _create_session(self, user_id: str, db: Session) -> str:
        """Create a new session for user"""
        # Generate token
        token = secrets.token_urlsafe(32)
        
        # Store session (expires in 30 days)
        session = SessionModel(
            token=token,
            user_id=user_id,
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(days=30)
        )
        
        db.add(session)
        db.commit()
        
        return token
    
    def verify_token(self, token: str) -> Optional[str]:
        """
        Verify authentication token and return user_id.
        
        Args:
            token: Authentication token
            
        Returns:
            user_id if valid, None otherwise
        """
        db: Session = SessionLocal()
        try:
            session = db.query(SessionModel).filter(
                SessionModel.token == token
            ).first()
            
            if not session:
                return None
            
            # Check expiration
            if datetime.utcnow() > session.expires_at:
                # Remove expired session
                db.delete(session)
                db.commit()
                return None
            
            return session.user_id
        finally:
            db.close()
    
    def logout_user(self, token: str):
        """Logout user by removing session"""
        db: Session = SessionLocal()
        try:
            session = db.query(SessionModel).filter(
                SessionModel.token == token
            ).first()
            
            if session:
                db.delete(session)
                db.commit()
        finally:
            db.close()
    
    def get_user(self, user_id: str) -> Optional[Dict]:
        """Get user information"""
        db: Session = SessionLocal()
        try:
            user = db.query(User).filter(User.user_id == user_id).first()
            
            if not user:
                return None
            
            return {
                "user_id": user.user_id,
                "email": user.email,
                "name": user.name,
                "created_at": user.created_at.isoformat() if user.created_at else None,
                "last_login": user.last_login.isoformat() if user.last_login else None,
                "profile": user.profile or {}
            }
        finally:
            db.close()


# Singleton instance
_auth_service = None

def get_auth_service() -> AuthService:
    """Get singleton instance of AuthService"""
    global _auth_service
    if _auth_service is None:
        _auth_service = AuthService()
    return _auth_service
