"""
Embedding Service - Generates dense vector representations of songs
Uses sentence-transformers for local, offline-first embeddings
"""

import hashlib
import json
from typing import List, Dict, Optional, Tuple
import numpy as np
from sentence_transformers import SentenceTransformer
import os
import pickle


class EmbeddingService:
    """
    Service for generating and caching song embeddings.
    Uses deterministic hashing for caching and re-use.
    """
    
    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        cache_dir: str = "data/embeddings_cache",
        embedding_dim: int = 384
    ):
        """
        Initialize embedding service.
        
        Args:
            model_name: sentence-transformers model name
            cache_dir: Directory for caching embeddings
            embedding_dim: Expected embedding dimension
        """
        self.model_name = model_name
        self.cache_dir = cache_dir
        self.embedding_dim = embedding_dim
        
        # Create cache directory
        os.makedirs(cache_dir, exist_ok=True)
        
        # Load model (lazy loading on first use)
        self._model = None
        self._embedding_cache = {}
        self._load_cache()
    
    def _get_model(self) -> SentenceTransformer:
        """Lazy load the embedding model"""
        if self._model is None:
            print(f"Loading embedding model: {self.model_name}")
            self._model = SentenceTransformer(self.model_name)
            print("✓ Model loaded")
        return self._model
    
    def _generate_embedding_id(self, title: str, artists: List[str], genre: Optional[List[str]] = None) -> str:
        """
        Generate deterministic ID for embedding caching.
        
        Args:
            title: Song title
            artists: List of artist names
            genre: Optional list of genres
            
        Returns:
            Deterministic hash ID
        """
        # Normalize inputs
        title_norm = title.lower().strip()
        artists_norm = "|".join(sorted([a.lower().strip() for a in artists]))
        genre_norm = "|".join(sorted([g.lower().strip() for g in (genre or [])]))
        
        # Create hash
        content = f"{title_norm}||{artists_norm}||{genre_norm}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def _load_cache(self):
        """Load embedding cache from disk"""
        cache_file = os.path.join(self.cache_dir, "embeddings.pkl")
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'rb') as f:
                    self._embedding_cache = pickle.load(f)
                print(f"✓ Loaded {len(self._embedding_cache)} cached embeddings")
            except Exception as e:
                print(f"⚠ Could not load cache: {e}")
                self._embedding_cache = {}
    
    def _save_cache(self):
        """Save embedding cache to disk"""
        cache_file = os.path.join(self.cache_dir, "embeddings.pkl")
        try:
            with open(cache_file, 'wb') as f:
                pickle.dump(self._embedding_cache, f)
        except Exception as e:
            print(f"⚠ Could not save cache: {e}")
    
    def embed_song(
        self,
        title: str,
        artists: List[str],
        genre: Optional[List[str]] = None,
        use_cache: bool = True
    ) -> Tuple[np.ndarray, str]:
        """
        Generate embedding for a song.
        
        Args:
            title: Song title
            artists: List of artist names
            genre: Optional list of genres
            use_cache: Whether to use cached embeddings
            
        Returns:
            Tuple of (embedding_vector, embedding_id)
        """
        # Generate deterministic ID
        embedding_id = self._generate_embedding_id(title, artists, genre)
        
        # Check cache
        if use_cache and embedding_id in self._embedding_cache:
            return self._embedding_cache[embedding_id], embedding_id
        
        # Generate embedding
        model = self._get_model()
        
        # Create text representation
        artist_str = ", ".join(artists)
        genre_str = f" ({', '.join(genre)})" if genre else ""
        text = f"{title} by {artist_str}{genre_str}"
        
        # Generate embedding
        embedding = model.encode(text, normalize_embeddings=True)
        embedding = np.array(embedding, dtype=np.float32)
        
        # Cache it
        if use_cache:
            self._embedding_cache[embedding_id] = embedding
            self._save_cache()
        
        return embedding, embedding_id
    
    def embed_songs_batch(
        self,
        songs: List[Dict],
        use_cache: bool = True
    ) -> List[Tuple[np.ndarray, str]]:
        """
        Generate embeddings for multiple songs (batch processing).
        
        Args:
            songs: List of song dicts with 'title', 'artists', optional 'genre'
            use_cache: Whether to use cached embeddings
            
        Returns:
            List of (embedding_vector, embedding_id) tuples
        """
        results = []
        uncached_songs = []
        uncached_indices = []
        
        # Check cache first
        for i, song in enumerate(songs):
            embedding_id = self._generate_embedding_id(
                song['title'],
                song['artists'],
                song.get('genre')
            )
            
            if use_cache and embedding_id in self._embedding_cache:
                results.append((self._embedding_cache[embedding_id], embedding_id))
            else:
                results.append(None)  # Placeholder
                uncached_songs.append(song)
                uncached_indices.append(i)
        
        # Generate embeddings for uncached songs
        if uncached_songs:
            model = self._get_model()
            
            # Prepare texts
            texts = []
            for song in uncached_songs:
                artist_str = ", ".join(song['artists'])
                genre_str = f" ({', '.join(song.get('genre', []))})" if song.get('genre') else ""
                texts.append(f"{song['title']} by {artist_str}{genre_str}")
            
            # Batch encode
            embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
            
            # Update results and cache
            for idx, (song, embedding) in enumerate(zip(uncached_songs, embeddings)):
                original_idx = uncached_indices[idx]
                embedding = np.array(embedding, dtype=np.float32)
                embedding_id = self._generate_embedding_id(
                    song['title'],
                    song['artists'],
                    song.get('genre')
                )
                
                if use_cache:
                    self._embedding_cache[embedding_id] = embedding
                
                results[original_idx] = (embedding, embedding_id)
            
            if use_cache:
                self._save_cache()
        
        return results
    
    def embed_mood(self, mood: str) -> np.ndarray:
        """
        Generate semantic embedding for a mood concept.
        Uses rich descriptions for better semantic representation.
        
        Args:
            mood: Mood name (e.g., "energetic", "calm", "sad")
            
        Returns:
            Normalized embedding vector
        """
        model = self._get_model()
        # Enhanced mood descriptions for semantic accuracy
        mood_descriptions = {
            "happy": "happy cheerful upbeat positive joyful energetic",
            "sad": "sad emotional melancholic slow introspective",
            "angry": "intense powerful aggressive energetic",
            "calm": "calm relaxing peaceful soft soothing gentle",
            "energetic": "energetic upbeat high energy fast tempo",
            "tired": "gentle soft soothing calm slow",
            "anxious": "calming peaceful zen meditation relaxing",
            "romantic": "romantic love ballad tender emotional",
            "nostalgic": "nostalgic classic retro vintage",
            "focused": "instrumental ambient focus study concentration",
            "workout": "high energy intense workout exercise fitness",
            "party": "upbeat dance party celebration fun energetic"
        }
        
        text = mood_descriptions.get(mood.lower(), mood)
        embedding = model.encode(text, normalize_embeddings=True)
        return np.array(embedding, dtype=np.float32)
    
    def cosine_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """
        Compute cosine similarity between two vectors.
        
        Args:
            vec1: First vector
            vec2: Second vector
            
        Returns:
            Cosine similarity score (0.0 to 1.0)
        """
        return float(np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2)))
    
    def get_cache_stats(self) -> Dict:
        """Get statistics about the embedding cache"""
        return {
            "cached_embeddings": len(self._embedding_cache),
            "cache_dir": self.cache_dir,
            "model_name": self.model_name,
            "embedding_dim": self.embedding_dim
        }

