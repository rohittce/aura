"""
LLM Analysis Service
Uses language models to analyze music taste and generate insights
"""

from typing import List, Dict, Optional
import json


class LLMAnalysisService:
    """Service for analyzing songs using language models"""
    
    def __init__(self):
        # For now, we'll use rule-based analysis
        # Can be extended with actual LLM integration later
        pass
    
    def analyze_songs(self, seed_songs: List[Dict], listened_songs: List[Dict] = None) -> Dict:
        """
        Analyze songs to extract taste patterns.
        
        Args:
            seed_songs: List of seed songs
            listened_songs: Optional list of songs user listened to
            
        Returns:
            Analysis result with insights
        """
        all_songs = seed_songs.copy()
        if listened_songs:
            all_songs.extend(listened_songs)
        
        # Extract patterns
        artists = {}
        genres = {}
        moods = []
        
        for song in all_songs:
            # Count artists
            for artist in song.get('artists', []):
                artists[artist] = artists.get(artist, 0) + 1
            
            # Count genres
            for genre in song.get('genre', []):
                genres[genre] = genres.get(genre, 0) + 1
        
        # Determine dominant patterns
        top_artists = sorted(artists.items(), key=lambda x: x[1], reverse=True)[:5]
        top_genres = sorted(genres.items(), key=lambda x: x[1], reverse=True)[:5]
        
        # Generate insights
        insights = []
        if top_artists:
            insights.append(f"You frequently listen to {top_artists[0][0]} and similar artists")
        if top_genres:
            insights.append(f"Your taste leans towards {top_genres[0][0]} music")
        if len(all_songs) > 10:
            insights.append("You have a diverse music taste with many different styles")
        
        # Create analysis result
        analysis = {
            "status": "complete",
            "total_songs_analyzed": len(all_songs),
            "seed_songs_count": len(seed_songs),
            "listened_songs_count": len(listened_songs) if listened_songs else 0,
            "top_artists": [{"artist": a, "count": c} for a, c in top_artists],
            "top_genres": [{"genre": g, "count": c} for g, c in top_genres],
            "insights": insights,
            "taste_profile": {
                "diversity_score": min(len(set([s.get('artists', [''])[0] for s in all_songs if s.get('artists')])), 10) / 10.0,
                "genre_diversity": min(len(set([g for s in all_songs for g in s.get('genre', [])])), 10) / 10.0
            }
        }
        
        return analysis
    
    def generate_recommendation_explanation(self, song: Dict, user_taste: Dict) -> str:
        """
        Generate explanation for why a song was recommended.
        
        Args:
            song: Song being recommended
            user_taste: User's taste profile
            
        Returns:
            Human-readable explanation
        """
        explanations = []
        
        # Check artist match
        song_artists = song.get('artists', [])
        top_artists = [a['artist'] for a in user_taste.get('top_artists', [])]
        
        for artist in song_artists:
            if artist in top_artists:
                explanations.append(f"Similar to {artist} who you frequently listen to")
                break
        
        # Check genre match
        song_genres = song.get('genre', [])
        top_genres = [g['genre'] for g in user_taste.get('top_genres', [])]
        
        for genre in song_genres:
            if genre in top_genres:
                explanations.append(f"Matches your preference for {genre} music")
                break
        
        if not explanations:
            explanations.append("Based on your overall music taste profile")
        
        return " • ".join(explanations[:2])  # Return top 2 explanations


# Singleton instance
_llm_analysis_service = None

def get_llm_analysis_service() -> LLMAnalysisService:
    """Get singleton instance of LLMAnalysisService"""
    global _llm_analysis_service
    if _llm_analysis_service is None:
        _llm_analysis_service = LLMAnalysisService()
    return _llm_analysis_service

