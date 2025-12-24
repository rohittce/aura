"""
Chatbot Service
Analyzes user sentiments from conversations and recommends music
Uses Llama model for sentiment analysis
Integrates with taste profile for personalized recommendations
"""

import re
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from src.services.llm_sentiment_service import get_llm_sentiment_service
from src.services.embedding_service import EmbeddingService


class ChatbotService:
    """Service for chatbot interactions and sentiment analysis"""
    
    def __init__(self):
        # Conversation context
        self.conversations = {}
        # Initialize LLM sentiment service
        self.llm_sentiment = get_llm_sentiment_service()
        # Initialize embedding service for taste profile integration
        self.embedding_service = EmbeddingService()
    
    def analyze_sentiment(self, message: str) -> Tuple[str, float, str]:
        """
        Analyze sentiment from user message using Llama model.
        
        Args:
            message: User's message
            
        Returns:
            Tuple of (mood, confidence_score, explanation)
        """
        # Use LLM for sentiment analysis
        mood, confidence, explanation = self.llm_sentiment.analyze_sentiment(message)
        return mood, confidence, explanation
    
    def generate_response(self, user_message: str, user_id: str) -> Dict:
        """
        Generate chatbot response based on user message.
        
        Args:
            user_message: User's message
            user_id: User identifier
            
        Returns:
            Response dictionary with message, sentiment, and recommendations
        """
        # Analyze sentiment using LLM
        mood, confidence, explanation = self.analyze_sentiment(user_message)
        
        # Store conversation
        if user_id not in self.conversations:
            self.conversations[user_id] = []
        
        self.conversations[user_id].append({
            "user_message": user_message,
            "mood": mood,
            "confidence": confidence,
            "explanation": explanation,
            "timestamp": datetime.now().isoformat()
        })
        
        # Generate empathetic response
        response = self._generate_empathetic_response(user_message, mood, confidence)
        
        return {
            "response": response,
            "detected_mood": mood,
            "confidence": confidence,
            "explanation": explanation,
            "recommendation_hint": self._get_recommendation_hint(mood)
        }
    
    def _generate_empathetic_response(self, message: str, mood: str, confidence: float) -> str:
        """Generate empathetic chatbot response"""
        
        responses = {
            "happy": [
                "That's wonderful to hear! Let's keep that positive energy going with some upbeat music! 🎵",
                "I'm so glad you're feeling great! How about some energetic songs to match your mood?",
                "Awesome! Your happiness is contagious. Let me find some joyful tunes for you!"
            ],
            "sad": [
                "I'm sorry you're feeling down. Music can be a great companion during tough times. Let me find some comforting songs for you.",
                "It sounds like you're going through a difficult time. Would you like some calming or uplifting music to help?",
                "I understand. Sometimes music helps us process our feelings. Let me suggest some songs that might resonate."
            ],
            "angry": [
                "I can sense some frustration. Music can be a great way to channel that energy. Would you like some intense or calming tracks?",
                "It sounds like you're dealing with something difficult. Let me find some music that might help you process this.",
                "I hear you. Sometimes we need music that matches our intensity. Let me suggest some powerful tracks."
            ],
            "calm": [
                "That peaceful energy is lovely! Let me find some serene, relaxing music to maintain that calm.",
                "A calm moment is precious. How about some ambient or gentle music to enhance that tranquility?",
                "Perfect time for some chill vibes! Let me suggest some relaxing tracks."
            ],
            "energetic": [
                "Love that energy! Let's match it with some high-energy tracks to keep you pumped! 💪",
                "You're in the zone! How about some workout-ready songs to fuel that motivation?",
                "That's the spirit! Let me find some energetic beats to match your vibe!"
            ],
            "tired": [
                "Sounds like you need some rest. Would you like some gentle, calming music to help you unwind?",
                "I understand feeling drained. Let me find some soothing tracks to help you relax and recharge.",
                "Take it easy. How about some peaceful, ambient music to help you unwind?"
            ],
            "anxious": [
                "I can sense some stress. Music can be really helpful for anxiety. Let me find some calming, grounding tracks.",
                "It sounds like you're feeling overwhelmed. Would you like some peaceful music to help you center yourself?",
                "I understand that anxious feeling. Let me suggest some soothing songs that might help you feel more grounded."
            ],
            "romantic": [
                "How sweet! Let me find some romantic tunes to match that loving feeling! 💕",
                "That's beautiful! How about some love songs to enhance that romantic mood?",
                "Love is in the air! Let me suggest some romantic tracks for you."
            ],
            "nostalgic": [
                "Nostalgia can be beautiful. Let me find some songs that might bring back those memories.",
                "Those memories are precious. How about some classic or sentimental tracks?",
                "I love that nostalgic feeling. Let me suggest some songs that capture that essence."
            ],
            "focused": [
                "Great focus! Let me find some instrumental or ambient tracks to help you stay in the zone.",
                "Productivity mode activated! How about some background music that won't distract?",
                "Let's keep that concentration going! I'll suggest some focus-friendly tracks."
            ]
        }
        
        # Select response based on mood
        mood_responses = responses.get(mood, ["I understand. Let me find some music that might help."])
        import random
        base_response = random.choice(mood_responses)
        
        # Add follow-up question
        follow_ups = [
            " What kind of music are you in the mood for?",
            " Would you like me to play something now?",
            " Should I create a playlist for you?"
        ]
        
        return base_response + random.choice(follow_ups)
    
    def _get_recommendation_hint(self, mood: str) -> str:
        """Get hint for music recommendation based on mood"""
        hints = {
            "happy": "upbeat, energetic, positive",
            "sad": "melancholic, emotional, comforting",
            "angry": "intense, powerful, cathartic",
            "calm": "peaceful, relaxing, ambient",
            "energetic": "high-energy, workout, motivational",
            "tired": "gentle, soothing, lullaby-like",
            "anxious": "calming, grounding, peaceful",
            "romantic": "love songs, tender, emotional",
            "nostalgic": "classic, sentimental, memory-evoking",
            "focused": "instrumental, ambient, non-distracting"
        }
        return hints.get(mood, "varied")
    
    def get_conversation_history(self, user_id: str, limit: int = 10) -> List[Dict]:
        """Get conversation history for a user"""
        if user_id not in self.conversations:
            return []
        return self.conversations[user_id][-limit:]
    
    def get_user_mood_trend(self, user_id: str, days: int = 7) -> Dict:
        """Get mood trends over time"""
        if user_id not in self.conversations:
            return {}
        
        conversations = self.conversations[user_id]
        mood_counts = {}
        
        for conv in conversations:
            mood = conv.get("mood", "neutral")
            mood_counts[mood] = mood_counts.get(mood, 0) + 1
        
        total = sum(mood_counts.values())
        mood_percentages = {mood: (count / total * 100) if total > 0 else 0 
                           for mood, count in mood_counts.items()}
        
        return {
            "mood_distribution": mood_percentages,
            "total_conversations": total,
            "dominant_mood": max(mood_counts.items(), key=lambda x: x[1])[0] if mood_counts else "neutral"
        }
    
    def get_mood_recommendations_with_taste(
        self,
        user_id: str,
        mood: str,
        taste_profile: Optional[Dict] = None,
        song_candidates: List[Dict] = None,
        limit: int = 5
    ) -> List[Dict]:
        """
        Get mood-based recommendations integrated with user taste profile.
        
        Args:
            user_id: User identifier
            mood: Detected mood
            taste_profile: User's taste profile (from RecommendationService)
            song_candidates: List of candidate songs from mood search
            limit: Number of recommendations to return
            
        Returns:
            List of recommended songs scored by both mood and taste similarity
        """
        if not song_candidates:
            return []
        
        # If no taste profile, return top candidates
        if not taste_profile or "taste_vector" not in taste_profile:
            return song_candidates[:limit]
        
        taste_vector = np.array(taste_profile["taste_vector"])
        
        # Score each candidate by taste similarity
        scored_songs = []
        for song in song_candidates:
            try:
                # Generate embedding for candidate song
                emb, _ = self.embedding_service.embed_song(
                    song.get("title", ""),
                    song.get("artists", ["Unknown"]),
                    song.get("genre", [])
                )
                
                # Calculate cosine similarity with taste profile
                similarity = self.embedding_service.cosine_similarity(taste_vector, emb)
                
                # Combine mood relevance (0.3) with taste similarity (0.7)
                # This gives more weight to taste profile while still considering mood
                mood_weight = 0.3
                taste_weight = 0.7
                
                # All candidates are mood-relevant, so give base score
                mood_score = 0.8  # Base relevance for mood-matched songs
                
                # Final score: weighted combination
                final_score = (mood_weight * mood_score) + (taste_weight * float(similarity))
                
                scored_songs.append({
                    **song,
                    "similarity": float(similarity),
                    "taste_score": float(similarity),
                    "mood_score": mood_score,
                    "final_score": final_score
                })
            except Exception as e:
                # If embedding fails, use default score
                scored_songs.append({
                    **song,
                    "similarity": 0.5,
                    "taste_score": 0.5,
                    "mood_score": 0.8,
                    "final_score": 0.6
                })
        
        # Sort by final score (descending)
        scored_songs.sort(key=lambda x: x["final_score"], reverse=True)
        
        # Return top recommendations
        return scored_songs[:limit]


# Singleton instance
_chatbot_service = None

def get_chatbot_service() -> ChatbotService:
    """Get singleton instance of ChatbotService"""
    global _chatbot_service
    if _chatbot_service is None:
        _chatbot_service = ChatbotService()
    return _chatbot_service

