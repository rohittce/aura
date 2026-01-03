"""
RJ (Radio Jockey) Service - Enhanced Version
Uses Llama model via Groq/HuggingFace to talk to users as an RJ, analyze mood,
and recommend songs based on conversation with rate limiting.
"""

import os
import logging
import requests
import json
import re
import time
import hashlib
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from functools import wraps
from collections import defaultdict
from threading import Lock

logger = logging.getLogger(__name__)


class RateLimiter:
    """Token bucket rate limiter for API calls"""
    
    def __init__(self, calls_per_minute: int = 30, calls_per_hour: int = 500):
        self.calls_per_minute = calls_per_minute
        self.calls_per_hour = calls_per_hour
        self.minute_calls = defaultdict(list)  # user_id -> [timestamps]
        self.hour_calls = defaultdict(list)
        self.lock = Lock()
    
    def _clean_old_calls(self, calls: list, window_seconds: int) -> list:
        """Remove calls older than the window"""
        now = time.time()
        return [t for t in calls if now - t < window_seconds]
    
    def is_allowed(self, user_id: str) -> Tuple[bool, str]:
        """Check if a request is allowed for this user"""
        with self.lock:
            now = time.time()
            
            # Clean and check minute limit
            self.minute_calls[user_id] = self._clean_old_calls(
                self.minute_calls[user_id], 60
            )
            if len(self.minute_calls[user_id]) >= self.calls_per_minute:
                wait_time = 60 - (now - self.minute_calls[user_id][0])
                return False, f"Rate limit exceeded. Please wait {int(wait_time)} seconds."
            
            # Clean and check hour limit
            self.hour_calls[user_id] = self._clean_old_calls(
                self.hour_calls[user_id], 3600
            )
            if len(self.hour_calls[user_id]) >= self.calls_per_hour:
                wait_time = 3600 - (now - self.hour_calls[user_id][0])
                return False, f"Hourly limit exceeded. Please wait {int(wait_time // 60)} minutes."
            
            return True, ""
    
    def record_call(self, user_id: str):
        """Record a successful API call"""
        with self.lock:
            now = time.time()
            self.minute_calls[user_id].append(now)
            self.hour_calls[user_id].append(now)


class ConversationManager:
    """Manages conversation history and context for RJ interactions"""
    
    def __init__(self, max_history: int = 20, max_users: int = 1000):
        self.conversations = {}  # user_id -> list of messages
        self.max_history = max_history
        self.max_users = max_users
        self.user_moods = {}  # user_id -> list of detected moods
        self.lock = Lock()
    
    def add_message(self, user_id: str, role: str, content: str, mood: str = None):
        """Add a message to conversation history"""
        with self.lock:
            if user_id not in self.conversations:
                # Evict oldest user if at capacity
                if len(self.conversations) >= self.max_users:
                    oldest = min(self.conversations.keys(), 
                               key=lambda k: self.conversations[k][-1]['timestamp'] if self.conversations[k] else 0)
                    del self.conversations[oldest]
                    if oldest in self.user_moods:
                        del self.user_moods[oldest]
                
                self.conversations[user_id] = []
                self.user_moods[user_id] = []
            
            self.conversations[user_id].append({
                'role': role,
                'content': content,
                'mood': mood,
                'timestamp': datetime.now().isoformat()
            })
            
            if mood:
                self.user_moods[user_id].append(mood)
                # Keep only last 10 moods
                self.user_moods[user_id] = self.user_moods[user_id][-10:]
            
            # Trim history if too long
            if len(self.conversations[user_id]) > self.max_history:
                self.conversations[user_id] = self.conversations[user_id][-self.max_history:]
    
    def get_context(self, user_id: str, last_n: int = 5) -> List[Dict]:
        """Get recent conversation context"""
        with self.lock:
            if user_id not in self.conversations:
                return []
            return self.conversations[user_id][-last_n:]
    
    def get_dominant_mood(self, user_id: str) -> str:
        """Get the most common mood for a user"""
        with self.lock:
            if user_id not in self.user_moods or not self.user_moods[user_id]:
                return "calm"
            
            from collections import Counter
            mood_counts = Counter(self.user_moods[user_id])
            return mood_counts.most_common(1)[0][0]
    
    def should_recommend_songs(self, user_id: str) -> bool:
        """Determine if we have enough conversation to recommend songs"""
        with self.lock:
            if user_id not in self.conversations:
                return False
            
            # Recommend after 2+ exchanges OR if user explicitly asks
            user_messages = [m for m in self.conversations[user_id] if m['role'] == 'user']
            return len(user_messages) >= 2


class RJService:
    """Enhanced RJ (Radio Jockey) Service with Llama integration and rate limiting"""
    
    def __init__(self):
        # Initialize managers
        self.rate_limiter = RateLimiter(
            calls_per_minute=int(os.getenv("RJ_RATE_LIMIT_MINUTE", "20")),
            calls_per_hour=int(os.getenv("RJ_RATE_LIMIT_HOUR", "200"))
        )
        self.conversation_manager = ConversationManager()
        
        # LLM Configuration - prioritize Groq for Llama
        self.api_provider = os.getenv("LLM_API_PROVIDER", "groq").lower()
        self.groq_api_key = os.getenv("GROQ_API_KEY", "")
        self.hf_api_key = os.getenv("HUGGINGFACE_API_KEY", "")
        
        # Model selection
        self.llama_model = os.getenv("LLAMA_MODEL", "llama-3.1-8b-instant")  # Groq model
        self.hf_model = os.getenv("HF_MODEL", "meta-llama/Llama-2-7b-chat-hf")
        
        # Response cache
        self.response_cache = {}
        self.cache_max_size = 500
        
        # Import services lazily to avoid circular imports
        self._recommendation_service = None
        self._song_search_service = None
        
        logger.info(f"RJ Service initialized with provider: {self.api_provider}")
    
    @property
    def recommendation_service(self):
        if self._recommendation_service is None:
            from src.services.recommendation_service import get_recommendation_service
            self._recommendation_service = get_recommendation_service()
        return self._recommendation_service
    
    @property
    def song_search_service(self):
        if self._song_search_service is None:
            from src.services.song_search_service import get_song_search_service
            self._song_search_service = get_song_search_service()
        return self._song_search_service
    
    def chat(self, user_message: str, user_id: str) -> Dict:
        """
        Main RJ chat interface. Handles conversation, mood analysis, and song recommendations.
        
        Args:
            user_message: User's message
            user_id: User identifier
            
        Returns:
            Dictionary with RJ response, mood, and optional song recommendations
        """
        # Rate limiting check
        allowed, error_msg = self.rate_limiter.is_allowed(user_id)
        if not allowed:
            return {
                "response": f"Whoa there, listener! You're messaging faster than a drum solo! 🥁 {error_msg}",
                "mood": None,
                "songs": [],
                "rate_limited": True
            }
        
        try:
            # Record the API call
            self.rate_limiter.record_call(user_id)
            
            # Get conversation context
            context = self.conversation_manager.get_context(user_id, last_n=5)
            
            # Analyze mood using Llama
            mood, confidence = self._analyze_mood_with_llama(user_message, context)
            
            # Store user message
            self.conversation_manager.add_message(user_id, 'user', user_message, mood)
            
            # Generate RJ response
            rj_response = self._generate_rj_response(user_message, mood, context, user_id)
            
            # Store RJ response
            self.conversation_manager.add_message(user_id, 'rj', rj_response)
            
            # Determine if we should recommend songs
            songs = []
            if self._should_recommend_now(user_message, user_id):
                songs = self._get_song_recommendations(user_id, mood, user_message)
                if songs:
                    rj_response += self._format_song_intro(mood)
            
            return {
                "response": rj_response,
                "mood": mood,
                "mood_confidence": confidence,
                "songs": songs,
                "conversation_turn": len(self.conversation_manager.get_context(user_id, 100)),
                "rate_limited": False
            }
            
        except Exception as e:
            logger.error(f"RJ chat error: {e}")
            return {
                "response": "Hey there! 🎵 I'm having a little technical hiccup, but the music never stops! Tell me what kind of vibe you're feeling today?",
                "mood": "calm",
                "songs": [],
                "error": str(e),
                "rate_limited": False
            }
    
    def _analyze_mood_with_llama(self, message: str, context: List[Dict]) -> Tuple[str, float]:
        """Use Llama to analyze mood from message and context"""
        
        # Build context string
        context_str = ""
        if context:
            recent = context[-3:]
            context_str = "\n".join([
                f"{'User' if m['role'] == 'user' else 'RJ'}: {m['content']}"
                for m in recent
            ])
        
        prompt = f"""You are analyzing the emotional state of a user chatting with a radio DJ.

Previous conversation:
{context_str}

Current user message: "{message}"

Based on the message and context, identify the user's current mood.
Respond with ONLY ONE of these moods: happy, sad, angry, calm, energetic, tired, anxious, romantic, nostalgic, focused, excited, melancholic

Mood:"""
        
        try:
            if self.api_provider == "groq" and self.groq_api_key:
                mood = self._call_groq_api(prompt, max_tokens=10)
            elif self.api_provider == "huggingface" and self.hf_api_key:
                mood = self._call_hf_api(prompt, max_tokens=10)
            else:
                mood = self._fallback_mood_analysis(message)
            
            # Clean and validate mood
            mood = mood.strip().lower().split()[0] if mood else "calm"
            valid_moods = ["happy", "sad", "angry", "calm", "energetic", "tired", 
                          "anxious", "romantic", "nostalgic", "focused", "excited", "melancholic"]
            
            if mood not in valid_moods:
                mood = self._fallback_mood_analysis(message)
            
            return mood, 0.8
            
        except Exception as e:
            logger.error(f"Mood analysis error: {e}")
            return self._fallback_mood_analysis(message), 0.5
    
    def _generate_rj_response(self, user_message: str, mood: str, 
                              context: List[Dict], user_id: str) -> str:
        """Generate an RJ-style conversational response using Llama"""
        
        # Build conversation history
        conv_history = ""
        if context:
            conv_history = "\n".join([
                f"{'Listener' if m['role'] == 'user' else 'RJ'}: {m['content']}"
                for m in context[-4:]
            ])
        
        # Get dominant mood trend
        dominant_mood = self.conversation_manager.get_dominant_mood(user_id)
        
        prompt = f"""You are a warm, friendly Radio Jockey (RJ) named Aura hosting a late-night music show. You chat with listeners about their feelings, life, and music preferences before suggesting songs.

Your personality:
- Warm, empathetic, and genuinely interested in listeners
- Use casual language with occasional radio phrases like "Coming in hot!", "That's what I'm talking about!"
- Reference music and artists naturally in conversation
- Ask follow-up questions to understand the listener better
- Keep responses concise (2-3 sentences max)
- Use 1-2 emojis sparingly

Conversation so far:
{conv_history}

Listener's current mood: {mood}
Listener's overall mood trend: {dominant_mood}

Listener just said: "{user_message}"

Respond as Aura the RJ. Be conversational - don't recommend songs yet unless they explicitly ask. Focus on connecting with the listener first:"""

        try:
            if self.api_provider == "groq" and self.groq_api_key:
                response = self._call_groq_api(prompt, max_tokens=150)
            elif self.api_provider == "huggingface" and self.hf_api_key:
                response = self._call_hf_api(prompt, max_tokens=150)
            else:
                response = self._get_fallback_response(mood)
            
            # Clean up response
            if response:
                response = response.strip()
                # Remove any "RJ:" or "Aura:" prefixes
                response = re.sub(r'^(RJ|Aura|Radio Jockey)[:\s]+', '', response, flags=re.IGNORECASE)
                response = response.split('\n')[0]  # Take first paragraph only
                
                if len(response) > 10:
                    return response[:500]  # Limit length
            
            return self._get_fallback_response(mood)
            
        except Exception as e:
            logger.error(f"Response generation error: {e}")
            return self._get_fallback_response(mood)
    
    def _call_groq_api(self, prompt: str, max_tokens: int = 100) -> Optional[str]:
        """Call Groq API for Llama inference"""
        try:
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.groq_api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.llama_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                    "temperature": 0.7
                },
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                return result["choices"][0]["message"]["content"]
            elif response.status_code == 429:
                logger.warning("Groq rate limit hit")
                return None
            else:
                logger.warning(f"Groq API error: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"Groq API error: {e}")
            return None
    
    def _call_hf_api(self, prompt: str, max_tokens: int = 100) -> Optional[str]:
        """Call Hugging Face API for Llama inference"""
        try:
            response = requests.post(
                f"https://api-inference.huggingface.co/models/{self.hf_model}",
                headers={"Authorization": f"Bearer {self.hf_api_key}"},
                json={
                    "inputs": prompt,
                    "parameters": {
                        "max_new_tokens": max_tokens,
                        "temperature": 0.7,
                        "return_full_text": False
                    }
                },
                timeout=15
            )
            
            if response.status_code == 200:
                result = response.json()
                if isinstance(result, list) and len(result) > 0:
                    return result[0].get("generated_text", "")
            
            return None
            
        except Exception as e:
            logger.error(f"HF API error: {e}")
            return None
    
    def _should_recommend_now(self, message: str, user_id: str) -> bool:
        """Determine if we should recommend songs now"""
        message_lower = message.lower()
        
        # Explicit song request triggers
        song_triggers = [
            "play", "song", "music", "recommend", "suggest", "listen",
            "what should i", "any song", "play something", "put on",
            "need music", "want music", "give me", "play me"
        ]
        
        if any(trigger in message_lower for trigger in song_triggers):
            return True
        
        # Also recommend after enough conversation
        return self.conversation_manager.should_recommend_songs(user_id)
    
    def _get_song_recommendations(self, user_id: str, mood: str, 
                                   message: str) -> List[Dict]:
        """Get personalized song recommendations"""
        try:
            recommendations = []
            
            # Extract any genre hints from message
            genre_hints = self._extract_genre_hints(message)
            
            # Try recommendation service first
            try:
                recs = self.recommendation_service.get_recommendations(
                    user_id=user_id,
                    limit=5,
                    mood=mood,
                    genre=genre_hints if genre_hints else None
                )
                recommendations.extend(recs)
            except Exception as e:
                logger.debug(f"Recommendation service error: {e}")
            
            # Also try mood-based search
            if len(recommendations) < 3:
                mood_query = self._get_mood_search_query(mood)
                try:
                    songs = self.song_search_service.search_songs(mood_query, limit=3)
                    recommendations.extend(songs)
                except Exception as e:
                    logger.debug(f"Song search error: {e}")
            
            # Deduplicate
            seen = set()
            unique = []
            for song in recommendations:
                title = song.get("title", "") or song.get("song", {}).get("title", "")
                if title.lower() not in seen:
                    seen.add(title.lower())
                    unique.append(song)
            
            return unique[:5]
            
        except Exception as e:
            logger.error(f"Song recommendation error: {e}")
            return []
    
    def _extract_genre_hints(self, message: str) -> List[str]:
        """Extract genre hints from user message"""
        message_lower = message.lower()
        
        genre_keywords = {
            "rock": ["rock", "guitar", "metal", "punk"],
            "pop": ["pop", "catchy", "mainstream", "top 40"],
            "hip hop": ["hip hop", "rap", "hiphop", "beats"],
            "electronic": ["electronic", "edm", "techno", "house", "trance"],
            "r&b": ["r&b", "rnb", "soul", "neo-soul"],
            "jazz": ["jazz", "smooth", "saxophone"],
            "classical": ["classical", "orchestra", "symphony", "piano"],
            "country": ["country", "folk", "acoustic"],
            "indie": ["indie", "alternative", "underground"],
            "bollywood": ["bollywood", "hindi", "indian"]
        }
        
        detected = []
        for genre, keywords in genre_keywords.items():
            if any(kw in message_lower for kw in keywords):
                detected.append(genre)
        
        return detected
    
    def _get_mood_search_query(self, mood: str) -> str:
        """Convert mood to a search query"""
        mood_queries = {
            "happy": "upbeat happy feel good",
            "sad": "emotional sad melancholic",
            "angry": "intense aggressive rock",
            "calm": "calm peaceful ambient",
            "energetic": "energetic workout pump",
            "tired": "soothing gentle sleep",
            "anxious": "calming meditation peaceful",
            "romantic": "romantic love ballad",
            "nostalgic": "classic throwback oldies",
            "focused": "lo-fi study instrumental",
            "excited": "party dance energetic",
            "melancholic": "sad emotional piano"
        }
        return mood_queries.get(mood, mood)
    
    def _format_song_intro(self, mood: str) -> str:
        """Add a song introduction to the response"""
        intros = {
            "happy": " I've got some feel-good tracks that'll keep that smile going! 🎵",
            "sad": " Let me play something that understands exactly how you're feeling... 💙",
            "energetic": " Time to turn it UP! Here's some high-energy tracks for you! 🔥",
            "calm": " I've got some peaceful vibes coming your way... 🌙",
            "romantic": " Aww, here's some songs to match that loving feeling! 💕",
            "nostalgic": " Let's take a trip down memory lane with these classics! ✨",
            "focused": " Here's some instrumental tracks to help you stay in the zone! 🎧"
        }
        return intros.get(mood, " Here's what I've got for you! 🎶")
    
    def _fallback_mood_analysis(self, message: str) -> str:
        """Rule-based fallback for mood analysis"""
        message_lower = message.lower()
        
        mood_keywords = {
            "happy": ["happy", "great", "awesome", "excited", "amazing", "good", "love"],
            "sad": ["sad", "depressed", "down", "upset", "lonely", "hurt"],
            "angry": ["angry", "mad", "furious", "annoyed", "frustrated"],
            "calm": ["calm", "peaceful", "relaxed", "chill"],
            "energetic": ["pumped", "workout", "gym", "running", "energy"],
            "tired": ["tired", "exhausted", "sleepy", "drained"],
            "anxious": ["anxious", "worried", "stressed", "nervous"],
            "romantic": ["romantic", "love", "dating", "crush"],
            "nostalgic": ["remember", "memories", "past", "childhood"]
        }
        
        for mood, keywords in mood_keywords.items():
            if any(kw in message_lower for kw in keywords):
                return mood
        
        return "calm"
    
    def _get_fallback_response(self, mood: str) -> str:
        """Get a fallback response when API fails"""
        import random
        
        responses = {
            "happy": [
                "That's amazing! I love that energy! 🌟 What's got you feeling so good today?",
                "YES! That positive vibe is contagious! Tell me more!"
            ],
            "sad": [
                "I hear you, and I'm here for you. 💙 Music can really help at times like these...",
                "It's okay to feel this way. Sometimes the best songs come from these moments."
            ],
            "calm": [
                "That's a nice peaceful energy you've got going. What's on your mind?",
                "I'm vibing with that chill mood! 🌙 Perfect for some smooth tunes."
            ],
            "energetic": [
                "I can feel that energy through the airwaves! 🔥 Ready to turn it up?",
                "That's what I'm talking about! Let's match that fire!"
            ]
        }
        
        mood_responses = responses.get(mood, responses["calm"])
        return random.choice(mood_responses)
    
    def get_conversation_history(self, user_id: str, limit: int = 10) -> List[Dict]:
        """Get conversation history for a user"""
        return self.conversation_manager.get_context(user_id, limit)
    
    def clear_conversation(self, user_id: str):
        """Clear conversation history for a user"""
        with self.conversation_manager.lock:
            if user_id in self.conversation_manager.conversations:
                del self.conversation_manager.conversations[user_id]
            if user_id in self.conversation_manager.user_moods:
                del self.conversation_manager.user_moods[user_id]


# Singleton instance
_rj_service = None

def get_rj_service() -> RJService:
    """Get singleton instance of RJService"""
    global _rj_service
    if _rj_service is None:
        _rj_service = RJService()
    return _rj_service
