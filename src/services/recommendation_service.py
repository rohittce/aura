"""
Recommendation Service
Generates music recommendations based on user taste profile
"""

import numpy as np
from typing import List, Dict, Optional
from src.services.embedding_service import EmbeddingService
from src.services.song_search_service import get_song_search_service
from src.services.taste_profile_service import get_taste_profile_service
import logging

logger = logging.getLogger(__name__)


class RecommendationService:
    """Service for generating music recommendations"""
    
    def __init__(self):
        self.embedding_service = EmbeddingService()
        self.song_search_service = get_song_search_service()
        self.taste_profile_service = get_taste_profile_service()
        # Cache for in-memory profiles (loaded from DB)
        self.user_profiles = {}
    
    def analyze_taste(self, user_id: str, seed_songs: List[Dict]) -> Dict:
        """
        Analyze user taste from seed songs.
        
        Args:
            user_id: User identifier
            seed_songs: List of seed songs with title, artists, genre
            
        Returns:
            Taste profile dictionary
        """
        if not seed_songs:
            return {
                "user_id": user_id,
                "status": "error",
                "message": "No seed songs provided"
            }
        
        # Generate embeddings for seed songs
        embeddings = self.embedding_service.embed_songs_batch(seed_songs)
        
        # Compute average embedding (simple taste vector)
        if embeddings:
            avg_embedding = np.mean([emb[0] for emb in embeddings], axis=0)
        else:
            avg_embedding = np.zeros(self.embedding_service.embedding_dim)
        
        # Store profile
        profile = {
            "user_id": user_id,
            "seed_songs": seed_songs,
            "taste_vector": avg_embedding.tolist(),
            "song_count": len(seed_songs),
            "status": "complete"
        }
        
        # Save to database
        self.taste_profile_service.save_profile(user_id, profile)
        
        # Cache in memory
        self.user_profiles[user_id] = profile
        
        logger.info(f"Created/updated taste profile for user {user_id} with {len(seed_songs)} songs")
        
        return profile
    
    def get_recommendations(
        self,
        user_id: str,
        limit: int = 10,
        context: Optional[Dict] = None,
        genre: Optional[List[str]] = None
    ) -> List[Dict]:
        """
        Get recommendations for a user based on taste profile.
        
        Args:
            user_id: User identifier
            limit: Number of recommendations
            context: Optional context dict
            genre: Optional genre filter
            
        Returns:
            List of recommended songs
        """
        # Load profile from database if not in cache
        if user_id not in self.user_profiles:
            profile_data = self.taste_profile_service.load_profile(user_id)
            if profile_data:
                self.user_profiles[user_id] = profile_data
            else:
                return []
        
        profile = self.user_profiles[user_id]
        taste_vector = np.array(profile["taste_vector"])
        
        # Get seed songs to find similar ones
        seed_songs = profile["seed_songs"]
        if not seed_songs:
            return []
        
        # Strategy: Search for songs similar to seed songs
        # Use multiple search strategies to get diverse recommendations
        all_candidates = []
        seen_titles = set()
        
        # Strategy 1: Search by artist (get more songs from same artists)
        for seed_song in seed_songs[:5]:  # Use up to 5 seed songs
            if seed_song.get('artists'):
                artist = seed_song['artists'][0]
                try:
                    results = self.song_search_service.search_songs(artist, limit=15)
                    for song in results:
                        title_key = (song['title'].lower(), song['artists'][0].lower() if song.get('artists') else '')
                        if title_key not in seen_titles:
                            is_seed = any(
                                s['title'].lower() == song['title'].lower() and
                                (s.get('artists', [''])[0].lower() == song.get('artists', [''])[0].lower() if song.get('artists') else False)
                                for s in seed_songs
                            )
                            if not is_seed:
                                all_candidates.append(song)
                                seen_titles.add(title_key)
                except Exception as e:
                    print(f"Error searching by artist: {e}")
                    continue
        
        # Strategy 2: Search by song title (get similar songs)
        for seed_song in seed_songs[:3]:
            query = f"{seed_song['title']}"
            try:
                results = self.song_search_service.search_songs(query, limit=10)
                for song in results:
                    title_key = (song['title'].lower(), song['artists'][0].lower() if song.get('artists') else '')
                    if title_key not in seen_titles:
                        is_seed = any(
                            s['title'].lower() == song['title'].lower() and
                            (s.get('artists', [''])[0].lower() == song.get('artists', [''])[0].lower() if song.get('artists') else False)
                            for s in seed_songs
                        )
                        if not is_seed:
                            all_candidates.append(song)
                            seen_titles.add(title_key)
            except Exception as e:
                print(f"Error searching by title: {e}")
                continue
        
        # Priority: If genre is explicitly provided, search by that genre first
        if genre and len(genre) > 0:
            # Search by provided genre(s) first - this takes priority
            for genre_name in genre[:3]:  # Use up to 3 genres
                try:
                    results = self.song_search_service.search_songs(genre_name, limit=20)
                    for song in results:
                        title_key = (song['title'].lower(), song['artists'][0].lower() if song.get('artists') else '')
                        if title_key not in seen_titles and len(all_candidates) < limit * 3:
                            is_seed = any(
                                s['title'].lower() == song['title'].lower() and
                                (s.get('artists', [''])[0].lower() == song.get('artists', [''])[0].lower() if song.get('artists') else False)
                                for s in seed_songs
                            )
                            if not is_seed:
                                all_candidates.append(song)
                                seen_titles.add(title_key)
                except Exception as e:
                    print(f"Error searching by provided genre: {e}")
                    continue
        
        # If we still don't have enough, search by genre from seed songs
        if len(all_candidates) < limit:
            genres = set()
            # Add provided genres if any
            if genre:
                genres.update(genre)
            # Add genres from seed songs
            for seed_song in seed_songs:
                if seed_song.get('genre'):
                    genres.update(seed_song['genre'])
            
            for genre_name in list(genres)[:2]:  # Use up to 2 genres
                try:
                    results = self.song_search_service.search_songs(genre_name, limit=10)
                    for song in results:
                        title_key = (song['title'].lower(), song['artists'][0].lower() if song.get('artists') else '')
                        if title_key not in seen_titles and len(all_candidates) < limit * 3:
                            is_seed = any(
                                s['title'].lower() == song['title'].lower() and
                                (s.get('artists', [''])[0].lower() == song.get('artists', [''])[0].lower() if song.get('artists') else False)
                                for s in seed_songs
                            )
                            if not is_seed:
                                all_candidates.append(song)
                                seen_titles.add(title_key)
                except Exception as e:
                    print(f"Error searching by genre: {e}")
                    continue
        
        # Use taste vector directly (no mood adjustment)
        adjusted_taste_vector = taste_vector
        
        # Get user feedback data for re-ranking
        feedback_scores = self._get_feedback_scores(user_id)
        
        # Score candidates with improved weighted scoring
        scored_candidates = []
        for candidate in all_candidates:
            try:
                # Generate embedding for candidate
                emb, _ = self.embedding_service.embed_song(
                    candidate['title'],
                    candidate.get('artists', ['Unknown']),
                    candidate.get('genre', [])
                )
                
                # Compute similarity to taste vector
                similarity = self.embedding_service.cosine_similarity(adjusted_taste_vector, emb)
                
                # Compute genre match score
                genre_match = 0.0
                if genre and candidate.get('genre'):
                    candidate_genres = [g.lower() for g in candidate.get('genre', [])]
                    provided_genres = [g.lower() for g in genre]
                    # Check if any provided genre matches candidate genre
                    if any(prov_genre in ' '.join(candidate_genres) or any(prov_genre in cg for cg in candidate_genres) for prov_genre in provided_genres):
                        genre_match = 1.0
                
                # Weighted combination: similarity (90%) + genre match (10%)
                final_score = (
                    0.9 * float(similarity) +
                    0.1 * float(genre_match)
                )
                
                # Light audio feature re-ranking (no mood dependency)
                audio_boost = self._compute_audio_feature_boost(candidate, None)
                final_score = final_score * (1.0 + audio_boost * 0.1)  # Max 10% boost
                
                # IMPROVEMENT 5: Feedback-aware re-ranking
                candidate_key = (candidate.get('title', '').lower(), 
                               candidate.get('artists', [''])[0].lower() if candidate.get('artists') else '')
                feedback_score = feedback_scores.get(candidate_key, 0.0)
                # Apply feedback: likes boost, skips penalize
                if feedback_score > 0:
                    final_score *= (1.0 + feedback_score * 0.15)  # Up to 15% boost for liked songs
                elif feedback_score < 0:
                    final_score *= (1.0 + feedback_score * 0.2)  # Up to 20% penalty for skipped songs
                
                # Cap final score at 1.0
                final_score = min(float(final_score), 1.0)
                
                # Build explanation
                explanation = f"Similar to your taste ({(similarity * 100):.0f}% match)"
                if genre and genre_match > 0:
                    explanation += f" • Same genre: {', '.join(genre[:2])}"
                
                scored_candidates.append({
                    **candidate,
                    'similarity_score': final_score,
                    'base_similarity': float(similarity),
                    'genre_match': float(genre_match),
                    'explanation': explanation
                })
            except Exception as e:
                logger.debug(f"Error scoring candidate: {e}")
                continue
        
        # Sort by similarity and return top results
        scored_candidates.sort(key=lambda x: x['similarity_score'], reverse=True)
        
        # IMPROVEMENT 3: Apply diversity constraints
        diverse_candidates = self._apply_diversity_constraints(
            scored_candidates, 
            limit=limit * 2  # Get more candidates for diversity filtering
        )
        
        # Format recommendations for frontend
        # Note: YouTube video ID search is done asynchronously to avoid blocking
        recommendations = []
        for i, rec in enumerate(diverse_candidates[:limit]):
            # Generate platform links
            from urllib.parse import quote
            song_query = f"{rec['title']} {rec.get('artists', [''])[0]}"
            spotify_link = f"https://open.spotify.com/search/{quote(song_query)}"
            youtube_link = f"https://music.youtube.com/search?q={quote(song_query)}"
            
            # Try to get YouTube video ID (non-blocking, can be None)
            video_id = None
            try:
                from src.services.youtube_service import get_youtube_service
                youtube_service = get_youtube_service()
                video_id = youtube_service.search_video_id(
                    rec['title'],
                    rec.get('artists', ['Unknown Artist'])
                )
            except Exception as e:
                print(f"Could not get YouTube ID for {rec['title']}: {e}")
                # Continue without video ID - can be fetched later
            
            recommendations.append({
                'recommendation_id': f"rec_{user_id}_{i}",
                'song': {
                    'title': rec['title'],
                    'artists': rec.get('artists', ['Unknown Artist']),
                    'album': rec.get('album', ''),
                    'image': rec.get('image', ''),
                    'genre': rec.get('genre', []),
                    'youtube_video_id': video_id
                },
                'score': rec['similarity_score'],
                'confidence': rec['similarity_score'],
                'explanation': {
                    'text': rec.get('explanation', f"Similar to your taste ({(rec['similarity_score'] * 100):.0f}% match)")
                },
                'platform_links': {
                    'spotify': spotify_link,
                    'youtube_music': youtube_link
                },
                'youtube_video_id': video_id  # Also at top level for easy access
            })
        
        return recommendations
    
    def get_taste_profile(self, user_id: str) -> Optional[Dict]:
        """Get user taste profile (loads from database if not cached)"""
        if user_id not in self.user_profiles:
            profile_data = self.taste_profile_service.load_profile(user_id)
            if profile_data:
                self.user_profiles[user_id] = profile_data
        return self.user_profiles.get(user_id)
    
    def update_profile_with_songs(self, user_id: str, new_songs: List[Dict], weight: float = 0.3) -> Optional[Dict]:
        """
        Update user's taste profile by adding new songs incrementally.
        
        Args:
            user_id: User identifier
            new_songs: List of new songs to add
            weight: Weight for new songs (0.0-1.0)
            
        Returns:
            Updated profile or None if failed
        """
        updated_profile = self.taste_profile_service.update_profile_with_new_songs(
            user_id, new_songs, weight
        )
        
        if updated_profile:
            # Update cache
            self.user_profiles[user_id] = updated_profile
            logger.info(f"Updated profile for user {user_id} with {len(new_songs)} new songs")
        
        return updated_profile
    
    def _get_feedback_scores(self, user_id: str) -> Dict:
        """
        IMPROVEMENT 5: Get feedback scores for songs.
        Returns a dictionary mapping (title_lower, artist_lower) -> score
        Positive scores for likes, negative for skips.
        """
        feedback_scores = {}
        try:
            from src.services.listening_history_service import get_listening_history_service
            history_service = get_listening_history_service()
            
            # Get recent listening history
            history = history_service.get_user_history(user_id, limit=100, days=30)
            
            for entry in history:
                title = entry.get('song_title', '').lower()
                artist = entry.get('artists', [''])[0].lower() if entry.get('artists') else ''
                key = (title, artist)
                
                # Check for implicit feedback signals
                metadata = entry.get('metadata', {})
                completed = entry.get('completed', False)
                duration = entry.get('duration_seconds', 0)
                
                # Likes: songs that were completed or listened to for a long time
                if completed or duration > 60:
                    feedback_scores[key] = feedback_scores.get(key, 0.0) + 0.5
                
                # Skips: songs with very short duration (< 10 seconds)
                if duration > 0 and duration < 10:
                    feedback_scores[key] = feedback_scores.get(key, 0.0) - 0.5
                
                # Repeat listens: multiple plays indicate preference
                play_count = metadata.get('play_count', 1)
                if play_count > 1:
                    feedback_scores[key] = feedback_scores.get(key, 0.0) + 0.3 * (play_count - 1)
            
            # Normalize scores to [-1, 1] range
            if feedback_scores:
                max_score = max(abs(s) for s in feedback_scores.values())
                if max_score > 0:
                    feedback_scores = {k: v / max_score for k, v in feedback_scores.items()}
        
        except Exception as e:
            logger.debug(f"Error getting feedback scores: {e}")
        
        return feedback_scores
    
    def _compute_audio_feature_boost(self, candidate: Dict, mood: Optional[str]) -> float:
        """
        IMPROVEMENT 4: Light audio feature re-ranking.
        Uses simple heuristics based on mood and song metadata.
        Returns a boost factor between -0.5 and 0.5.
        """
        if not mood:
            return 0.0
        
        boost = 0.0
        
        # Extract simple features from title/artist/genre (heuristic-based)
        title_lower = candidate.get('title', '').lower()
        artist_lower = candidate.get('artists', [''])[0].lower() if candidate.get('artists') else ''
        genre_lower = ' '.join([g.lower() for g in candidate.get('genre', [])])
        text = f"{title_lower} {artist_lower} {genre_lower}"
        
        # Mood-specific feature matching
        mood_features = {
            "energetic": {
                "positive": ["fast", "upbeat", "energetic", "intense", "pump", "workout", "dance", "party"],
                "negative": ["slow", "calm", "soft", "gentle", "relaxing"]
            },
            "calm": {
                "positive": ["calm", "peaceful", "relaxing", "soft", "gentle", "ambient", "zen"],
                "negative": ["intense", "aggressive", "energetic", "fast", "loud"]
            },
            "sad": {
                "positive": ["sad", "emotional", "melancholic", "slow", "ballad", "introspective"],
                "negative": ["happy", "upbeat", "energetic", "party"]
            },
            "happy": {
                "positive": ["happy", "upbeat", "cheerful", "joyful", "positive", "bright"],
                "negative": ["sad", "melancholic", "dark", "depressing"]
            }
        }
        
        if mood.lower() in mood_features:
            features = mood_features[mood.lower()]
            # Check for positive features
            for feature in features["positive"]:
                if feature in text:
                    boost += 0.1
            
            # Check for negative features (mismatch)
            for feature in features["negative"]:
                if feature in text:
                    boost -= 0.1
        
        # Cap boost between -0.5 and 0.5
        return max(-0.5, min(0.5, boost))
    
    def _apply_diversity_constraints(
        self, 
        candidates: List[Dict], 
        limit: int = 20
    ) -> List[Dict]:
        """
        IMPROVEMENT 3: Apply diversity constraints to prevent repetitive recommendations.
        
        Rules:
        - Max 2 songs per artist
        - Penalize consecutive same artist
        - Penalize identical tempo/energy clusters (simplified)
        """
        if not candidates:
            return []
        
        diverse_list = []
        artist_counts = {}
        last_artist = None
        seen_energy_clusters = set()
        
        for candidate in candidates:
            if len(diverse_list) >= limit:
                break
            
            artist = candidate.get('artists', ['Unknown'])[0] if candidate.get('artists') else 'Unknown'
            artist_key = artist.lower()
            
            # Constraint 1: Max 2 songs per artist
            if artist_counts.get(artist_key, 0) >= 2:
                continue
            
            # Constraint 2: Penalize consecutive same artist
            score_penalty = 0.0
            if last_artist and last_artist.lower() == artist_key:
                # Apply 15% penalty for consecutive same artist
                candidate['similarity_score'] *= 0.85
                score_penalty = 0.15
            
            # Constraint 3: Simple energy cluster diversity
            # Use genre as a proxy for energy/tempo cluster
            genre_key = '|'.join(sorted([g.lower() for g in candidate.get('genre', [])]))
            if genre_key in seen_energy_clusters and len(seen_energy_clusters) > 3:
                # Small penalty if we've seen this genre cluster recently
                candidate['similarity_score'] *= 0.95
            
            # Add to diverse list
            diverse_list.append(candidate)
            artist_counts[artist_key] = artist_counts.get(artist_key, 0) + 1
            last_artist = artist
            seen_energy_clusters.add(genre_key)
            
            # Reset energy cluster tracking periodically
            if len(seen_energy_clusters) > 10:
                seen_energy_clusters.clear()
        
        # Re-sort by score after applying penalties
        diverse_list.sort(key=lambda x: x.get('similarity_score', 0), reverse=True)
        
        return diverse_list


# Singleton instance
_recommendation_service = None

def get_recommendation_service() -> RecommendationService:
    """Get singleton instance of RecommendationService"""
    global _recommendation_service
    if _recommendation_service is None:
        _recommendation_service = RecommendationService()
    return _recommendation_service

