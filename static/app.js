// AURA Frontend API Client
// Auto-detect API URL based on environment
const API_BASE = (typeof window !== 'undefined' && (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'))
    ? 'http://localhost:8000/api/v1'
    : (typeof window !== 'undefined' ? window.location.origin + '/api/v1' : 'http://localhost:8000/api/v1');

class AuraAPI {
    constructor(userId) {
        this.userId = userId || this.generateUserId();
    }

    generateUserId() {
        return 'user_' + Math.random().toString(36).substr(2, 9);
    }

    async analyzeTaste(seedSongs, context = {}) {
        const response = await fetch(`${API_BASE}/taste/analyze`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                user_id: this.userId,
                seed_songs: seedSongs,
                context: context
            })
        });
        return response.json();
    }

    async getRecommendations(limit = 10, context = null, mood = null) {
        const params = new URLSearchParams({
            user_id: this.userId,
            limit: limit.toString()
        });
        if (context) params.append('context', JSON.stringify(context));
        if (mood) params.append('mood', mood);

        const response = await fetch(`${API_BASE}/recommendations?${params}`);
        return response.json();
    }

    async submitFeedback(recommendationId, songId, feedbackType, feedbackDetails = null, context = {}) {
        const response = await fetch(`${API_BASE}/feedback`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                user_id: this.userId,
                recommendation_id: recommendationId,
                song_id: songId,
                feedback_type: feedbackType,
                feedback_details: feedbackDetails,
                context: context
            })
        });
        return response.json();
    }

    async getTasteProfile() {
        const response = await fetch(`${API_BASE}/taste/profile?user_id=${this.userId}`);
        return response.json();
    }

    getTimeOfDay() {
        const hour = new Date().getHours();
        if (hour < 12) return 'morning';
        if (hour < 17) return 'afternoon';
        if (hour < 21) return 'evening';
        return 'night';
    }
}

// Export for use in HTML
if (typeof window !== 'undefined') {
    window.AuraAPI = AuraAPI;
}

