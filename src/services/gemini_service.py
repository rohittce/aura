"""
Gemini Service
Uses Google Gemini AI to improve song search accuracy and generate better YouTube search queries
"""

import os
import logging
from typing import Optional, List, Dict
import google.generativeai as genai

logger = logging.getLogger(__name__)


class GeminiService:
    """Service for using Gemini AI to improve song search"""
    
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY", "")
        self.model_name = os.getenv("GEMINI_MODEL", "gemini-pro")
        self.enabled = bool(self.api_key)
        
        if self.enabled:
            try:
                genai.configure(api_key=self.api_key)
                self.model = genai.GenerativeModel(self.model_name)
                logger.info(f"Gemini service initialized with model: {self.model_name}")
            except Exception as e:
                logger.error(f"Failed to initialize Gemini: {e}")
                self.enabled = False
        else:
            logger.warning("Gemini API key not found. Gemini features disabled.")
            self.model = None
    
    def generate_search_query(self, song_title: str, artists: List[str]) -> Optional[str]:
        """
        Use Gemini to generate an optimized YouTube search query for a song.
        
        Args:
            song_title: Song title
            artists: List of artist names
            
        Returns:
            Optimized search query string or None if Gemini is unavailable
        """
        if not self.enabled or not self.model:
            # Fallback to simple query
            artist_str = " ".join(artists[:2]) if artists else ""
            return f"{song_title} {artist_str} official audio".strip()
        
        try:
            artist_str = ", ".join(artists[:3]) if artists else "Unknown Artist"
            
            prompt = f"""Generate the best YouTube search query to find the official audio/video for this song:
Song Title: {song_title}
Artists: {artist_str}

Requirements:
- Prioritize official audio or official music video
- Include artist name(s) and song title
- Use common search terms that work well on YouTube
- Keep it concise (max 10 words)
- Return ONLY the search query, nothing else

Search Query:"""
            
            response = self.model.generate_content(prompt)
            query = response.text.strip()
            
            # Clean up the response (remove quotes if present)
            query = query.strip('"\'')
            
            logger.info(f"Gemini generated search query: {query} for {song_title} by {artists}")
            return query
            
        except Exception as e:
            logger.error(f"Gemini search query generation error: {e}")
            # Fallback to simple query
            artist_str = " ".join(artists[:2]) if artists else ""
            return f"{song_title} {artist_str} official audio".strip()
    
    def validate_video_result(self, video_id: str, song_title: str, artists: List[str]) -> bool:
        """
        Use Gemini to validate if a YouTube video ID matches the requested song.
        This helps filter out incorrect or random results.
        
        Args:
            video_id: YouTube video ID to validate
            artists: List of artist names
            
        Returns:
            True if video likely matches the song, False otherwise
        """
        if not self.enabled or not self.model:
            # If Gemini is unavailable, assume valid (fallback behavior)
            return True
        
        try:
            artist_str = ", ".join(artists[:3]) if artists else "Unknown Artist"
            
            prompt = f"""I'm searching for this song on YouTube:
Song Title: {song_title}
Artists: {artist_str}

I found a video with ID: {video_id}

Based on typical YouTube video IDs and search patterns, does this video ID format look valid for finding this song?
- Valid YouTube video IDs are 11 characters long, alphanumeric with hyphens/underscores
- Consider if the video ID format matches YouTube's standard format

Respond with only "YES" or "NO" and a brief reason (one sentence).

Response:"""
            
            response = self.model.generate_content(prompt)
            response_text = response.text.strip().upper()
            
            # Check if response indicates valid
            is_valid = "YES" in response_text or "valid" in response_text.lower()
            
            logger.info(f"Gemini validation for {video_id}: {is_valid} ({response_text[:50]})")
            return is_valid
            
        except Exception as e:
            logger.error(f"Gemini validation error: {e}")
            # On error, assume valid to not block legitimate results
            return True
    
    def suggest_alternative_queries(self, song_title: str, artists: List[str], failed_attempts: int = 0) -> List[str]:
        """
        Use Gemini to suggest alternative search queries if initial search fails.
        
        Args:
            song_title: Song title
            artists: List of artist names
            failed_attempts: Number of failed search attempts
            
        Returns:
            List of alternative search query strings
        """
        if not self.enabled or not self.model:
            # Fallback queries
            artist_str = " ".join(artists[:2]) if artists else ""
            return [
                f"{song_title} {artist_str}",
                f"{song_title} music",
                f"{song_title} audio"
            ]
        
        try:
            artist_str = ", ".join(artists[:3]) if artists else "Unknown Artist"
            
            prompt = f"""I'm trying to find this song on YouTube but my search failed {failed_attempts} time(s):
Song Title: {song_title}
Artists: {artist_str}

Generate 3 alternative YouTube search queries that might work better.
Each query should be different and try different approaches:
1. One with "official" keyword
2. One with just title and artist
3. One with "music" or "audio" keyword

Return only the 3 queries, one per line, no numbering or bullets.

Queries:"""
            
            response = self.model.generate_content(prompt)
            queries = [q.strip().strip('"\'') for q in response.text.strip().split('\n') if q.strip()]
            
            # Filter out empty queries and limit to 3
            queries = [q for q in queries if q][:3]
            
            # Add fallbacks if Gemini didn't return enough
            if len(queries) < 3:
                artist_str = " ".join(artists[:2]) if artists else ""
                fallbacks = [
                    f"{song_title} {artist_str}",
                    f"{song_title} music",
                    f"{song_title} audio"
                ]
                queries.extend(fallbacks)
                queries = queries[:3]
            
            logger.info(f"Gemini suggested {len(queries)} alternative queries for {song_title}")
            return queries
            
        except Exception as e:
            logger.error(f"Gemini alternative query generation error: {e}")
            # Fallback queries
            artist_str = " ".join(artists[:2]) if artists else ""
            return [
                f"{song_title} {artist_str}",
                f"{song_title} music",
                f"{song_title} audio"
            ]


# Singleton instance
_gemini_service = None

def get_gemini_service() -> GeminiService:
    """Get singleton instance of GeminiService"""
    global _gemini_service
    if _gemini_service is None:
        _gemini_service = GeminiService()
    return _gemini_service

