"""
FastAPI Application - Main Entry Point
Advanced AI Music Recommendation System API
"""

from fastapi import FastAPI, HTTPException, Query, BackgroundTasks, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import List, Optional, Dict
import uvicorn
import os
import asyncio
import threading
import httpx
from pathlib import Path

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    # Try multiple possible .env file locations
    env_paths = [
        Path(__file__).parent.parent.parent / ".env",
        Path(__file__).parent.parent.parent.parent / ".env",
        Path.cwd() / ".env",
    ]
    for env_path in env_paths:
        if env_path.exists():
            load_dotenv(env_path)
            print(f"✓ Loaded environment variables from {env_path}")
            break
    else:
        # Try default location
        load_dotenv()
except ImportError:
    print("⚠ python-dotenv not installed, skipping .env file loading")
except Exception as e:
    print(f"⚠ Error loading .env file: {e}")
from src.services.song_search_service import get_song_search_service
from src.services.recommendation_service import get_recommendation_service
from src.services.listening_history_service import get_listening_history_service
from src.services.storage_service import get_storage_service
from src.services.llm_analysis_service import get_llm_analysis_service
from src.services.rj_service import get_rj_service
from src.services.song_storage_service import get_song_storage_service
from src.services.auth_service import get_auth_service
from src.services.friend_service import get_friend_service
from src.services.room_service import get_room_service
# WebSocket import will be done at module level later
from src.database.models import init_database

app = FastAPI(
    title="AI Music Recommendation System",
    description="Advanced, production-ready music recommendation API",
    version="1.0.0"
)

# Add Content Security Policy headers to block ads
@app.middleware("http")
async def add_security_headers(request, call_next):
    """Add security headers including CSP to block ads"""
    response = await call_next(request)
    
    # Content Security Policy to block ad domains (must be single line)
    # Relaxed CSP for Render deployment - allow necessary external resources
    csp = "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval' https://www.youtube.com https://www.youtube-nocookie.com https://www.gstatic.com https://cdn.tailwindcss.com https://unpkg.com https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; frame-src 'self' https://www.youtube.com https://www.youtube-nocookie.com; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.tailwindcss.com; font-src 'self' https://fonts.gstatic.com data:; img-src 'self' data: https:; connect-src 'self' https://api.openai.com https://api.replicate.com https://api-inference.huggingface.co https://www.youtube.com https://www.youtube-nocookie.com https://itunes.apple.com https://ws.audioscrobbler.com https://cdn.socket.io https://cdnjs.cloudflare.com; media-src 'self' https://www.youtube.com https://www.youtube-nocookie.com; object-src 'none'; base-uri 'self';"
    
    response.headers["Content-Security-Policy"] = csp
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    
    return response

# Initialize database on startup
@app.on_event("startup")
async def startup_event():
    """Initialize database and services on application startup"""
    try:
        init_database()
        print("✓ Database initialized successfully")
    except Exception as e:
        print(f"⚠ Database initialization warning: {e}")
        # Don't fail startup if database already exists
    
    # Run database migrations (auto-add missing columns like username)
    try:
        from src.database.migrate import migrate as run_migration
        print("🔄 Running database migrations...")
        run_migration()
        print("✓ Database migrations completed")
    except Exception as e:
        print(f"⚠ Database migration warning: {e}")
    
    # Initialize YouTube service to verify API keys are loaded
    try:
        from src.services.youtube_service import get_youtube_service
        youtube_service = get_youtube_service()
        if youtube_service.youtube_apis:
            print(f"✓ YouTube API ready with {len(youtube_service.youtube_apis)} key(s)")
        else:
            print("⚠ YouTube API not available - will use web scraping fallback")
            if not youtube_service.api_keys:
                print("   No API keys found in environment. Check your .env file.")
    except Exception as e:
        print(f"⚠ YouTube service initialization warning: {e}")

    # Start Keep-Alive Loop (Render Support)
    asyncio.create_task(start_keep_alive_loop())

async def start_keep_alive_loop():
    """Background task to ping the server every 5 minutes to prevent idle sleep"""
    app_url = os.getenv("APP_URL", "http://localhost:8000")
    print(f"🔄 Starting Keep-Alive Loop for {app_url}...")
    
    async with httpx.AsyncClient() as client:
        while True:
            try:
                # Sleep for 5 minutes (300 seconds) - Render sleeps after 15 mins
                await asyncio.sleep(300) 
                response = await client.get(f"{app_url}/health")
                if response.status_code == 200:
                    print(f"♥ Keep-Alive Ping Successful: {response.status_code}")
                else:
                    print(f"⚠ Keep-Alive Ping Failed: {response.status_code}")
            except Exception as e:
                # Log but continue (don't crash the loop)
                print(f"⚠ Keep-Alive Ping Error: {str(e)}")
                # Shorter sleep on error to retry sooner
                await asyncio.sleep(60)

# CORS middleware for frontend integration
# Get allowed origins from environment or use defaults
allowed_origins = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:8000,http://localhost:3000,http://127.0.0.1:8000"
).split(",")

# Add Vercel deployment URL if available
vercel_url = os.getenv("VERCEL_URL")
if vercel_url:
    allowed_origins.append(f"https://{vercel_url}")

# Add Render deployment URL if available
render_url = os.getenv("RENDER_EXTERNAL_URL")
if render_url:
    allowed_origins.append(render_url)
    allowed_origins.append(render_url.replace("https://", "http://"))  # Also allow HTTP

# Add Render internal URL if available
render_internal_url = os.getenv("RENDER_INTERNAL_URL")
if render_internal_url:
    allowed_origins.append(render_internal_url)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
static_dir = os.path.join(BASE_DIR, "static")

# Ensure static directory exists (try multiple paths for different deployment scenarios)
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
else:
    # Try alternative path for deployment (Render uses different working directory)
    static_dir_alt = os.path.join(os.getcwd(), "static")
    if os.path.exists(static_dir_alt):
        static_dir = static_dir_alt
        app.mount("/static", StaticFiles(directory=static_dir), name="static")
    else:
        print(f"⚠ Warning: Static directory not found at {static_dir} or {static_dir_alt}")

# Global state for analysis status tracking
analysis_status: Dict[str, Dict] = {}

# Security
security = HTTPBearer(auto_error=False)


# Authentication dependency
async def get_current_user(
    authorization: Optional[str] = Header(None),
    token: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[str]:
    """
    Get current user from token.
    Returns user_id if authenticated, None otherwise.
    """
    auth_service = get_auth_service()
    
    # Try to get token from Authorization header or Bearer token
    token_value = None
    if token:
        token_value = token.credentials
    elif authorization:
        # Extract token from "Bearer <token>" format
        if authorization.startswith("Bearer "):
            token_value = authorization[7:]
    
    if not token_value:
        return None
    
    user_id = auth_service.verify_token(token_value)
    return user_id


def require_auth(user_id: Optional[str] = Depends(get_current_user)) -> str:
    """Require authentication - raises 401 if not authenticated"""
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user_id


# Request/Response Models
class SongInput(BaseModel):
    """Input song schema"""
    title: str
    artists: List[str]
    genre: Optional[List[str]] = None
    platform: Optional[str] = "spotify"  # spotify or youtube_music
    platform_id: Optional[str] = None
    audio_features: Optional[Dict] = None


class TasteAnalysisRequest(BaseModel):
    """Request for taste analysis"""
    user_id: str
    seed_songs: List[SongInput]
    context: Optional[Dict] = None  # time_of_day, user_context, etc.
    mood: Optional[str] = None  # User's current mood


class RecommendationRequest(BaseModel):
    """Request for recommendations"""
    user_id: str
    limit: int = 10
    context: Optional[Dict] = None
    mood: Optional[str] = None


class FeedbackRequest(BaseModel):
    """User feedback"""
    user_id: str
    recommendation_id: str
    song_id: str
    feedback_type: str  # like, skip, replay, open_in_app
    feedback_details: Optional[Dict] = None
    context: Optional[Dict] = None


class TrackListeningRequest(BaseModel):
    """Request to track a song listening"""
    user_id: str
    song_title: str
    artists: List[str]
    source: str = "unknown"
    platform: Optional[str] = None
    metadata: Optional[Dict] = None


class RegisterRequest(BaseModel):
    """User registration request"""
    email: str
    password: str
    name: Optional[str] = None
    username: Optional[str] = None


class LoginRequest(BaseModel):
    """User login request"""
    email: str
    password: str


class UsernameUpdateRequest(BaseModel):
    """Username update request"""
    username: str


class FriendRequestRequest(BaseModel):
    """Friend request"""
    receiver_username: str


class FriendActionRequest(BaseModel):
    """Friend action (accept/reject)"""
    sender_id: str


class CreateRoomRequest(BaseModel):
    """Create room request"""
    name: Optional[str] = None
    is_friends_only: bool = False


class JoinRoomRequest(BaseModel):
    """Join room request"""
    room_id: str


@app.get("/health")
async def health_check():
    """Health check endpoint for keep-alive pings"""
    return {"status": "healthy", "service": "aura-music-api"}

@app.get("/")
async def root():
    """Serve landing page"""
    try:
        static_file = os.path.join(static_dir, "landing.html")
        if os.path.exists(static_file):
            return FileResponse(static_file)
        # Fallback to index.html if landing.html doesn't exist
        static_file = os.path.join(static_dir, "index.html")
        if os.path.exists(static_file):
            return FileResponse(static_file)
    except Exception as e:
        print(f"Error serving static file: {e}")
    
    return {
        "message": "AI Music Recommendation System API",
        "version": "1.0.0",
        "docs": "/docs"
    }

@app.get("/app")
async def app_page():
    """Serve main app"""
    static_file = os.path.join(static_dir, "index.html")
    if os.path.exists(static_file):
        return FileResponse(static_file)
    return {"error": "App page not found"}

@app.get("/landing")
async def landing_page():
    """Serve landing page"""
    static_file = os.path.join(static_dir, "landing.html")
    if os.path.exists(static_file):
        return FileResponse(static_file)
    return {"error": "Landing page not found"}

@app.get("/play")
async def play():
    """Serve play page"""
    static_file = os.path.join(static_dir, "play.html")
    if os.path.exists(static_file):
        return FileResponse(static_file)
    return {"error": "Play page not found"}

@app.get("/login")
async def login_page():
    """Serve login page"""
    static_file = os.path.join(static_dir, "login.html")
    if os.path.exists(static_file):
        return FileResponse(static_file)
    return {"error": "Login page not found"}

@app.get("/register")
async def register_page():
    """Serve register page"""
    static_file = os.path.join(static_dir, "register.html")
    if os.path.exists(static_file):
        return FileResponse(static_file)
    return {"error": "Register page not found"}


@app.get("/analyze")
async def analyze_page():
    """Serve analysis page"""
    static_file = os.path.join(static_dir, "analyze.html")
    if os.path.exists(static_file):
        return FileResponse(static_file)
    return {"error": "Analysis page not found"}


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy"}


# Authentication Endpoints
@app.post("/api/v1/auth/register")
async def register(request: RegisterRequest):
    """
    Register a new user.
    
    Body:
    {
        "email": "user@example.com",
        "password": "password123",
        "name": "User Name" (optional)
    }
    """
    try:
        auth_service = get_auth_service()
        result = auth_service.register_user(
            email=request.email,
            password=request.password,
            name=request.name,
            username=request.username
        )
        return {
            "status": "success",
            "message": "User registered successfully",
            "user": {
                "user_id": result["user_id"],
                "email": result["email"],
                "name": result["name"]
            },
            "token": result["token"]
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        import logging
        logging.error(f"Registration error: {e}")
        raise HTTPException(status_code=500, detail="Registration failed")


@app.post("/api/v1/auth/login")
async def login(request: LoginRequest, background_tasks: BackgroundTasks):
    """
    Login a user.
    
    Body:
    {
        "email": "user@example.com",
        "password": "password123"
    }
    """
    try:
        auth_service = get_auth_service()
        result = auth_service.login_user(
            email=request.email,
            password=request.password
        )
        user_id = result["user_id"]
        
        # Check if user has seed songs and trigger analysis in background
        background_tasks.add_task(check_and_analyze_seed_songs, user_id)
        
        return {
            "status": "success",
            "message": "Login successful",
            "user": {
                "user_id": result["user_id"],
                "email": result["email"],
                "name": result.get("name"),
                "username": result.get("username")
            },
            "token": result["token"]
        }

    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        import logging
        logging.error(f"Login error: {e}")
        raise HTTPException(status_code=500, detail="Login failed")


@app.post("/api/v1/auth/logout")
async def logout(user_id: str = Depends(require_auth), token: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    """
    Logout a user.
    Requires authentication.
    """
    try:
        auth_service = get_auth_service()
        if token:
            auth_service.logout_user(token.credentials)
        return {
            "status": "success",
            "message": "Logged out successfully"
        }
    except Exception as e:
        import logging
        logging.error(f"Logout error: {e}")
        raise HTTPException(status_code=500, detail="Logout failed")


@app.get("/api/v1/auth/verify")
async def verify_auth(user_id: Optional[str] = Depends(get_current_user)):
    """
    Verify authentication token.
    Returns user info if authenticated.
    """
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        auth_service = get_auth_service()
        user = auth_service.get_user(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        return {
            "status": "authenticated",
            "user": {
                "user_id": user["user_id"],
                "email": user["email"],
                "username": user.get("username"),
                "name": user.get("name", ""),
                "created_at": user.get("created_at")
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.error(f"Verify error: {e}")
        raise HTTPException(status_code=500, detail="Verification failed")


# ============================================================
# Friend Management Endpoints
# ============================================================

@app.post("/api/v1/friends/request")
async def send_friend_request(request: FriendRequestRequest, user_id: str = Depends(require_auth)):
    """
    Send a friend request to another user by username.
    Requires authentication.
    """
    try:
        friend_service = get_friend_service()
        result = friend_service.send_friend_request(user_id, request.receiver_username)
        return {
            "status": "success",
            **result
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        import logging
        logging.error(f"Send friend request error: {e}")
        raise HTTPException(status_code=500, detail="Failed to send friend request")


@app.post("/api/v1/friends/accept")
async def accept_friend_request(request: FriendActionRequest, user_id: str = Depends(require_auth)):
    """
    Accept a pending friend request.
    Requires authentication.
    """
    try:
        friend_service = get_friend_service()
        result = friend_service.accept_friend_request(user_id, request.sender_id)
        return {
            "status": "success",
            **result
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        import logging
        logging.error(f"Accept friend request error: {e}")
        raise HTTPException(status_code=500, detail="Failed to accept friend request")


@app.post("/api/v1/friends/reject")
async def reject_friend_request(request: FriendActionRequest, user_id: str = Depends(require_auth)):
    """
    Reject a pending friend request.
    Requires authentication.
    """
    try:
        friend_service = get_friend_service()
        result = friend_service.reject_friend_request(user_id, request.sender_id)
        return {
            "status": "success",
            **result
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        import logging
        logging.error(f"Reject friend request error: {e}")
        raise HTTPException(status_code=500, detail="Failed to reject friend request")


@app.get("/api/v1/friends/requests")
async def get_friend_requests(
    type: str = Query("received", description="Type of requests: 'sent' or 'received'"),
    user_id: str = Depends(require_auth)
):
    """
    Get pending friend requests.
    Requires authentication.
    
    Args:
        type: 'sent' for outgoing requests, 'received' for incoming requests
    """
    try:
        friend_service = get_friend_service()
        requests = friend_service.get_friend_requests(user_id, type)
        return {
            "status": "success",
            "type": type,
            "requests": requests,
            "count": len(requests)
        }
    except Exception as e:
        import logging
        logging.error(f"Get friend requests error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get friend requests")


@app.get("/api/v1/friends")
async def get_friends(user_id: str = Depends(require_auth)):
    """
    Get list of friends.
    Requires authentication.
    """
    try:
        friend_service = get_friend_service()
        friends = friend_service.get_friends(user_id)
        return {
            "status": "success",
            "friends": friends,
            "count": len(friends)
        }
    except Exception as e:
        import logging
        logging.error(f"Get friends error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get friends")


@app.delete("/api/v1/friends/{friend_id}")
async def remove_friend(friend_id: str, user_id: str = Depends(require_auth)):
    """
    Remove a friend.
    Requires authentication.
    """
    try:
        friend_service = get_friend_service()
        result = friend_service.remove_friend(user_id, friend_id)
        return {
            "status": "success",
            **result
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        import logging
        logging.error(f"Remove friend error: {e}")
        raise HTTPException(status_code=500, detail="Failed to remove friend")


@app.post("/api/v1/friends/search")
async def search_users(
    q: str = Query(..., description="Username to search for"),
    limit: int = Query(20, ge=1, le=50, description="Maximum results"),
    user_id: str = Depends(require_auth)
):
    """
    Search for users by username.
    Requires authentication.
    """
    try:
        friend_service = get_friend_service()
        users = friend_service.search_user_by_username(q, limit)
        # Filter out the current user from results
        users = [u for u in users if u["user_id"] != user_id]
        return {
            "status": "success",
            "query": q,
            "users": users,
            "count": len(users)
        }
    except Exception as e:
        import logging
        logging.error(f"Search users error: {e}")
        raise HTTPException(status_code=500, detail="Failed to search users")


# ============================================================
# Room Management Endpoints
# ============================================================

@app.post("/api/v1/rooms/create")
async def create_room(request: CreateRoomRequest, user_id: str = Depends(require_auth)):
    """
    Create a new music room.
    Requires authentication.
    """
    try:
        room_service = get_room_service()
        result = room_service.create_room(
            host_id=user_id,
            name=request.name,
            is_friends_only=request.is_friends_only
        )
        return {
            "status": "success",
            **result
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        import logging
        logging.error(f"Create room error: {e}")
        raise HTTPException(status_code=500, detail="Failed to create room")


@app.post("/api/v1/rooms/join")
async def join_room(request: JoinRoomRequest, user_id: str = Depends(require_auth)):
    """
    Join an existing music room.
    Requires authentication.
    """
    try:
        room_service = get_room_service()
        result = room_service.join_room(request.room_id, user_id)
        return {
            "status": "success",
            **result
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        import logging
        logging.error(f"Join room error: {e}")
        raise HTTPException(status_code=500, detail="Failed to join room")


@app.post("/api/v1/rooms/{room_id}/leave")
async def leave_room(room_id: str, user_id: str = Depends(require_auth)):
    """
    Leave a music room.
    Requires authentication.
    """
    try:
        room_service = get_room_service()
        result = room_service.leave_room(room_id, user_id)
        return {
            "status": "success",
            **result
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        import logging
        logging.error(f"Leave room error: {e}")
        raise HTTPException(status_code=500, detail="Failed to leave room")


@app.get("/api/v1/rooms/{room_id}")
async def get_room_state(room_id: str, user_id: str = Depends(require_auth)):
    """
    Get current room state.
    Requires authentication.
    """
    try:
        room_service = get_room_service()
        result = room_service.get_room_state(room_id)
        if not result:
            raise HTTPException(status_code=404, detail="Room not found")
        return {
            "status": "success",
            **result
        }
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.error(f"Get room error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get room")


@app.get("/api/v1/rooms")
async def get_user_rooms(user_id: str = Depends(require_auth)):
    """
    Get all rooms the user is currently in.
    Requires authentication.
    """
    try:
        room_service = get_room_service()
        rooms = room_service.get_user_rooms(user_id)
        return {
            "status": "success",
            "rooms": rooms,
            "count": len(rooms)
        }
    except Exception as e:
        import logging
        logging.error(f"Get user rooms error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get rooms")

@app.get("/api/v1/songs/search")
async def search_songs(
    q: str = Query(..., description="Search query"),
    limit: int = Query(20, ge=1, le=50, description="Maximum number of results")
):
    """
    Search for songs with metadata and images.
    
    Args:
        q: Search query (song title, artist, etc.)
        limit: Maximum number of results (1-50)
    """
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        # Trim and validate query
        query = q.strip()
        if not query or len(query) < 1:
            return {
                "query": q,
                "results": [],
                "count": 0,
                "error": "Query too short"
            }
        
        logger.info(f"Search request: query='{query}', limit={limit}")
        
        search_service = get_song_search_service()
        results = search_service.search_songs(query, limit)
        
        logger.info(f"Search completed: {len(results)} results for '{query}'")
        
        return {
            "query": query,
            "results": results,
            "songs": results, # For compatibility with play.html
            "count": len(results)
        }
    except Exception as e:
        # Log error for debugging with full traceback
        import traceback
        logger.error(f"Search error for query '{q}': {e}")
        logger.error(traceback.format_exc())
        
        # Return empty results instead of error for better UX
        return {
            "query": q,
            "results": [],
            "count": 0,
            "error": f"Search failed: {str(e)}"
        }


def check_and_analyze_seed_songs(user_id: str):
    """
    Check if user has seed songs and automatically trigger analysis.
    This is called in the background after user login.
    Also loads existing taste profile from database.
    """
    try:
        import logging
        logger = logging.getLogger(__name__)
        
        recommendation_service = get_recommendation_service()
        song_storage = get_song_storage_service()
        history_service = get_listening_history_service()
        
        # Load existing taste profile from database
        existing_profile = recommendation_service.get_taste_profile(user_id)
        if existing_profile:
            logger.info(f"Loaded existing taste profile for user {user_id} with {existing_profile.get('song_count', 0)} songs")
        
        # Get user's seed songs
        user_songs_data = song_storage.get_user_songs(user_id)
        seed_songs = user_songs_data.get("seed_songs", [])
        
        # Only analyze if user has at least 5 seed songs and no existing profile
        if len(seed_songs) >= 5 and not existing_profile:
            logger.info(f"User {user_id} has {len(seed_songs)} seed songs but no profile. Triggering automatic analysis.")
            
            # Get all songs for analysis (seed songs + listening history)
            all_songs = song_storage.get_songs_for_analysis(user_id)
            
            # Get listening history songs
            history_songs = history_service.get_songs_for_analysis(
                user_id=user_id,
                min_plays=2,
                days=30
            )
            
            # Run analysis in background (without mood, use default)
            run_analysis_background(user_id, all_songs, history_songs, mood=None)
            
            logger.info(f"Automatic analysis started for user {user_id} with {len(all_songs)} songs.")
        elif existing_profile:
            logger.info(f"User {user_id} already has a taste profile. Skipping automatic analysis.")
        else:
            logger.info(f"User {user_id} has {len(seed_songs)} seed songs. Skipping automatic analysis (need at least 5).")
    except Exception as e:
        import logging
        logging.error(f"Error checking/analyzing seed songs for user {user_id}: {e}")


def run_analysis_background(user_id: str, all_songs: List[Dict], history_songs: List[Dict], mood: Optional[str] = None):
    """Run taste analysis in background thread using songs from JSON storage"""
    try:
        # Update status
        analysis_status[user_id] = {"status": "processing", "progress": 0, "result": None, "mood": mood}
        
        recommendation_service = get_recommendation_service()
        
        # Update progress
        analysis_status[user_id]["progress"] = 30
        
        # Analyze taste using songs from JSON storage
        profile = recommendation_service.analyze_taste(user_id, all_songs)
        analysis_status[user_id]["progress"] = 70
        
        # Get recommendations
        recommendations = recommendation_service.get_recommendations(
            user_id=user_id,
            limit=10,
            context=None
        )
        analysis_status[user_id]["progress"] = 90
        
        # Complete
        analysis_status[user_id] = {
            "status": "complete",
            "progress": 100,
            "result": {
                "profile": {
                    "global_taste": {
                        "song_count": profile["song_count"],
                        "seed_songs": len(all_songs),
                        "history_songs": len(history_songs),
                        "familiarity_preference": 0.5
                    },
                    "mood_profiles": {}
                },
                "recommendations": recommendations
            }
        }
    except Exception as e:
        import logging
        logging.error(f"Background analysis error: {e}")
        analysis_status[user_id] = {
            "status": "error",
            "progress": 0,
            "result": None,
            "error": str(e)
        }


@app.post("/api/v1/taste/analyze")
async def analyze_taste(request: TasteAnalysisRequest, background_tasks: BackgroundTasks):
    """
    Start taste analysis in background using songs from JSON storage.
    
    Use GET /api/v1/taste/analyze/status to check progress.
    """
    try:
        recommendation_service = get_recommendation_service()
        history_service = get_listening_history_service()
        song_storage = get_song_storage_service()
        
        # Save seed songs to JSON storage
        seed_songs = []
        for song in request.seed_songs:
            song_dict = {
                "title": song.title,
                "artists": song.artists,
                "genre": song.genre or [],
                "album": getattr(song, 'album', None) or "",
                "image": getattr(song, 'image', None) or ""
            }
            # Save to storage
            song_storage.add_song(song_dict, user_id=request.user_id)
            seed_songs.append({
                "title": song.title,
                "artists": song.artists,
                "genre": song.genre or []
            })
        
        # Get songs from JSON storage (includes saved seed songs)
        stored_songs = song_storage.get_songs_for_analysis(request.user_id)
        
        # Get listening history songs
        history_songs = history_service.get_songs_for_analysis(
            user_id=request.user_id,
            min_plays=2,
            days=30
        )
        
        # Combine stored songs with history
        all_songs = stored_songs.copy()
        seen = set()
        for song in stored_songs:
            key = (song["title"].lower(), "|".join([a.lower() for a in song.get("artists", [])]))
            seen.add(key)
        
        for hist_song in history_songs:
            key = (hist_song["title"].lower(), "|".join([a.lower() for a in hist_song["artists"]]))
            if key not in seen:
                all_songs.append({
                    "title": hist_song["title"],
                    "artists": hist_song["artists"],
                    "genre": hist_song.get("genre", [])
                })
                seen.add(key)
        
        # Initialize status
        analysis_status[request.user_id] = {"status": "processing", "progress": 0, "result": None, "mood": request.mood}
        
        # Run analysis in background with all songs and mood
        background_tasks.add_task(run_analysis_background, request.user_id, all_songs, [], request.mood)
        
        return {
            "user_id": request.user_id,
            "status": "processing",
            "message": f"Analysis started in background with {len(all_songs)} songs. Use /api/v1/taste/analyze/status to check progress.",
            "songs_count": len(all_songs)
        }
    except Exception as e:
        import logging
        logging.error(f"Taste analysis error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/taste/analyze/status")
async def get_analysis_status(user_id: str):
    """Get current analysis status and results"""
    if user_id not in analysis_status:
        return {
            "user_id": user_id,
            "status": "not_started",
            "progress": 0,
            "result": None
        }
    
    return {
        "user_id": user_id,
        **analysis_status[user_id]
    }


@app.get("/api/v1/recommendations")
async def get_recommendations(
    user_id: str,
    limit: int = 10,
    context: Optional[str] = None,
    genre: Optional[str] = None
):
    """
    Get music recommendations for a user based on taste profile.
    
    Args:
        user_id: User identifier
        limit: Number of recommendations
        context: JSON string with context (time_of_day, user_context, etc.)
        genre: Optional genre filter
    """
    try:
        recommendation_service = get_recommendation_service()
        
        # Check if user has a profile
        if user_id not in recommendation_service.user_profiles:
            # Check if analysis is in progress or completed
            if user_id in analysis_status:
                status = analysis_status[user_id]
                if status.get("status") == "complete" and status.get("result") and status["result"].get("recommendations"):
                    # Return recommendations from analysis result
                    return {
                        "user_id": user_id,
                        "recommendations": status["result"]["recommendations"],
                        "count": len(status["result"]["recommendations"]),
                        "source": "analysis_result"
                    }
                elif status.get("status") == "processing":
                    # Analysis still in progress
                    return {
                        "user_id": user_id,
                        "recommendations": [],
                        "count": 0,
                        "status": "processing",
                        "message": "Analysis in progress. Please wait."
                    }
            
            # No profile and no analysis - return empty
            return {
                "user_id": user_id,
                "recommendations": [],
                "count": 0,
                "message": "No taste profile found. Please analyze your taste first."
            }
        
        # Parse context if provided
        context_dict = None
        if context:
            try:
                import json
                context_dict = json.loads(context)
            except:
                pass
        
        # Parse genre if provided (can be comma-separated)
        genre_list = None
        if genre:
            genre_list = [g.strip() for g in genre.split(',') if g.strip()]
        
        # Get recommendations
        recommendations = recommendation_service.get_recommendations(
            user_id=user_id,
            limit=limit,
            context=context_dict,
            genre=genre_list
        )
        
        import logging
        logging.info(f"Generated {len(recommendations)} recommendations for user {user_id}")
        
        return {
            "user_id": user_id,
            "recommendations": recommendations,
            "count": len(recommendations)
        }
    except Exception as e:
        import logging
        import traceback
        logging.error(f"Recommendations error: {e}")
        logging.error(traceback.format_exc())
        return {
            "user_id": user_id,
            "recommendations": [],
            "count": 0,
            "error": str(e)
        }


@app.post("/api/v1/feedback")
async def submit_feedback(request: FeedbackRequest):
    """
    Submit user feedback to improve recommendations.
    
    Updates taste vectors based on feedback signals.
    Tracks listening history when users open songs.
    """
    try:
        history_service = get_listening_history_service()
        
        # Track song if user opened it in an app
        if request.feedback_type == "open_in_app":
            # Extract song info from recommendation_id or song_id
            # For now, we'll need to get song info from the recommendation
            # This is a simplified version - in production, you'd look up the song
            history_service.track_song(
                user_id=request.user_id,
                song_title=request.song_id,  # This should be the song title
                artists=[],  # Would need to be passed or looked up
                source="recommendation",
                platform=request.feedback_details.get("platform") if request.feedback_details else None
            )
        
        return {
            "user_id": request.user_id,
            "status": "feedback_received",
            "message": "Feedback recorded"
        }
    except Exception as e:
        import logging
        logging.error(f"Feedback error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class SongForProfile(BaseModel):
    """Song model for profile updates"""
    title: str
    artists: List[str]
    genre: Optional[List[str]] = []


class TasteUpdateRequest(BaseModel):
    """Request model for updating taste profile"""
    user_id: str
    songs: List[SongForProfile]
    weight: Optional[float] = 0.3


@app.post("/api/v1/taste/update")
async def update_taste_profile(request: TasteUpdateRequest):
    """
    Update user's taste profile by adding new songs.
    
    Body:
    {
        "user_id": "user_123",
        "songs": [
            {"title": "Song Title", "artists": ["Artist"], "genre": ["Genre"]}
        ],
        "weight": 0.3  # Optional, default 0.3
    }
    """
    try:
        recommendation_service = get_recommendation_service()
        
        # Convert Pydantic models to dicts
        songs_dict = [
            {
                "title": song.title,
                "artists": song.artists,
                "genre": song.genre or []
            }
            for song in request.songs
        ]
        
        updated_profile = recommendation_service.update_profile_with_songs(
            request.user_id, songs_dict, request.weight
        )
        
        if updated_profile:
            return {
                "status": "success",
                "message": f"Profile updated with {len(request.songs)} new songs",
                "profile": updated_profile
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to update profile")
    except Exception as e:
        import logging
        logging.error(f"Error updating taste profile: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/taste/profile")
async def get_taste_profile(user_id: str):
    """
    Get current user taste profile.
    
    Returns global taste and mood-specific profiles.
    """
    try:
        recommendation_service = get_recommendation_service()
        profile = recommendation_service.get_taste_profile(user_id)
        
        if profile:
            return {
                "user_id": user_id,
                "profile": {
                    "global_taste": {
                        "song_count": profile.get("song_count", 0),
                        "familiarity_preference": 0.5
                    },
                    "mood_profiles": {}
                }
            }
        else:
            return {
                "user_id": user_id,
                "profile": None,
                "message": "No profile found. Analyze your taste first."
            }
    except Exception as e:
        import logging
        logging.error(f"Profile retrieval error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/listening/history")
async def get_listening_history(
    user_id: str,
    limit: Optional[int] = None,
    days: Optional[int] = None
):
    """
    Get user's listening history.
    
    Args:
        user_id: User identifier
        limit: Maximum number of entries
        days: Only return entries from last N days
    """
    try:
        history_service = get_listening_history_service()
        history = history_service.get_user_history(user_id, limit=limit, days=days)
        
        return {
            "user_id": user_id,
            "history": history,
            "count": len(history)
        }
    except Exception as e:
        import logging
        logging.error(f"History retrieval error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/listening/stats")
async def get_listening_stats(user_id: str, days: Optional[int] = 30):
    """
    Get listening statistics for a user.
    
    Args:
        user_id: User identifier
        days: Number of days to analyze (default: 30)
    """
    try:
        history_service = get_listening_history_service()
        stats = history_service.get_listening_stats(user_id, days=days)
        
        return {
            "user_id": user_id,
            "stats": stats
        }
    except Exception as e:
        import logging
        logging.error(f"Stats retrieval error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/listening/track")
async def track_listening(request: TrackListeningRequest):
    """
    Track a song that a user listened to.
    
    Body:
    {
        "user_id": "user_123",
        "song_title": "Song Name",
        "artists": ["Artist 1", "Artist 2"],
        "source": "recommendation",
        "platform": "spotify",
        "metadata": {}
    }
    """
    try:
        history_service = get_listening_history_service()
        
        history_service.track_song(
            user_id=request.user_id,
            song_title=request.song_title,
            artists=request.artists,
            source=request.source,
            platform=request.platform,
            metadata=request.metadata or {}
        )
        
        return {
            "status": "tracked",
            "message": "Song listening tracked"
        }
    except Exception as e:
        import logging
        logging.error(f"Tracking error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class ChatMessageRequest(BaseModel):
    """Request for chat message"""
    user_id: str
    message: str


@app.get("/chat")
async def chat_page():
    """Serve chat page"""
    static_file = os.path.join(static_dir, "chat.html")
    if os.path.exists(static_file):
        return FileResponse(static_file)
    return {"error": "Chat page not found"}


@app.post("/api/v1/chat/message")
async def chat_message(request: ChatMessageRequest):
    """
    Process chat message with RJ (Radio Jockey) using Llama model.
    RJ analyzes mood, engages in conversation, and suggests songs after rapport-building.
    
    Rate limited: 20 requests/minute, 200 requests/hour per user.
    """
    try:
        rj_service = get_rj_service()
        
        # Use the new chat() method with integrated mood analysis and rate limiting
        result = rj_service.chat(request.message, request.user_id)
        
        # Check if rate limited
        if result.get("rate_limited"):
            return {
                "response": result["response"],
                "detected_mood": None,
                "confidence": 0,
                "recommended_songs": [],
                "rate_limited": True,
                "error": "Rate limit exceeded"
            }
        
        # Format recommended songs
        formatted_songs = []
        for song in result.get("songs", []):
            formatted_songs.append({
                "title": song.get("title") or song.get("song", {}).get("title", ""),
                "artists": song.get("artists") or song.get("song", {}).get("artists", []),
                "image": song.get("image") or song.get("song", {}).get("image", ""),
                "album": song.get("album") or song.get("song", {}).get("album", ""),
                "genre": song.get("genre") or song.get("song", {}).get("genre", []),
                "youtube_video_id": song.get("youtube_video_id") or song.get("song", {}).get("youtube_video_id")
            })
        
        return {
            "response": result["response"],
            "detected_mood": result.get("mood"),
            "confidence": result.get("mood_confidence", 0.8),
            "recommended_songs": formatted_songs,
            "conversation_turn": result.get("conversation_turn", 0),
            "personalized": len(formatted_songs) > 0,
            "rate_limited": False
        }
        
    except Exception as e:
        import logging
        import traceback
        logging.error(f"Chat error: {e}")
        logging.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/chat/history")
async def get_chat_history(user_id: str, limit: int = 20):
    """Get chat conversation history"""
    try:
        chatbot_service = get_chatbot_service()
        history = chatbot_service.get_conversation_history(user_id, limit=limit)
        return {
            "user_id": user_id,
            "history": history,
            "count": len(history)
        }
    except Exception as e:
        import logging
        logging.error(f"Chat history error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Song Storage Endpoints
@app.post("/api/v1/songs/store")
async def store_song(song: Dict, user_id: Optional[str] = None):
    """Store a song and update taste profile if user_id provided"""
    try:
        song_storage = get_song_storage_service()
        song_storage.add_song(song, user_id=user_id)
        
        # Update taste profile if user_id is provided
        if user_id:
            try:
                recommendation_service = get_recommendation_service()
                
                # Format song for profile update
                song_for_profile = {
                    "title": song.get("title", ""),
                    "artists": song.get("artists", []),
                    "genre": song.get("genre", [])
                }
                
                # Check if user has existing profile
                existing_profile = recommendation_service.get_taste_profile(user_id)
                
                if existing_profile:
                    # Update existing profile with new song (weight: 0.2 = 20% new, 80% existing)
                    recommendation_service.update_profile_with_songs(
                        user_id, 
                        [song_for_profile], 
                        weight=0.2
                    )
                else:
                    # If no profile exists, check if user has enough songs to create one
                    user_songs_data = song_storage.get_user_songs(user_id)
                    seed_songs = user_songs_data.get("seed_songs", [])
                    
                    if len(seed_songs) >= 5:
                        # Create new profile from all user songs
                        songs_for_analysis = [
                            {
                                "title": s.get("title", ""),
                                "artists": s.get("artists", []),
                                "genre": s.get("genre", [])
                            }
                            for s in seed_songs
                        ]
                        recommendation_service.analyze_taste(user_id, songs_for_analysis)
            except Exception as profile_error:
                import logging
                logging.warning(f"Could not update taste profile: {profile_error}")
                # Don't fail the song storage if profile update fails
        
        return {"status": "success", "message": "Song stored successfully"}
    except Exception as e:
        import logging
        logging.error(f"Error storing song: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/songs/user/{user_id}")
async def get_user_stored_songs(user_id: str):
    """Get all songs stored for a user"""
    try:
        song_storage = get_song_storage_service()
        user_songs = song_storage.get_user_songs(user_id)
        return {
            "user_id": user_id,
            "songs": user_songs
        }
    except Exception as e:
        import logging
        logging.error(f"Error getting user songs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/songs/storage/search")
async def search_stored_songs(q: str = Query(..., description="Search query"), limit: int = 20):
    """Search songs in JSON storage"""
    try:
        song_storage = get_song_storage_service()
        results = song_storage.search_songs(q, limit=limit)
        return {
            "query": q,
            "results": results,
            "count": len(results)
        }
    except Exception as e:
        import logging
        logging.error(f"Error searching songs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/songs/youtube-video-id")
async def get_youtube_video_id(
    title: str = Query(..., description="Song title"),
    artists: str = Query(..., description="Comma-separated artist names")
):
    """
    Get YouTube video ID for a song.
    Uses metadata normalization for better search results.
    
    Args:
        title: Song title
        artists: Comma-separated list of artist names
    """
    import logging
    import traceback
    logger = logging.getLogger(__name__)
    
    try:
        from src.services.youtube_service import get_youtube_service
        youtube_service = get_youtube_service()
        
        artist_list = [a.strip() for a in artists.split(',') if a.strip()]
        logger.info(f"Searching YouTube for: '{title}' by {artist_list}")
        
        if not title or not title.strip():
            logger.warning("Empty title provided for YouTube search")
            return {
                "title": title,
                "artists": artist_list,
                "youtube_video_id": None,
                "error": "Title is required"
            }
        
        # Normalize metadata for better search
        normalized = youtube_service.normalize_metadata(title, artist_list)
        logger.debug(f"Normalized: '{normalized['normalized_title']}' by {normalized['normalized_artists']}")
        
        video_id = youtube_service.search_video_id(title, artist_list)
        
        if video_id:
            # Validate the video ID before returning
            if len(video_id) == 11 and all(c.isalnum() or c in '-_' for c in video_id):
                logger.info(f"Found valid video ID: {video_id} for '{title}'")
                return {
                    "title": title,
                    "artists": artist_list,
                    "youtube_video_id": video_id,
                    "embed_url": youtube_service.get_embed_url(video_id),
                    "watch_url": youtube_service.get_watch_url(video_id)
                }
            else:
                logger.warning(f"Invalid video ID format: {video_id} for '{title}'")
                return {
                    "title": title,
                    "artists": artist_list,
                    "youtube_video_id": None,
                    "error": f"Invalid video ID format: {video_id}"
                }
        else:
            logger.warning(f"No video ID found for: '{title}' by {artist_list}")
            return {
                "title": title,
                "artists": artist_list,
                "youtube_video_id": None,
                "error": "Video not found. Please check the song title and artist name."
            }
    except Exception as e:
        logger.error(f"Error getting YouTube video ID for '{title}': {e}")
        logger.error(traceback.format_exc())
        return {
            "title": title,
            "artists": [a.strip() for a in artists.split(',') if a.strip()] if artists else [],
            "youtube_video_id": None,
            "error": f"Search failed: {str(e)}"
        }


# Friend Management Endpoints
@app.post("/api/v1/friends/search")
async def search_users(
    q: str = Query(..., description="Username search query"),
    limit: int = Query(20, ge=1, le=50),
    user_id: str = Depends(require_auth)
):
    """Search users by username"""
    try:
        friend_service = get_friend_service()
        results = friend_service.search_user_by_username(q, limit)
        return {
            "query": q,
            "results": results,
            "count": len(results)
        }
    except Exception as e:
        import logging
        logging.error(f"User search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/friends/request")
async def send_friend_request(
    request: FriendRequestRequest,
    user_id: str = Depends(require_auth)
):
    """Send a friend request"""
    try:
        friend_service = get_friend_service()
        result = friend_service.send_friend_request(user_id, request.receiver_username)
        return {
            "status": "success",
            **result
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        import logging
        logging.error(f"Friend request error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/friends/accept")
async def accept_friend_request(
    request: FriendActionRequest,
    user_id: str = Depends(require_auth)
):
    """Accept a friend request"""
    try:
        friend_service = get_friend_service()
        result = friend_service.accept_friend_request(user_id, request.sender_id)
        return {
            "status": "success",
            **result
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        import logging
        logging.error(f"Accept friend request error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/friends/reject")
async def reject_friend_request(
    request: FriendActionRequest,
    user_id: str = Depends(require_auth)
):
    """Reject a friend request"""
    try:
        friend_service = get_friend_service()
        result = friend_service.reject_friend_request(user_id, request.sender_id)
        return {
            "status": "success",
            **result
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        import logging
        logging.error(f"Reject friend request error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/friends/requests")
async def get_friend_requests(
    type: str = Query("received", description="Type: 'sent' or 'received'"),
    user_id: str = Depends(require_auth)
):
    """Get friend requests (sent or received)"""
    try:
        friend_service = get_friend_service()
        requests = friend_service.get_friend_requests(user_id, type)
        return {
            "type": type,
            "requests": requests,
            "count": len(requests)
        }
    except Exception as e:
        import logging
        logging.error(f"Get friend requests error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/friends")
async def get_friends(user_id: str = Depends(require_auth)):
    """Get all friends"""
    try:
        friend_service = get_friend_service()
        friends = friend_service.get_friends(user_id)
        return {
            "friends": friends,
            "count": len(friends)
        }
    except Exception as e:
        import logging
        logging.error(f"Get friends error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/v1/friends/{friend_id}")
async def remove_friend(friend_id: str, user_id: str = Depends(require_auth)):
    """Remove a friend"""
    try:
        friend_service = get_friend_service()
        result = friend_service.remove_friend(user_id, friend_id)
        return {
            "status": "success",
            **result
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        import logging
        logging.error(f"Remove friend error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/auth/username")
async def update_username(
    request: UsernameUpdateRequest,
    user_id: str = Depends(require_auth)
):
    """Update username"""
    try:
        auth_service = get_auth_service()
        result = auth_service.update_username(user_id, request.username)
        return {
            "status": "success",
            "user": result
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        import logging
        logging.error(f"Update username error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Room Management Endpoints
@app.post("/api/v1/rooms/create")
async def create_room(
    request: CreateRoomRequest,
    user_id: str = Depends(require_auth)
):
    """Create a music room"""
    try:
        room_service = get_room_service()
        room = room_service.create_room(
            host_id=user_id,
            name=request.name,
            is_friends_only=request.is_friends_only
        )
        return {
            "status": "success",
            **room
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        import logging
        logging.error(f"Create room error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/rooms/join")
async def join_room(
    request: JoinRoomRequest,
    user_id: str = Depends(require_auth)
):
    """Join a music room"""
    try:
        room_service = get_room_service()
        room_state = room_service.join_room(request.room_id, user_id)
        return {
            "status": "success",
            **room_state
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        import logging
        logging.error(f"Join room error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/rooms/{room_id}/leave")
async def leave_room(room_id: str, user_id: str = Depends(require_auth)):
    """Leave a music room"""
    try:
        room_service = get_room_service()
        result = room_service.leave_room(room_id, user_id)
        return {
            "status": "success",
            **result
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        import logging
        logging.error(f"Leave room error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/rooms/{room_id}")
async def get_room(room_id: str, user_id: str = Depends(require_auth)):
    """Get room state"""
    try:
        room_service = get_room_service()
        room_state = room_service.get_room_state(room_id)
        if not room_state:
            raise HTTPException(status_code=404, detail="Room not found")
        return {
            "status": "success",
            **room_state
        }
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.error(f"Get room error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/rooms")
async def get_user_rooms(user_id: str = Depends(require_auth)):
    """Get all rooms user is in"""
    try:
        room_service = get_room_service()
        rooms = room_service.get_user_rooms(user_id)
        return {
            "rooms": rooms,
            "count": len(rooms)
        }
    except Exception as e:
        import logging
        logging.error(f"Get user rooms error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Import for WebSocket support (will be loaded later)
has_socketio = False
sio = None


# Create Socket.IO ASGI app wrapper
try:
    import socketio
    from src.services.websocket_service import sio
    socketio_asgi = socketio.ASGIApp(sio, app)
    has_socketio = True
    print("✓ Socket.IO WebSocket support enabled")
except ImportError as e:
    socketio_asgi = app
    print(f"⚠ Socket.IO not available - WebSocket features disabled: {e}")
except Exception as e:
    socketio_asgi = app
    print(f"⚠ Socket.IO initialization error - WebSocket features disabled: {e}")

# Export socketio_asgi for uvicorn (used in Dockerfile)
__all__ = ['app', 'socketio_asgi']


if __name__ == "__main__":
    uvicorn.run(
        socketio_asgi if 'socketio_asgi' in globals() else app,
        host="0.0.0.0",
        port=8000,
        reload=True
    )

