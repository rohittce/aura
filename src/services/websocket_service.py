"""
WebSocket Service
Handles Socket.IO connections, authentication, and real-time events
"""

import socketio
from typing import Dict, Optional, Set
import logging
from datetime import datetime
import json

from src.services.auth_service import get_auth_service
from src.services.room_service import get_room_service

logger = logging.getLogger(__name__)

# Create Socket.IO server
sio = socketio.AsyncServer(
    cors_allowed_origins="*",  # Configure in production
    async_mode='asgi',
    logger=True,
    engineio_logger=True
)

# Track connected users and their rooms
connected_users: Dict[str, Dict] = {}  # {user_id: {socket_id, room_id, last_ping}}
user_socket_map: Dict[str, str] = {}  # {socket_id: user_id}
room_users: Dict[str, Set[str]] = {}  # {room_id: {user_id, ...}}


@sio.event
async def connect(sid, environ, auth):
    """
    Handle client connection.
    Expects JWT token in auth['token'] or query parameter.
    """
    try:
        # Get token from auth dict or query string
        token = None
        if auth and isinstance(auth, dict):
            token = auth.get('token')
        
        if not token:
            # Try query parameter
            query_string = environ.get('QUERY_STRING', '')
            if query_string:
                params = dict(param.split('=') for param in query_string.split('&') if '=' in param)
                token = params.get('token')
        
        if not token:
            logger.warning(f"Connection rejected: No token provided for {sid}")
            return False
        
        # Verify token
        auth_service = get_auth_service()
        user_id = auth_service.verify_token(token)
        
        if not user_id:
            logger.warning(f"Connection rejected: Invalid token for {sid}")
            return False
        
        # Store connection info
        connected_users[user_id] = {
            "socket_id": sid,
            "room_id": None,
            "last_ping": datetime.utcnow(),
            "connected_at": datetime.utcnow()
        }
        user_socket_map[sid] = user_id
        
        logger.info(f"User {user_id} connected (socket: {sid})")
        
        # Send connection confirmation
        await sio.emit('connected', {
            "user_id": user_id,
            "timestamp": datetime.utcnow().isoformat()
        }, room=sid)
        
        return True
    except Exception as e:
        logger.error(f"Error in connect: {e}")
        return False


@sio.event
async def disconnect(sid):
    """Handle client disconnection"""
    try:
        user_id = user_socket_map.get(sid)
        if not user_id:
            return
        
        # Get room info
        user_info = connected_users.get(user_id, {})
        room_id = user_info.get("room_id")
        
        # Remove from room
        if room_id:
            room_users[room_id] = room_users.get(room_id, set()) - {user_id}
            
            # Leave room in database
            room_service = get_room_service()
            try:
                room_service.leave_room(room_id, user_id)
            except:
                pass
            
            # Notify other users in room
            await sio.emit('user_left', {
                "user_id": user_id,
                "timestamp": datetime.utcnow().isoformat()
            }, room=room_id)
            
            # Broadcast updated participant list
            await broadcast_participant_list(room_id)
        
        # Clean up
        del connected_users[user_id]
        del user_socket_map[sid]
        
        logger.info(f"User {user_id} disconnected (socket: {sid})")
    except Exception as e:
        logger.error(f"Error in disconnect: {e}")


@sio.event
async def join_room(sid, data):
    """
    Join a music room.
    
    Expected payload:
    {
        "room_id": "room_xxx",
        "token": "jwt_token"  # Optional, if not authenticated in connect
    }
    """
    try:
        user_id = user_socket_map.get(sid)
        if not user_id:
            await sio.emit('error', {
                "message": "Not authenticated",
                "code": "AUTH_REQUIRED"
            }, room=sid)
            return
        
        room_id = data.get('room_id')
        if not room_id:
            await sio.emit('error', {
                "message": "room_id required",
                "code": "INVALID_REQUEST"
            }, room=sid)
            return
        
        room_id = room_id.upper()
        
        # Join room in database
        room_service = get_room_service()
        try:
            room_state = room_service.join_room(room_id, user_id)
        except ValueError as e:
            await sio.emit('error', {
                "message": str(e),
                "code": "JOIN_FAILED"
            }, room=sid)
            return
        
        # Update tracking
        connected_users[user_id]["room_id"] = room_id
        if room_id not in room_users:
            room_users[room_id] = set()
        room_users[room_id].add(user_id)
        
        # Join Socket.IO room
        await sio.enter_room(sid, room_id)
        
        # Get current room state
        current_state = room_service.get_room_state(room_id)
        
        # Send confirmation to user
        await sio.emit('room_joined', {
            "room_id": room_id,
            "room_state": current_state,
            "is_host": current_state["host_id"] == user_id if current_state else False,
            "timestamp": datetime.utcnow().isoformat()
        }, room=sid)
        
        # Notify others in room
        await sio.emit('user_joined', {
            "user_id": user_id,
            "timestamp": datetime.utcnow().isoformat()
        }, room=room_id, skip_sid=sid)
        
        # Broadcast updated participant list to everyone in the room
        await broadcast_participant_list(room_id)
        
        logger.info(f"User {user_id} joined room {room_id}")
    except Exception as e:
        logger.error(f"Error in join_room: {e}")
        await sio.emit('error', {
            "message": "Failed to join room",
            "code": "JOIN_ERROR"
        }, room=sid)


@sio.event
async def leave_room_socket(sid, data):
    """
    Leave a music room.
    
    Expected payload:
    {
        "room_id": "room_xxx"  # Optional, uses current room if not provided
    }
    """
    try:
        user_id = user_socket_map.get(sid)
        if not user_id:
            return
        
        user_info = connected_users.get(user_id, {})
        room_id = data.get('room_id') or user_info.get("room_id")
        
        if not room_id:
            await sio.emit('error', {
                "message": "Not in a room",
                "code": "NOT_IN_ROOM"
            }, room=sid)
            return
        
        room_id = room_id.upper()
        
        # Leave room in database
        room_service = get_room_service()
        try:
            room_service.leave_room(room_id, user_id)
        except:
            pass
        
        # Update tracking
        connected_users[user_id]["room_id"] = None
        if room_id in room_users:
            room_users[room_id] = room_users[room_id] - {user_id}
        
        # Leave Socket.IO room
        await sio.leave_room(sid, room_id)
        
        # Notify others in room
        await sio.emit('user_left', {
            "user_id": user_id,
            "timestamp": datetime.utcnow().isoformat()
        }, room=room_id)
        
        # Broadcast updated participant list
        await broadcast_participant_list(room_id)
        
        # Send confirmation to user
        await sio.emit('room_left', {
            "room_id": room_id,
            "timestamp": datetime.utcnow().isoformat()
        }, room=sid)
        
        logger.info(f"User {user_id} left room {room_id}")
    except Exception as e:
        logger.error(f"Error in leave_room_socket: {e}")


@sio.event
async def sync_state(sid, data):
    """
    Host sends sync state update.
    
    Expected payload:
    {
        "room_id": "room_xxx",
        "playback_state": {
            "playing": bool,
            "position": float,
            "current_time": float
        },
        "current_song": {...}  # Optional
    }
    """
    try:
        user_id = user_socket_map.get(sid)
        if not user_id:
            return
        
        room_id = data.get('room_id')
        playback_state = data.get('playback_state')
        current_song = data.get('current_song')
        
        if not room_id or not playback_state:
            await sio.emit('error', {
                "message": "room_id and playback_state required",
                "code": "INVALID_REQUEST"
            }, room=sid)
            return
        
        room_id = room_id.upper()
        
        # Update room state (only host can do this)
        room_service = get_room_service()
        try:
            room_service.update_room_state(
                room_id=room_id,
                user_id=user_id,
                current_song=current_song,
                playback_state=playback_state
            )
        except ValueError as e:
            await sio.emit('error', {
                "message": str(e),
                "code": "UPDATE_FAILED"
            }, room=sid)
            return
        
        # Broadcast to all in room (except sender)
        await sio.emit('state_synced', {
            "playback_state": playback_state,
            "current_song": current_song,
            "timestamp": datetime.utcnow().isoformat()
        }, room=room_id, skip_sid=sid)
        
        logger.debug(f"State synced in room {room_id} by {user_id}")
    except Exception as e:
        logger.error(f"Error in sync_state: {e}")


@sio.event
async def room_chat(sid, data):
    """
    User sends a chat message to the room.
    
    Expected payload:
    {
        "room_id": "room_xxx",
        "message": "Hello world!"
    }
    """
    try:
        user_id = user_socket_map.get(sid)
        if not user_id:
            return
        
        room_id = data.get('room_id')
        message = data.get('message')
        
        if not room_id or not message:
            return
        
        room_id = room_id.upper()
        
        # In a real app, we'd fetch the name from DB. 
        # For efficiency, we can pass it from client or use a cached name if available.
        # Let's try to get user info if possible
        username = "User"
        try:
            from src.database.models import User, SessionLocal
            db = SessionLocal()
            user = db.query(User).filter(User.user_id == user_id).first()
            if user:
                username = user.username or user.name or user_id
            db.close()
        except:
            pass

        # Broadcast message to everyone in the room
        await sio.emit('room_chat', {
            "user_id": user_id,
            "username": username,
            "message": message,
            "timestamp": datetime.utcnow().isoformat()
        }, room=room_id)
        
        logger.info(f"Chat in room {room_id} from {user_id}: {message[:50]}...")
    except Exception as e:
        logger.error(f"Error in room_chat: {e}")


@sio.event
async def request_sync(sid, data):
    """
    Listener requests current sync state (for late joiners or reconnects).
    
    Expected payload:
    {
        "room_id": "room_xxx"
    }
    """
    try:
        user_id = user_socket_map.get(sid)
        if not user_id:
            return
        
        room_id = data.get('room_id')
        if not room_id:
            return
        
        room_id = room_id.upper()
        
        # Get current room state
        room_service = get_room_service()
        room_state = room_service.get_room_state(room_id)
        
        if room_state:
            await sio.emit('state_synced', {
                "playback_state": room_state.get("playback_state"),
                "current_song": room_state.get("current_song"),
                "timestamp": datetime.utcnow().isoformat()
            }, room=sid)
    except Exception as e:
        logger.error(f"Error in request_sync: {e}")


@sio.event
async def ping(sid, data):
    """Handle ping for connection keepalive"""
    try:
        user_id = user_socket_map.get(sid)
        if user_id and user_id in connected_users:
            connected_users[user_id]["last_ping"] = datetime.utcnow()
        
        await sio.emit('pong', {
            "timestamp": datetime.utcnow().isoformat()
        }, room=sid)
    except Exception as e:
        logger.error(f"Error in ping: {e}")


async def broadcast_participant_list(room_id: str):
    """Broadcast the list of currently online participants in a room"""
    try:
        user_ids = list(room_users.get(room_id, set()))
        if not user_ids:
            return

        participants = []
        try:
            from src.database.models import User, SessionLocal
            db = SessionLocal()
            users = db.query(User).filter(User.user_id.in_(user_ids)).all()
            
            # Create a map for quick lookup
            user_map = {u.user_id: u.username or u.name or u.user_id for u in users}
            
            for uid in user_ids:
                participants.append({
                    "user_id": uid,
                    "username": user_map.get(uid, "Unknown User")
                })
            db.close()
        except Exception as e:
            logger.error(f"Error fetching usernames for participant list: {e}")
            # Fallback to just IDs if DB fails
            for uid in user_ids:
                participants.append({"user_id": uid, "username": uid})

        await sio.emit('room_participants_update', {
            "room_id": room_id,
            "participants": participants,
            "timestamp": datetime.utcnow().isoformat()
        }, room=room_id)
    except Exception as e:
        logger.error(f"Error broadcasting participant list: {e}")


def get_socketio_app():
    """Get Socket.IO ASGI application"""
    return socketio.ASGIApp(sio)

