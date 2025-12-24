"""
Cat Intelligence Service
Uses LLM to give the cat personality and emotional reactions to songs
"""

from typing import Dict, Optional, Tuple
import logging
import os
import requests
import json

from src.services.llm_sentiment_service import get_llm_sentiment_service

logger = logging.getLogger(__name__)


class CatIntelligenceService:
    """Service for cat's intelligent reactions to music"""
    
    def __init__(self):
        self.llm_sentiment = get_llm_sentiment_service()
        self.api_provider = os.getenv("LLM_API_PROVIDER", "huggingface").lower()
        self.hf_api_key = os.getenv("HUGGINGFACE_API_KEY", "")
        self.hf_model = os.getenv("HF_MODEL", "TinyLlama/TinyLlama-1.1B-Chat-v1.0")
        self.use_online_api = os.getenv("USE_ONLINE_LLM", "true").lower() == "true"
    
    def analyze_song_for_cat(self, song_title: str, artists: list, genre: list = None) -> Dict:
        """
        Analyze a song and generate cat's emotional reaction.
        
        Args:
            song_title: Song title
            artists: List of artists
            genre: List of genres
            
        Returns:
            Dictionary with emotion, comment, and reaction
        """
        try:
            # Build prompt for cat's reaction
            artist_str = ", ".join(artists[:2]) if artists else "Unknown Artist"
            genre_str = ", ".join(genre[:2]) if genre else "Unknown Genre"
            
            prompt = f"""You are a cute, intelligent cat who loves music. Analyze this song and react emotionally:

Song: "{song_title}" by {artist_str}
Genre: {genre_str}

React as a cat would - be playful, emotional, and expressive. Determine:
1. Your emotional reaction (happy, sad, excited, calm, energetic, depressed, nostalgic, etc.)
2. A short comment (1-2 sentences, max 50 words) in cat language (use "meow", "purr", etc. but be intelligent)
3. Your mood level (0.0 to 1.0, where 0.0 is very sad/depressed, 1.0 is very happy/excited)

Respond in JSON format:
{{
    "emotion": "happy|sad|excited|calm|energetic|depressed|nostalgic|romantic|angry|peaceful",
    "comment": "Your cat comment here",
    "mood_score": 0.75,
    "reaction": "dancing|sleeping|rolling|purring|meowing"
}}"""

            if self.use_online_api and self.api_provider == "huggingface" and self.hf_api_key:
                result = self._analyze_with_hf_api(prompt, song_title, artists, genre)
                if result:
                    return result
                # If LLM failed, fall through to rule-based
            
            # Fallback to rule-based analysis
            return self._analyze_song_rules(song_title, artists, genre)
            
        except Exception as e:
            logger.error(f"Error analyzing song for cat: {e}")
            # Fallback to rule-based
            return self._analyze_song_rules(song_title, artists, genre)
    
    def _analyze_with_hf_api(self, prompt: str, song_title: str, artists: list, genre: list) -> Dict:
        """Analyze using Hugging Face API"""
        try:
            url = f"https://api-inference.huggingface.co/models/{self.hf_model}"
            headers = {
                "Authorization": f"Bearer {self.hf_api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "inputs": prompt,
                "parameters": {
                    "max_new_tokens": 150,
                    "temperature": 0.7,
                    "return_full_text": False
                }
            }
            
            response = requests.post(url, headers=headers, json=payload, timeout=10)
            
            if response.status_code == 200:
                result = response.json()
                if isinstance(result, list) and len(result) > 0:
                    generated_text = result[0].get("generated_text", "")
                    # Try to extract JSON from response
                    parsed = self._parse_llm_response(generated_text)
                    if parsed and parsed.get("emotion"):
                        return parsed
            
            # If API fails, fallback to rule-based
            logger.debug("HF API failed or returned invalid response, using rule-based analysis")
            return self._analyze_song_rules(song_title, artists, genre)
            
        except Exception as e:
            logger.error(f"HF API error: {e}")
            return self._analyze_song_rules(song_title, artists, genre)
    
    def _parse_llm_response(self, text: str) -> Dict:
        """Parse LLM response and extract JSON"""
        try:
            # Try to find JSON in the response
            import re
            json_match = re.search(r'\{[^{}]*"emotion"[^{}]*\}', text, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                result = json.loads(json_str)
                
                # Validate and normalize
                emotion = result.get("emotion", "happy").lower()
                comment = result.get("comment", "Meow! This song is interesting!")
                mood_score = float(result.get("mood_score", 0.5))
                reaction = result.get("reaction", "dancing")
                
                return {
                    "emotion": emotion,
                    "comment": comment[:100],  # Limit length
                    "mood_score": max(0.0, min(1.0, mood_score)),
                    "reaction": reaction
                }
        except Exception as e:
            logger.debug(f"Could not parse LLM response: {e}")
        
        # Return None to trigger fallback in caller
        return None
    
    def _analyze_song_rules(self, song_title: str, artists: list, genre: list) -> Dict:
        """Rule-based fallback analysis with intelligent keyword matching"""
        title_lower = song_title.lower()
        artist_str = " ".join(artists).lower() if artists else ""
        genre_str = " ".join(genre).lower() if genre else ""
        
        # Analyze keywords for emotion
        happy_keywords = ["happy", "joy", "celebrate", "party", "dance", "upbeat", "cheerful", "sunny", "smile", "laugh"]
        sad_keywords = ["sad", "cry", "tears", "lonely", "heartbreak", "melancholy", "blue", "pain", "hurt", "miss"]
        depressed_keywords = ["depressed", "suicide", "death", "die", "end", "dark", "black", "void", "empty", "numb", "hopeless"]
        energetic_keywords = ["energy", "pump", "workout", "intense", "power", "strong", "fire", "wild", "crazy", "explosive"]
        calm_keywords = ["calm", "peace", "relax", "zen", "meditation", "soft", "gentle", "quiet", "serene", "tranquil"]
        romantic_keywords = ["love", "romantic", "heart", "kiss", "together", "forever", "sweet", "darling", "beloved"]
        
        emotion = "happy"
        mood_score = 0.6
        comment = "Meow! This song is interesting! 🎵"
        reaction = "dancing"
        
        # Check for emotional keywords
        text_to_check = f"{title_lower} {artist_str} {genre_str}"
        
        # Check for depressed keywords first (most negative)
        if any(kw in text_to_check for kw in depressed_keywords):
            emotion = "depressed"
            mood_score = 0.1
            comment = "Meow... this song is so dark and sad. I feel depressed listening to this. *lies down* 😿"
            reaction = "sleeping"
        elif any(kw in text_to_check for kw in sad_keywords):
            emotion = "sad"
            mood_score = 0.25
            comment = "Meow... this song makes me feel sad. *sniffles* I need a hug. 😢"
            reaction = "sleeping"
        elif any(kw in text_to_check for kw in happy_keywords):
            emotion = "happy"
            mood_score = 0.85
            comment = "Purr purr! This makes me so happy! I want to dance and roll around! 🎉✨"
            reaction = "dancing"
        elif any(kw in text_to_check for kw in energetic_keywords):
            emotion = "excited"
            mood_score = 0.9
            comment = "MEOW MEOW! This is SO energetic! I'm rolling around with excitement! ⚡🔥"
            reaction = "rolling"
        elif any(kw in text_to_check for kw in calm_keywords):
            emotion = "calm"
            mood_score = 0.6
            comment = "Purr... so peaceful and calming. I feel so relaxed. This is nice. 😌🕊️"
            reaction = "sleeping"
        elif any(kw in text_to_check for kw in romantic_keywords):
            emotion = "happy"
            mood_score = 0.75
            comment = "Aww meow! This is so romantic and sweet! My heart is purring with love! 💕💜"
            reaction = "purring"
        
        # Genre-based reactions (override if genre is strong indicator)
        if "devotional" in genre_str or "spiritual" in genre_str or "bhajan" in genre_str or "bhakti" in genre_str:
            emotion = "calm"
            mood_score = 0.65
            comment = "Meow... this spiritual music brings me inner peace. So calming and beautiful! 🕊️🙏"
            reaction = "sleeping"
        elif "rock" in genre_str or "metal" in genre_str or "punk" in genre_str:
            emotion = "excited"
            mood_score = 0.9
            comment = "MEOW! This rock/metal is so intense! I'm headbanging and rolling! 🤘🔥"
            reaction = "rolling"
        elif "jazz" in genre_str or "blues" in genre_str:
            emotion = "calm"
            mood_score = 0.6
            comment = "Purr... smooth and sophisticated. I like this jazzy vibe! Very classy! 🎷✨"
            reaction = "purring"
        elif "pop" in genre_str:
            emotion = "happy"
            mood_score = 0.75
            comment = "Meow! This pop song is catchy! I'm dancing to the beat! 🎵💃"
            reaction = "dancing"
        elif "classical" in genre_str or "orchestral" in genre_str:
            emotion = "calm"
            mood_score = 0.55
            comment = "Purr... such beautiful classical music. So elegant and peaceful. 🎼"
            reaction = "sleeping"
        
        return {
            "emotion": emotion,
            "comment": comment,
            "mood_score": mood_score,
            "reaction": reaction
        }
    
    def get_cat_reaction_to_song(self, song: Dict) -> Dict:
        """
        Get cat's reaction to a song.
        
        Args:
            song: Song dictionary with title, artists, genre
            
        Returns:
            Reaction dictionary
        """
        title = song.get("title", "") or song.get("song", {}).get("title", "")
        artists = song.get("artists", []) or song.get("song", {}).get("artists", [])
        genre = song.get("genre", []) or song.get("song", {}).get("genre", [])
        
        return self.analyze_song_for_cat(title, artists, genre)


# Singleton instance
_cat_intelligence_service = None

def get_cat_intelligence_service() -> CatIntelligenceService:
    """Get singleton instance of CatIntelligenceService"""
    global _cat_intelligence_service
    if _cat_intelligence_service is None:
        _cat_intelligence_service = CatIntelligenceService()
    return _cat_intelligence_service

