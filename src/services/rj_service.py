"""
RJ (Radio Jockey) Service
Uses LLM to talk to users as an RJ and suggest songs based on conversation
"""

import os
import logging
import requests
import json
import re
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from src.services.llm_sentiment_service import get_llm_sentiment_service
from src.services.recommendation_service import get_recommendation_service
from src.services.song_search_service import get_song_search_service

logger = logging.getLogger(__name__)


class RJService:
    """Service for RJ (Radio Jockey) interactions using LLM"""
    
    def __init__(self):
        self.llm_sentiment = get_llm_sentiment_service()
        self.recommendation_service = get_recommendation_service()
        self.song_search_service = get_song_search_service()
        self.conversations = {}  # Store conversation history
        
        # LLM Configuration
        self.api_provider = os.getenv("LLM_API_PROVIDER", "huggingface").lower()
        self.hf_api_key = os.getenv("HUGGINGFACE_API_KEY", "")
        self.hf_model = os.getenv("HF_MODEL", "TinyLlama/TinyLlama-1.1B-Chat-v1.0")
        self.use_online_api = os.getenv("USE_ONLINE_LLM", "true").lower() == "true"
    
    def generate_rj_response(
        self, 
        user_message: str, 
        user_id: str,
        conversation_context: Optional[List[Dict]] = None
    ) -> Dict:
        """
        Generate RJ-style response using LLM and suggest songs.
        
        Args:
            user_message: User's message
            user_id: User identifier
            conversation_context: Previous conversation messages
            
        Returns:
            Dictionary with RJ response, mood, and song recommendations
        """
        try:
            # Analyze sentiment first
            mood, confidence, explanation = self.llm_sentiment.analyze_sentiment(user_message)
            
            # Store conversation
            if user_id not in self.conversations:
                self.conversations[user_id] = []
            
            self.conversations[user_id].append({
                "user_message": user_message,
                "mood": mood,
                "timestamp": datetime.now().isoformat()
            })
            
            # Get conversation history for context
            recent_conversations = self.conversations[user_id][-5:] if len(self.conversations[user_id]) > 5 else self.conversations[user_id]
            
            # Generate RJ response using LLM
            rj_response = self._generate_rj_response_with_llm(
                user_message, 
                mood, 
                recent_conversations,
                user_id
            )
            
            # Extract song suggestions from conversation context
            suggested_songs = self._suggest_songs_from_conversation(
                user_message, 
                mood, 
                user_id,
                recent_conversations
            )
            
            return {
                "response": rj_response,
                "detected_mood": mood,
                "confidence": confidence,
                "explanation": explanation,
                "recommended_songs": suggested_songs,
                "personalized": len(suggested_songs) > 0
            }
            
        except Exception as e:
            logger.error(f"Error generating RJ response: {e}")
            # Fallback response
            return {
                "response": "Hey there! Thanks for tuning in! Let me find some great music for you! 🎵",
                "detected_mood": "happy",
                "confidence": 0.5,
                "explanation": "Default response",
                "recommended_songs": [],
                "personalized": False
            }
    
    def _generate_rj_response_with_llm(
        self, 
        user_message: str, 
        mood: str,
        conversation_history: List[Dict],
        user_id: str
    ) -> str:
        """Generate RJ-style response using LLM"""
        
        # Build conversation context
        context_str = ""
        if conversation_history:
            context_str = "\n".join([
                f"User: {conv.get('user_message', '')}"
                for conv in conversation_history[-3:]  # Last 3 messages
            ])
        
        # Build prompt for RJ
        prompt = f"""You are a friendly, energetic Radio Jockey (RJ) hosting a live music show. You talk to listeners, understand their mood, and suggest songs.

Current conversation context:
{context_str}

User just said: "{user_message}"
Detected mood: {mood}

Respond as an RJ would:
1. Be warm, friendly, and engaging
2. Acknowledge what the user said
3. Show understanding of their mood
4. Naturally transition to suggesting music
5. Keep it conversational and radio-like (1-2 sentences, max 80 words)
6. Use phrases like "That's great!", "I hear you", "Let me play something for you", etc.

RJ Response:"""

        if self.use_online_api and self.api_provider == "huggingface" and self.hf_api_key:
            try:
                response = self._call_hf_api(prompt)
                if response:
                    return response
            except Exception as e:
                logger.error(f"HF API error: {e}")
        
        # Fallback to rule-based RJ responses
        return self._generate_rj_response_fallback(user_message, mood)
    
    def _call_hf_api(self, prompt: str) -> Optional[str]:
        """Call Hugging Face API for LLM response"""
        try:
            url = f"https://api-inference.huggingface.co/models/{self.hf_model}"
            headers = {
                "Authorization": f"Bearer {self.hf_api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "inputs": prompt,
                "parameters": {
                    "max_new_tokens": 100,
                    "temperature": 0.8,
                    "return_full_text": False
                }
            }
            
            response = requests.post(url, headers=headers, json=payload, timeout=10)
            
            if response.status_code == 200:
                result = response.json()
                if isinstance(result, list) and len(result) > 0:
                    generated_text = result[0].get("generated_text", "").strip()
                    # Clean up the response
                    generated_text = re.sub(r'^RJ Response:\s*', '', generated_text, flags=re.IGNORECASE)
                    generated_text = generated_text.split('\n')[0].strip()  # Take first line
                    if generated_text and len(generated_text) > 10:
                        return generated_text[:200]  # Limit length
            
            return None
            
        except Exception as e:
            logger.error(f"HF API call error: {e}")
            return None
    
    def _generate_rj_response_fallback(self, user_message: str, mood: str) -> str:
        """Fallback rule-based RJ responses"""
        mood_responses = {
            "happy": [
                "That's fantastic! I love that positive energy! Let me play something upbeat that'll keep that smile on your face! 🎵",
                "Awesome! You're in such a great mood! I've got the perfect track to match that energy!",
                "Love it! That happiness is contagious! Let me spin something that'll make you want to dance!"
            ],
            "sad": [
                "I hear you, and I'm here for you. Music can be such a comfort. Let me play something that might help you feel better.",
                "I understand. Sometimes we need music that understands us. Let me find something that speaks to what you're feeling.",
                "It's okay to feel this way. Let me play something gentle and comforting for you."
            ],
            "calm": [
                "That peaceful vibe is beautiful! Let me play something serene that'll keep you in that zen state!",
                "Perfect! That calm energy is so precious. I've got some relaxing tracks that'll enhance that tranquility!",
                "I love that peaceful feeling! Let me spin something gentle and soothing for you!"
            ],
            "energetic": [
                "YES! That energy is amazing! Let me play something that'll match that fire and keep you pumped! 🔥",
                "I can feel that energy through the radio! Let me drop something high-energy that'll keep you moving!",
                "That's the spirit! I've got the perfect energetic track to fuel that motivation!"
            ],
            "tired": [
                "I get it, you've had a long day. Let me play something gentle and soothing to help you unwind.",
                "Take it easy! Let me find some peaceful music to help you relax and recharge.",
                "You deserve some rest. Let me play something calming to help you unwind."
            ],
            "anxious": [
                "I understand that feeling. Music can really help. Let me play something calming and grounding for you.",
                "It's okay, take a deep breath. Let me find some peaceful music that'll help you feel more centered.",
                "I'm here with you. Let me play something soothing that might help ease that anxiety."
            ],
            "romantic": [
                "Aww, that's so sweet! Let me play something romantic that'll make your heart flutter! 💕",
                "Love is in the air! I've got the perfect romantic track for you!",
                "How beautiful! Let me spin something that captures that loving feeling!"
            ],
            "nostalgic": [
                "Those memories are precious! Let me play something that might bring back those beautiful moments.",
                "I love that nostalgic feeling! Let me find a track that captures that essence.",
                "Those memories are special. Let me play something that resonates with that sentiment."
            ]
        }
        
        import random
        responses = mood_responses.get(mood, [
            "Thanks for sharing! Let me play something great for you! 🎵",
            "I hear you! Let me find the perfect track!",
            "Got it! Let me spin something that'll hit just right!"
        ])
        
        return random.choice(responses)
    
    def _suggest_songs_from_conversation(
        self,
        user_message: str,
        mood: str,
        user_id: str,
        conversation_history: List[Dict]
    ) -> List[Dict]:
        """Suggest songs based on conversation context using LLM and recommendation service"""
        try:
            # Try to extract song preferences, genres, or artists from conversation
            all_text = user_message.lower()
            if conversation_history:
                all_text += " " + " ".join([conv.get("user_message", "").lower() for conv in conversation_history])
            
            # Extract keywords that might indicate music preferences
            genre_keywords = {
                "rock": ["rock", "guitar", "band"],
                "pop": ["pop", "catchy", "mainstream"],
                "jazz": ["jazz", "smooth", "sophisticated"],
                "classical": ["classical", "orchestra", "symphony"],
                "electronic": ["electronic", "edm", "dance", "techno"],
                "hip hop": ["hip hop", "rap", "hiphop"],
                "country": ["country", "folk"],
                "r&b": ["r&b", "soul", "rnb"],
                "devotional": ["devotional", "spiritual", "bhajan", "prayer"],
                "indie": ["indie", "alternative"]
            }
            
            detected_genres = []
            for genre, keywords in genre_keywords.items():
                if any(kw in all_text for kw in keywords):
                    detected_genres.append(genre)
            
            # Get recommendations based on mood and detected genres
            recommendations = []
            
            # Try mood-based recommendations first
            try:
                if detected_genres:
                    # Search by genre
                    for genre in detected_genres[:2]:  # Limit to 2 genres
                        songs = self.song_search_service.search_songs(genre, limit=3)
                        recommendations.extend(songs)
                
                # Also try mood-based search
                mood_queries = {
                    "happy": "upbeat happy energetic",
                    "sad": "sad emotional melancholic",
                    "angry": "intense powerful rock",
                    "calm": "calm peaceful relaxing",
                    "energetic": "energetic workout pump",
                    "tired": "gentle soothing lullaby",
                    "anxious": "calming peaceful meditation",
                    "romantic": "romantic love ballad",
                    "nostalgic": "nostalgic classic old",
                    "focused": "instrumental ambient background"
                }
                
                mood_query = mood_queries.get(mood, mood)
                mood_songs = self.song_search_service.search_songs(mood_query, limit=3)
                recommendations.extend(mood_songs)
                
                # Also get personalized recommendations if user has taste profile
                try:
                    recs = self.recommendation_service.get_recommendations(
                        user_id=user_id,
                        limit=5,
                        mood=mood,
                        genre=detected_genres if detected_genres else None
                    )
                    recommendations.extend(recs)
                except Exception as e:
                    logger.debug(f"Could not get personalized recommendations: {e}")
                    
            except Exception as e:
                logger.error(f"Error getting recommendations: {e}")
            
            # Remove duplicates
            seen = set()
            unique_recommendations = []
            for song in recommendations:
                title_key = (song.get("title", "").lower(), 
                           (song.get("artists", []) or song.get("song", {}).get("artists", []))[0].lower() if (song.get("artists") or song.get("song", {}).get("artists")) else "")
                if title_key not in seen:
                    seen.add(title_key)
                    unique_recommendations.append(song)
            
            return unique_recommendations[:5]  # Return top 5
            
        except Exception as e:
            logger.error(f"Error suggesting songs: {e}")
            return []
    
    def get_conversation_history(self, user_id: str, limit: int = 10) -> List[Dict]:
        """Get conversation history for a user"""
        if user_id not in self.conversations:
            return []
        return self.conversations[user_id][-limit:]


# Singleton instance
_rj_service = None

def get_rj_service() -> RJService:
    """Get singleton instance of RJService"""
    global _rj_service
    if _rj_service is None:
        _rj_service = RJService()
    return _rj_service

