/**
 * Friend and Room Management Client
 * Handles WebSocket connections, friend management, and synchronized music rooms
 */

class FriendRoomClient {
    constructor(apiBase, token) {
        this.apiBase = apiBase;
        this.token = token;
        this.userId = null;
        this.socket = null;
        this.currentRoom = null;
        this.isHost = false;
        this.syncInterval = null;
        this.lastSyncTime = null;

        // Event callbacks
        this.onRoomStateChange = null;
        this.onUserJoined = null;
        this.onUserLeft = null;
        this.onError = null;
    }

    /**
     * Initialize Socket.IO connection
     */
    async connect() {
        if (!this.token) {
            console.error("Token required for WebSocket connection");
            return false;
        }

        try {
            // Load Socket.IO client library if not already loaded
            if (typeof io === 'undefined') {
                await this.loadSocketIO();
            }

            // Connect to Socket.IO server
            const wsUrl = this.apiBase.replace('/api/v1', '');
            this.socket = io(wsUrl, {
                auth: { token: this.token },
                transports: ['websocket', 'polling'],
                reconnection: true,
                reconnectionDelay: 1000,
                reconnectionAttempts: 5
            });

            // Setup event handlers
            this.setupSocketHandlers();

            return new Promise((resolve) => {
                this.socket.on('connect', () => {
                    console.log('WebSocket connected');
                    resolve(true);
                });

                this.socket.on('connect_error', (error) => {
                    console.error('WebSocket connection error:', error);
                    resolve(false);
                });
            });
        } catch (error) {
            console.error('Error connecting WebSocket:', error);
            return false;
        }
    }

    /**
     * Load Socket.IO client library dynamically
     */
    loadSocketIO() {
        return new Promise((resolve, reject) => {
            if (typeof io !== 'undefined') {
                resolve();
                return;
            }

            const script = document.createElement('script');
            script.src = 'https://cdn.socket.io/4.5.4/socket.io.min.js';
            script.onload = resolve;
            script.onerror = reject;
            document.head.appendChild(script);
        });
    }

    /**
     * Setup Socket.IO event handlers
     */
    setupSocketHandlers() {
        this.socket.on('connected', (data) => {
            console.log('Authenticated:', data);
            this.userId = data.user_id;
        });

        this.socket.on('room_joined', (data) => {
            console.log('Joined room:', data);
            this.currentRoom = data.room_id;
            this.isHost = data.is_host;

            // Request current state
            this.requestSync();

            if (this.onRoomStateChange) {
                this.onRoomStateChange(data.room_state);
            }
        });

        this.socket.on('room_left', (data) => {
            console.log('Left room:', data);
            this.currentRoom = null;
            this.isHost = false;
            this.stopSync();
        });

        this.socket.on('user_joined', (data) => {
            console.log('User joined:', data);
            if (this.onUserJoined) {
                this.onUserJoined(data);
            }
        });

        this.socket.on('user_left', (data) => {
            console.log('User left:', data);
            if (this.onUserLeft) {
                this.onUserLeft(data);
            }
        });

        this.socket.on('state_synced', (data) => {
            console.log('State synced:', data);
            this.lastSyncTime = new Date(data.timestamp);

            if (this.onRoomStateChange) {
                this.onRoomStateChange({
                    current_song: data.current_song,
                    playback_state: data.playback_state
                });
            }
        });

        this.socket.on('error', (data) => {
            console.error('Socket error:', data);
            if (this.onError) {
                this.onError(data);
            }
        });

        this.socket.on('disconnect', () => {
            console.log('WebSocket disconnected');
            this.stopSync();
        });
    }

    /**
     * Join a music room
     */
    async joinRoom(roomId) {
        if (!this.socket || !this.socket.connected) {
            await this.connect();
        }

        const rId = roomId.toUpperCase();
        this.socket.emit('join_room', { room_id: rId });
    }

    /**
     * Leave current room
     */
    leaveRoom() {
        if (this.socket && this.currentRoom) {
            const rId = this.currentRoom.toUpperCase();
            this.socket.emit('leave_room_socket', { room_id: rId });
            this.currentRoom = null;
            this.isHost = false;
            this.stopSync();
        }
    }

    /**
     * Send sync state (host only)
     */
    syncState(playbackState, currentSong = null) {
        if (!this.isHost || !this.socket || !this.currentRoom) {
            return;
        }

        const rId = this.currentRoom.toUpperCase();
        this.socket.emit('sync_state', {
            room_id: rId,
            playback_state: playbackState,
            current_song: currentSong
        });
    }

    /**
     * Request current sync state (for late joiners)
     */
    requestSync() {
        if (!this.socket || !this.currentRoom) {
            return;
        }

        const rId = this.currentRoom.toUpperCase();
        this.socket.emit('request_sync', { room_id: rId });
    }

    /**
     * Start periodic sync (host only)
     */
    startSync(updateCallback, intervalMs = 1000) {
        if (!this.isHost) {
            return;
        }

        this.stopSync();

        this.syncInterval = setInterval(() => {
            if (updateCallback) {
                const state = updateCallback();
                if (state) {
                    this.syncState(state.playback_state, state.current_song);
                }
            }
        }, intervalMs);
    }

    /**
     * Stop periodic sync
     */
    stopSync() {
        if (this.syncInterval) {
            clearInterval(this.syncInterval);
            this.syncInterval = null;
        }
    }

    /**
     * Disconnect WebSocket
     */
    disconnect() {
        this.leaveRoom();
        this.stopSync();

        if (this.socket) {
            this.socket.disconnect();
            this.socket = null;
        }
    }

    // Friend Management API methods

    async searchUsers(query, limit = 20) {
        const response = await fetch(`${this.apiBase}/friends/search?q=${encodeURIComponent(query)}&limit=${limit}`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${this.token}`,
                'Content-Type': 'application/json'
            }
        });
        return response.json();
    }

    async sendFriendRequest(username) {
        const response = await fetch(`${this.apiBase}/friends/request`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${this.token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ receiver_username: username })
        });
        return response.json();
    }

    async acceptFriendRequest(senderId) {
        const response = await fetch(`${this.apiBase}/friends/accept`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${this.token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ sender_id: senderId })
        });
        return response.json();
    }

    async rejectFriendRequest(senderId) {
        const response = await fetch(`${this.apiBase}/friends/reject`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${this.token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ sender_id: senderId })
        });
        return response.json();
    }

    async getFriendRequests(type = 'received') {
        const response = await fetch(`${this.apiBase}/friends/requests?type=${type}`, {
            headers: {
                'Authorization': `Bearer ${this.token}`
            }
        });
        return response.json();
    }

    async getFriends() {
        const response = await fetch(`${this.apiBase}/friends`, {
            headers: {
                'Authorization': `Bearer ${this.token}`
            }
        });
        return response.json();
    }

    async removeFriend(friendId) {
        const response = await fetch(`${this.apiBase}/friends/${friendId}`, {
            method: 'DELETE',
            headers: {
                'Authorization': `Bearer ${this.token}`
            }
        });
        return response.json();
    }

    // Room Management API methods

    async createRoom(name = null, isFriendsOnly = false) {
        const response = await fetch(`${this.apiBase}/rooms/create`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${this.token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ name, is_friends_only: isFriendsOnly })
        });
        return response.json();
    }

    async joinRoomAPI(roomId) {
        const response = await fetch(`${this.apiBase}/rooms/join`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${this.token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ room_id: roomId })
        });
        return response.json();
    }

    async leaveRoomAPI(roomId) {
        const response = await fetch(`${this.apiBase}/rooms/${roomId}/leave`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${this.token}`
            }
        });
        return response.json();
    }

    async getRoomState(roomId) {
        const response = await fetch(`${this.apiBase}/rooms/${roomId}`, {
            headers: {
                'Authorization': `Bearer ${this.token}`
            }
        });
        return response.json();
    }

    async getUserRooms() {
        const response = await fetch(`${this.apiBase}/rooms`, {
            headers: {
                'Authorization': `Bearer ${this.token}`
            }
        });
        return response.json();
    }

    async updateUsername(username) {
        const response = await fetch(`${this.apiBase}/auth/username`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${this.token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ username })
        });
        return response.json();
    }
}

// Export for use in HTML
if (typeof window !== 'undefined') {
    window.FriendRoomClient = FriendRoomClient;
}

