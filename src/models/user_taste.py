"""
User Taste Vector - Multi-dimensional taste representation
Includes global taste and mood-specific profiles
"""

from typing import Dict, List, Optional
from datetime import datetime
import numpy as np
from pydantic import BaseModel, Field


class TempoPreference(BaseModel):
    """Tempo preference range"""
    min_bpm: float = Field(default=60.0, ge=0, le=200)
    max_bpm: float = Field(default=180.0, ge=0, le=200)
    preferred_bpm: Optional[float] = Field(default=None, ge=0, le=200)


class MoodSpectrum(BaseModel):
    """Mood preference distribution"""
    happy: float = Field(default=0.0, ge=0.0, le=1.0)
    sad: float = Field(default=0.0, ge=0.0, le=1.0)
    energetic: float = Field(default=0.0, ge=0.0, le=1.0)
    calm: float = Field(default=0.0, ge=0.0, le=1.0)
    romantic: float = Field(default=0.0, ge=0.0, le=1.0)
    melancholic: float = Field(default=0.0, ge=0.0, le=1.0)
    party: float = Field(default=0.0, ge=0.0, le=1.0)
    focus: float = Field(default=0.0, ge=0.0, le=1.0)
    
    def normalize(self):
        """Normalize mood spectrum to sum to 1.0"""
        total = sum(self.dict().values())
        if total > 0:
            for key in self.dict().keys():
                setattr(self, key, getattr(self, key) / total)
        return self


class TasteProfile(BaseModel):
    """Base taste profile (used for both global and mood-specific)"""
    energy_preference: float = Field(default=0.5, ge=0.0, le=1.0)
    mood_spectrum: MoodSpectrum = Field(default_factory=MoodSpectrum)
    tempo_preference: TempoPreference = Field(default_factory=TempoPreference)
    acoustic_bias: float = Field(default=0.0, ge=-1.0, le=1.0)  # -1: electronic, +1: acoustic
    familiarity_preference: float = Field(default=0.5, ge=0.0, le=1.0)
    genre_weights: Dict[str, float] = Field(default_factory=dict)
    embedding_centroid: Optional[List[float]] = Field(default=None)  # 384-dim vector
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    song_count: int = Field(default=0, ge=0)
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    version: int = Field(default=1, ge=1)


class UserTasteVector(BaseModel):
    """
    Complete user taste representation.
    Includes global taste and mood-specific profiles.
    """
    user_id: str
    global_taste: TasteProfile
    mood_profiles: Dict[str, TasteProfile] = Field(default_factory=dict)
    taste_history: List[Dict] = Field(default_factory=list)  # For drift detection
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    
    def get_mood_profile(self, mood: str, min_confidence: float = 0.5) -> Optional[TasteProfile]:
        """
        Get mood-specific profile if confidence is high enough.
        Falls back to global taste if not available or low confidence.
        
        Args:
            mood: Mood name
            min_confidence: Minimum confidence threshold
            
        Returns:
            TasteProfile or None
        """
        if mood in self.mood_profiles:
            profile = self.mood_profiles[mood]
            if profile.confidence >= min_confidence:
                return profile
        
        return self.global_taste
    
    def update_from_songs(
        self,
        songs: List[Dict],
        mood: Optional[str] = None,
        embedding_centroid: Optional[np.ndarray] = None,
        weight: float = 1.0
    ):
        """
        Update taste profile from a list of songs.
        
        Args:
            songs: List of song dicts with metadata
            mood: Optional mood context
            embedding_centroid: Pre-computed embedding centroid
            weight: Update weight (0.0 to 1.0)
        """
        if not songs:
            return
        
        # Determine target profile
        if mood and mood in self.mood_profiles:
            target_profile = self.mood_profiles[mood]
        else:
            target_profile = self.global_taste
        
        # Update embedding centroid
        if embedding_centroid is not None:
            if target_profile.embedding_centroid is None:
                target_profile.embedding_centroid = embedding_centroid.tolist()
            else:
                # Weighted average
                old_centroid = np.array(target_profile.embedding_centroid)
                new_centroid = (1 - weight) * old_centroid + weight * embedding_centroid
                target_profile.embedding_centroid = new_centroid.tolist()
        
        # Update audio features if available
        energy_values = []
        tempo_values = []
        acousticness_values = []
        genres = []
        
        for song in songs:
            if 'audio_features' in song:
                af = song['audio_features']
                if 'energy' in af:
                    energy_values.append(af['energy'])
                if 'tempo' in af:
                    tempo_values.append(af['tempo'])
                if 'acousticness' in af:
                    acousticness_values.append(af['acousticness'])
            
            if 'genre' in song:
                genres.extend(song['genre'])
        
        # Update energy preference
        if energy_values:
            avg_energy = np.mean(energy_values)
            target_profile.energy_preference = (
                (1 - weight) * target_profile.energy_preference + weight * avg_energy
            )
        
        # Update tempo preference
        if tempo_values:
            avg_tempo = np.mean(tempo_values)
            min_tempo = min(tempo_values)
            max_tempo = max(tempo_values)
            
            target_profile.tempo_preference.preferred_bpm = (
                (1 - weight) * (target_profile.tempo_preference.preferred_bpm or avg_tempo) +
                weight * avg_tempo
            )
            target_profile.tempo_preference.min_bpm = min(
                target_profile.tempo_preference.min_bpm,
                min_tempo
            )
            target_profile.tempo_preference.max_bpm = max(
                target_profile.tempo_preference.max_bpm,
                max_tempo
            )
        
        # Update acoustic bias
        if acousticness_values:
            avg_acoustic = np.mean(acousticness_values)
            # Convert 0-1 acousticness to -1 to +1 bias
            acoustic_bias = (avg_acoustic - 0.5) * 2
            target_profile.acoustic_bias = (
                (1 - weight) * target_profile.acoustic_bias + weight * acoustic_bias
            )
        
        # Update genre weights
        if genres:
            from collections import Counter
            genre_counts = Counter(genres)
            total = sum(genre_counts.values())
            
            for genre, count in genre_counts.items():
                weight_val = count / total
                if genre in target_profile.genre_weights:
                    target_profile.genre_weights[genre] = (
                        (1 - weight) * target_profile.genre_weights[genre] + weight * weight_val
                    )
                else:
                    target_profile.genre_weights[genre] = weight * weight_val
        
        # Update metadata
        target_profile.song_count += len(songs)
        target_profile.confidence = min(1.0, target_profile.song_count / 20.0)  # Cap at 20 songs
        target_profile.updated_at = datetime.utcnow().isoformat() + "Z"
        target_profile.version += 1
        
        # Update global updated_at
        self.updated_at = datetime.utcnow().isoformat() + "Z"
    
    def add_taste_snapshot(self):
        """Add current taste state to history for drift detection"""
        snapshot = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "taste_vector": {
                "energy_preference": self.global_taste.energy_preference,
                "acoustic_bias": self.global_taste.acoustic_bias,
                "familiarity_preference": self.global_taste.familiarity_preference,
                "embedding_centroid": self.global_taste.embedding_centroid
            },
            "song_count": self.global_taste.song_count
        }
        self.taste_history.append(snapshot)
        
        # Keep only last 100 snapshots
        if len(self.taste_history) > 100:
            self.taste_history = self.taste_history[-100:]

