"""
Database Models
SQLAlchemy models for user data and listening history
"""

from sqlalchemy import create_engine, Column, String, Integer, DateTime, Text, JSON, ForeignKey, Float, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import os

Base = declarative_base()


class User(Base):
    """User model"""
    __tablename__ = "users"
    
    user_id = Column(String(255), primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(50), unique=True, nullable=True, index=True)  # Unique username for friend search
    name = Column(String(255), nullable=True)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_login = Column(DateTime, nullable=True)
    profile = Column(JSON, default=dict)  # User preferences and settings
    
    # Relationships
    sessions = relationship("Session", back_populates="user", cascade="all, delete-orphan")
    listening_history = relationship("ListeningHistory", back_populates="user", cascade="all, delete-orphan")
    user_songs = relationship("UserSong", back_populates="user", cascade="all, delete-orphan")
    sent_friend_requests = relationship("FriendRequest", foreign_keys="FriendRequest.sender_id", back_populates="sender", cascade="all, delete-orphan")
    received_friend_requests = relationship("FriendRequest", foreign_keys="FriendRequest.receiver_id", back_populates="receiver", cascade="all, delete-orphan")
    friendships_as_user1 = relationship("Friendship", foreign_keys="Friendship.user1_id", back_populates="user1", cascade="all, delete-orphan")
    friendships_as_user2 = relationship("Friendship", foreign_keys="Friendship.user2_id", back_populates="user2", cascade="all, delete-orphan")
    room_participants = relationship("RoomParticipant", back_populates="user", cascade="all, delete-orphan")


class Session(Base):
    """User session model"""
    __tablename__ = "sessions"
    
    token = Column(String(255), primary_key=True)
    user_id = Column(String(255), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    
    # Relationships
    user = relationship("User", back_populates="sessions")


class Song(Base):
    """Song model - stores song metadata"""
    __tablename__ = "songs"
    
    song_id = Column(String(255), primary_key=True)
    title = Column(String(500), nullable=False, index=True)
    artists = Column(JSON, nullable=False)  # List of artist names
    genre = Column(JSON, default=list)  # List of genres
    album = Column(String(500), nullable=True)
    image = Column(Text, nullable=True)
    platform = Column(String(50), default="unknown")
    platform_id = Column(String(255), nullable=True)
    youtube_video_id = Column(String(50), nullable=True, index=True)  # Indexed for faster cache lookups
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    extra_data = Column(JSON, default=dict)  # Additional metadata
    
    # Relationships
    user_songs = relationship("UserSong", back_populates="song", cascade="all, delete-orphan")
    listening_history = relationship("ListeningHistory", back_populates="song")


class UserSong(Base):
    """User's song collection - links users to songs"""
    __tablename__ = "user_songs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(255), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True)
    song_id = Column(String(255), ForeignKey("songs.song_id", ondelete="CASCADE"), nullable=False, index=True)
    source = Column(String(50), default="manual")  # manual, recommendation, search, etc.
    added_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    is_favorite = Column(Boolean, default=False)
    play_count = Column(Integer, default=0)
    last_played = Column(DateTime, nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="user_songs")
    song = relationship("Song", back_populates="user_songs")


class ListeningHistory(Base):
    """Listening history - tracks when users listen to songs"""
    __tablename__ = "listening_history"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(255), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True)
    song_id = Column(String(255), ForeignKey("songs.song_id", ondelete="CASCADE"), nullable=True, index=True)
    song_title = Column(String(500), nullable=False)  # Store title even if song is deleted
    artists = Column(JSON, nullable=False)  # Store artists even if song is deleted
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    source = Column(String(50), default="recommendation")  # recommendation, search, etc.
    platform = Column(String(50), nullable=True)
    duration_seconds = Column(Float, nullable=True)  # How long they listened
    completed = Column(Boolean, default=False)  # Did they listen to the full song?
    extra_data = Column(JSON, default=dict)  # Additional metadata
    
    # Relationships
    user = relationship("User", back_populates="listening_history")
    song = relationship("Song", back_populates="listening_history")


class TasteProfile(Base):
    """User taste profile for recommendations"""
    __tablename__ = "taste_profiles"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(255), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    profile_data = Column(JSON, nullable=False)  # Taste vector, preferences, etc.
    song_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class FriendRequest(Base):
    """Friend request model"""
    __tablename__ = "friend_requests"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    sender_id = Column(String(255), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True)
    receiver_id = Column(String(255), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(20), default="pending")  # pending, accepted, rejected
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    responded_at = Column(DateTime, nullable=True)
    
    # Relationships
    sender = relationship("User", foreign_keys=[sender_id], back_populates="sent_friend_requests")
    receiver = relationship("User", foreign_keys=[receiver_id], back_populates="received_friend_requests")
    
    # Unique constraint: one pending request per pair
    __table_args__ = (
        {"sqlite_autoincrement": True},
    )


class Friendship(Base):
    """Friendship model - bidirectional relationship"""
    __tablename__ = "friendships"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user1_id = Column(String(255), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True)
    user2_id = Column(String(255), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    user1 = relationship("User", foreign_keys=[user1_id], back_populates="friendships_as_user1")
    user2 = relationship("User", foreign_keys=[user2_id], back_populates="friendships_as_user2")
    
    # Unique constraint: ensure no duplicate friendships
    __table_args__ = (
        {"sqlite_autoincrement": True},
    )


class MusicRoom(Base):
    """Music room model - for synced listening sessions"""
    __tablename__ = "music_rooms"
    
    room_id = Column(String(255), primary_key=True)
    host_id = Column(String(255), ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True, index=True)
    name = Column(String(255), nullable=True)  # Optional room name
    is_friends_only = Column(Boolean, default=False)  # Only friends can join
    current_song = Column(JSON, nullable=True)  # Current song metadata
    playback_state = Column(JSON, default=dict)  # {playing: bool, position: float, timestamp: datetime}
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_activity = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    participants = relationship("RoomParticipant", back_populates="room", cascade="all, delete-orphan")


class RoomParticipant(Base):
    """Room participant model"""
    __tablename__ = "room_participants"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    room_id = Column(String(255), ForeignKey("music_rooms.room_id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(255), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True)
    joined_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_seen = Column(DateTime, default=datetime.utcnow, nullable=False)
    is_active = Column(Boolean, default=True)  # Track if user is currently connected
    
    # Relationships
    room = relationship("MusicRoom", back_populates="participants")
    user = relationship("User", back_populates="room_participants")
    
    # Unique constraint: one entry per user per room
    __table_args__ = (
        {"sqlite_autoincrement": True},
    )


# Database setup
def get_database_url():
    """
    Get database URL from environment.
    Supports PostgreSQL (for production) and SQLite (for development).
    
    Logic:
    - Local development: Uses SQLite by default
    - Deployment: Uses PostgreSQL from DATABASE_URL (set by hosting provider)
    - Can override with USE_SQLITE_LOCAL=false to force PostgreSQL locally
    
    Environment variables:
    - DATABASE_URL: Full database connection string (postgresql://user:pass@host:port/dbname)
    - USE_SQLITE_LOCAL: Set to "false" to use PostgreSQL even locally (default: auto-detect)
    - DB_HOST: PostgreSQL host (default: localhost)
    - DB_PORT: PostgreSQL port (default: 5432)
    - DB_NAME: Database name (default: aura_music)
    - DB_USER: Database user (default: postgres)
    - DB_PASSWORD: Database password (required for PostgreSQL)
    
    For PostgreSQL: postgresql://user:password@host:port/dbname
    For SQLite (fallback): sqlite:///data/aura.db
    """
    # Detect if we're in a deployment environment
    is_deployment = bool(
        os.getenv("RENDER_EXTERNAL_URL") or 
        os.getenv("VERCEL_URL") or 
        os.getenv("HEROKU_APP_NAME") or
        os.getenv("FLY_APP_NAME") or
        os.getenv("RAILWAY_ENVIRONMENT")
    )
    
    # Check if user explicitly wants to use SQLite locally
    use_sqlite_local = os.getenv("USE_SQLITE_LOCAL", "").lower()
    if use_sqlite_local == "false":
        force_postgres = True
    elif use_sqlite_local == "true":
        force_sqlite = True
    else:
        force_postgres = False
        force_sqlite = False
    
    # Check for full DATABASE_URL first (used by most hosting providers)
    db_url = os.getenv("DATABASE_URL", "").strip()
    
    if db_url:
        # Some providers use postgres:// instead of postgresql://
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        
        # If we're in deployment, always use DATABASE_URL
        if is_deployment:
            print("✓ Using PostgreSQL from DATABASE_URL (deployment environment)")
            return db_url
        
        # If DATABASE_URL points to localhost, use it
        if "localhost" in db_url or "127.0.0.1" in db_url:
            print("✓ Using PostgreSQL from DATABASE_URL (local PostgreSQL)")
            return db_url
        
        # If user explicitly wants PostgreSQL locally, use it
        if force_postgres:
            print("✓ Using PostgreSQL from DATABASE_URL (USE_SQLITE_LOCAL=false)")
            return db_url
        
        # Otherwise, DATABASE_URL is likely from a deployment config but we're running locally
        # Ignore it and use SQLite instead
        print(f"⚠ DATABASE_URL found but appears to be for deployment (host: {db_url.split('@')[1].split('/')[0] if '@' in db_url else 'unknown'})")
        print("   Using SQLite for local development instead.")
        print("   Set USE_SQLITE_LOCAL=false to use PostgreSQL locally.")
    
    # Build PostgreSQL URL from individual components (only if explicitly configured)
    db_host = os.getenv("DB_HOST", "localhost")
    db_port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME", "aura_music")
    db_user = os.getenv("DB_USER", "postgres")
    db_password = os.getenv("DB_PASSWORD")
    
    # If password is provided and we're not forcing SQLite, use PostgreSQL
    if db_password and not force_sqlite:
        # Only use if host is localhost or user explicitly wants PostgreSQL
        if db_host in ["localhost", "127.0.0.1"] or force_postgres:
            print(f"✓ Using PostgreSQL from DB_* environment variables (host: {db_host})")
            return f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
        else:
            print(f"⚠ DB_HOST is not localhost ({db_host}), using SQLite for local development")
    
    # Default to SQLite for local development
    data_dir = os.getenv("DATA_DIR", "data")
    os.makedirs(data_dir, exist_ok=True)
    sqlite_path = f"sqlite:///{os.path.join(data_dir, 'aura.db')}"
    print("✓ Using SQLite for local development")
    print(f"   Database file: {os.path.join(data_dir, 'aura.db')}")
    print("   To use PostgreSQL locally, set USE_SQLITE_LOCAL=false and configure DB_* variables")
    return sqlite_path


def create_engine_instance():
    """Create SQLAlchemy engine"""
    database_url = get_database_url()
    
    # SQLite specific settings
    if database_url.startswith("sqlite"):
        engine = create_engine(
            database_url,
            connect_args={"check_same_thread": False},  # Needed for SQLite
            echo=False  # Set to True for SQL query logging
        )
    else:
        # PostgreSQL settings
        engine = create_engine(
            database_url,
            pool_pre_ping=True,  # Verify connections before using
            pool_size=5,  # Connection pool size
            max_overflow=10,  # Max overflow connections
            echo=False  # Set to True for SQL query logging
        )
    
    return engine


def get_session_local():
    """Get database session factory"""
    engine = create_engine_instance()
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


# Create engine and session factory
engine = create_engine_instance()
SessionLocal = get_session_local()


def init_database():
    """Initialize database - create all tables"""
    Base.metadata.create_all(bind=engine)
    print("Database initialized successfully!")


def get_db():
    """Dependency for getting database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

