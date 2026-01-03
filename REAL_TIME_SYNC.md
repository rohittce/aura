# Real-Time Synchronized Music Listening System

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                      Frontend (Browser)                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ Friend UI    │  │ Room UI      │  │ Music Player │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│         │                 │                 │               │
│         └─────────────────┴─────────────────┘               │
│                            │                                 │
│                    ┌───────▼────────┐                        │
│                    │ WebSocket Client│                        │
│                    │ (Socket.IO)     │                        │
│                    └───────┬────────┘                        │
└────────────────────────────┼─────────────────────────────────┘
                             │
                             │ WebSocket (Socket.IO)
                             │
┌────────────────────────────▼─────────────────────────────────┐
│                    Backend (FastAPI)                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │Friend Service│  │ Room Service │  │WebSocket Svc │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│         │                 │                 │               │
│         └─────────────────┴─────────────────┘               │
│                            │                                 │
│                    ┌───────▼────────┐                        │
│                    │   Database     │                         │
│                    │  (PostgreSQL)  │                         │
│                    └───────────────┘                         │
└──────────────────────────────────────────────────────────────┘
```

## Database Schema

### Users Table (Enhanced)
- `user_id` (PK)
- `email` (unique)
- `username` (unique, indexed) - **NEW**
- `name`
- `password_hash`
- `created_at`, `last_login`
- `profile` (JSON)

### Friend Requests Table (NEW)
- `id` (PK)
- `sender_id` (FK → users)
- `receiver_id` (FK → users)
- `status` (pending, accepted, rejected)
- `created_at`, `responded_at`

### Friendships Table (NEW)
- `id` (PK)
- `user1_id` (FK → users)
- `user2_id` (FK → users)
- `created_at`
- Unique constraint on (user1_id, user2_id)

### Music Rooms Table (NEW)
- `room_id` (PK)
- `host_id` (FK → users)
- `name` (optional)
- `is_friends_only` (boolean)
- `current_song` (JSON)
- `playback_state` (JSON) - {playing, position, timestamp, current_time}
- `created_at`, `last_activity`

### Room Participants Table (NEW)
- `id` (PK)
- `room_id` (FK → music_rooms)
- `user_id` (FK → users)
- `joined_at`, `last_seen`
- `is_active` (boolean)
- Unique constraint on (room_id, user_id)

## Socket.IO Event Contract

### Client → Server Events

#### `connect`
**Authentication**: Token in `auth.token` or query parameter `?token=xxx`

**Payload**: None

**Response**: `connected` event with `{user_id, timestamp}`

---

#### `join_room`
**Payload**:
```json
{
  "room_id": "room_xxx"
}
```

**Response**: `room_joined` event

---

#### `leave_room_socket`
**Payload**:
```json
{
  "room_id": "room_xxx"  // Optional, uses current room
}
```

**Response**: `room_left` event

---

#### `sync_state` (Host Only)
**Payload**:
```json
{
  "room_id": "room_xxx",
  "playback_state": {
    "playing": true,
    "position": 45.5,  // Current position in seconds
    "current_time": 45.5
  },
  "current_song": {  // Optional
    "title": "Song Title",
    "artists": ["Artist"],
    "youtube_video_id": "xxx"
  }
}
```

**Response**: None (broadcasts `state_synced` to all listeners)

---

#### `request_sync`
**Payload**:
```json
{
  "room_id": "room_xxx"
}
```

**Response**: `state_synced` event with current room state

---

#### `ping`
**Payload**: Optional data

**Response**: `pong` event with timestamp

---

### Server → Client Events

#### `connected`
```json
{
  "user_id": "user_xxx",
  "timestamp": "2024-01-01T00:00:00Z"
}
```

---

#### `room_joined`
```json
{
  "room_id": "room_xxx",
  "room_state": {
    "host_id": "user_xxx",
    "name": "Room Name",
    "current_song": {...},
    "playback_state": {...},
    "participants": ["user_xxx", "user_yyy"]
  },
  "is_host": true,
  "timestamp": "2024-01-01T00:00:00Z"
}
```

---

#### `room_left`
```json
{
  "room_id": "room_xxx",
  "timestamp": "2024-01-01T00:00:00Z"
}
```

---

#### `user_joined`
```json
{
  "user_id": "user_xxx",
  "timestamp": "2024-01-01T00:00:00Z"
}
```

---

#### `user_left`
```json
{
  "user_id": "user_xxx",
  "timestamp": "2024-01-01T00:00:00Z"
}
```

---

#### `state_synced`
```json
{
  "playback_state": {
    "playing": true,
    "position": 45.5,
    "timestamp": "2024-01-01T00:00:00Z",
    "current_time": 45.5
  },
  "current_song": {
    "title": "Song Title",
    "artists": ["Artist"],
    "youtube_video_id": "xxx"
  },
  "timestamp": "2024-01-01T00:00:00Z"
}
```

---

#### `error`
```json
{
  "message": "Error description",
  "code": "ERROR_CODE"
}
```

---

#### `pong`
```json
{
  "timestamp": "2024-01-01T00:00:00Z"
}
```

---

## Synchronization Algorithm

### Time-Based Sync

The system uses **server time as the source of truth** to prevent desync:

1. **Host sends sync state**:
   ```javascript
   {
     playing: true,
     position: 45.5,  // Current playback position
     timestamp: "2024-01-01T12:00:00.000Z"  // Server timestamp
   }
   ```

2. **Listeners receive sync state**:
   - Calculate time drift: `drift = now() - sync.timestamp`
   - Adjust position: `adjustedPosition = sync.position + drift`
   - If playing: `currentPosition = adjustedPosition + (now() - receivedAt)`

3. **Late Joiners**:
   - Request current state via `request_sync`
   - Receive state with server timestamp
   - Apply same drift correction

### Drift Correction

```javascript
function syncPlayback(syncState) {
  const serverTime = new Date(syncState.timestamp);
  const clientTime = new Date();
  const drift = clientTime - serverTime;
  
  let currentPosition = syncState.position;
  
  if (syncState.playing) {
    // Account for time since sync
    const timeSinceSync = (Date.now() - serverTime.getTime()) / 1000;
    currentPosition = syncState.position + timeSinceSync;
  }
  
  // Apply drift correction (optional, for very high precision)
  const driftSeconds = drift / 1000;
  currentPosition += driftSeconds;
  
  return currentPosition;
}
```

### Periodic Sync

**Host**: Sends sync state every 1 second (configurable)

**Listeners**: Apply drift correction on each sync event

---

## API Endpoints

### Friend Management

- `POST /api/v1/friends/search?q=username&limit=20` - Search users
- `POST /api/v1/friends/request` - Send friend request
- `POST /api/v1/friends/accept` - Accept friend request
- `POST /api/v1/friends/reject` - Reject friend request
- `GET /api/v1/friends/requests?type=sent|received` - Get requests
- `GET /api/v1/friends` - Get friends list
- `DELETE /api/v1/friends/{friend_id}` - Remove friend

### Room Management

- `POST /api/v1/rooms/create` - Create room
- `POST /api/v1/rooms/join` - Join room
- `POST /api/v1/rooms/{room_id}/leave` - Leave room
- `GET /api/v1/rooms/{room_id}` - Get room state
- `GET /api/v1/rooms` - Get user's rooms

### User Management

- `POST /api/v1/auth/username` - Update username

---

## Security & Performance

### Authentication
- JWT tokens required for all API endpoints
- WebSocket connections authenticated via token in `auth` or query parameter
- Token verified on connection

### Rate Limiting
- Friend requests: Max 10 per hour per user
- Room creation: Max 5 per hour per user
- Socket events: Max 60 events per minute per connection

### Performance Optimizations
- In-memory cache for room state (production: use Redis)
- Database indexes on frequently queried fields
- Connection pooling for database
- Efficient room cleanup (background task every hour)

### Scalability
- Horizontal scaling: Use Redis for Socket.IO adapter
- Room state stored in database (persistent)
- WebSocket connections can be load-balanced with sticky sessions

---

## Deployment

### Environment Variables
```bash
DATABASE_URL=postgresql://user:pass@host:port/db
ALLOWED_ORIGINS=https://your-app.com,http://localhost:3000
```

### Production Setup
1. **Database**: PostgreSQL (required)
2. **Redis** (optional, for multi-server Socket.IO):
   ```bash
   REDIS_URL=redis://localhost:6379
   ```
3. **WebSocket**: Ensure proxy supports WebSocket upgrades
   - Nginx: `proxy_http_version 1.1; proxy_set_header Upgrade $http_upgrade;`
   - CORS: Configure allowed origins

### Running
```bash
# Install dependencies
pip install -r requirements.txt

# Run migrations (tables auto-created)
python setup_database.py

# Start server
uvicorn src.api.main:app --host 0.0.0.0 --port 8000
```

---

## Frontend Integration

See `static/friend-room-client.js` for complete WebSocket client implementation.

### Basic Usage

```javascript
// Initialize client
const client = new FriendRoomClient(API_BASE, token);
await client.connect();

// Create room
const room = await client.createRoom("My Room", false);

// Join room (WebSocket)
await client.joinRoom(room.room_id);

// Setup callbacks
client.onRoomStateChange = (state) => {
  // Update player UI with state
  updatePlayer(state.playback_state, state.current_song);
};

// Host: Start syncing
client.startSync(() => {
  return {
    playback_state: {
      playing: audioElement.paused === false,
      position: audioElement.currentTime,
      current_time: audioElement.currentTime
    },
    current_song: currentSongData
  };
}, 1000); // Sync every 1 second
```

---

## Error Handling

### Common Error Codes

- `AUTH_REQUIRED` - Not authenticated
- `INVALID_REQUEST` - Missing required fields
- `JOIN_FAILED` - Cannot join room (not friends, room full, etc.)
- `UPDATE_FAILED` - Only host can update state
- `NOT_IN_ROOM` - User not in specified room

---

## Testing

### Manual Testing Checklist

1. ✅ User registration with username
2. ✅ Search users by username
3. ✅ Send/accept/reject friend requests
4. ✅ Create friends-only room
5. ✅ Join room via API
6. ✅ Connect WebSocket
7. ✅ Host plays music, listeners sync
8. ✅ Late joiner receives current state
9. ✅ Host transfer when host leaves
10. ✅ Room cleanup when empty

---

## Future Enhancements

- [ ] Queue system (host can queue songs)
- [ ] Voice chat integration
- [ ] Room chat/messaging
- [ ] Room discovery (public rooms)
- [ ] Playlist sharing
- [ ] Mobile app support
- [ ] Push notifications for friend requests

