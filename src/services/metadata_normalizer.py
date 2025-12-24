"""
Music Metadata Normalizer
Generates optimized YouTube search queries for finding official audio/video
"""

import re
from typing import Dict, List, Any
import json


class MetadataNormalizer:
    """Normalizes music metadata for optimal YouTube search queries"""
    
    @staticmethod
    def normalize(song_title: str, artists: List[str]) -> Dict[str, Any]:
        """
        Normalize music metadata and generate YouTube search queries.
        
        Rules:
        - Remove parentheses, movie names, soundtrack info, and censored words
        - Remove "From", "feat.", "ft.", remix/version labels unless artist disambiguation is required
        - Prefer official audio over fan uploads
        - Do NOT hallucinate artists
        
        Returns JSON with normalized metadata and search queries.
        """
        # Normalize title
        normalized_title = song_title.strip()
        
        # Remove parentheses and their contents (movie names, soundtrack info, etc.)
        normalized_title = re.sub(r'\([^)]*\)', '', normalized_title)
        normalized_title = re.sub(r'\[[^\]]*\]', '', normalized_title)
        
        # Remove common soundtrack/movie prefixes
        patterns_to_remove = [
            r'^From\s+"[^"]*"\s*',  # "From "Movie Name""
            r'^From\s+[^:]*:\s*',  # "From Movie:"
            r'\(From\s+"[^"]*"\)',  # (From "Movie")
            r'\(From\s+[^)]*\)',  # (From Movie)
            r'\[From\s+"[^"]*"\]',  # [From "Movie"]
            r'\[From\s+[^\]]*\]',  # [From Movie]
            r'\(Soundtrack\)',  # (Soundtrack)
            r'\[Soundtrack\]',  # [Soundtrack]
            r'\(OST\)',  # (OST)
            r'\[OST\]',  # [OST]
        ]
        
        for pattern in patterns_to_remove:
            normalized_title = re.sub(pattern, '', normalized_title, flags=re.IGNORECASE)
        
        # Remove censored words (common patterns like "B*****s" or "F***")
        normalized_title = re.sub(r'\b\w*\*+\w*\b', '', normalized_title)
        
        # Remove "feat.", "ft.", "featuring" and featured artist names from title
        # But keep main artist names in the artists list
        feat_patterns = [
            r'\s+feat\.?\s+[^(]+',  # "feat. Artist"
            r'\s+ft\.?\s+[^(]+',  # "ft. Artist"
            r'\s+featuring\s+[^(]+',  # "featuring Artist"
            r'\s+\(feat\.?\s+[^)]+\)',  # "(feat. Artist)"
            r'\s+\(ft\.?\s+[^)]+\)',  # "(ft. Artist)"
        ]
        
        for pattern in feat_patterns:
            normalized_title = re.sub(pattern, '', normalized_title, flags=re.IGNORECASE)
        
        # Remove remix/version labels
        remix_patterns = [
            r'\s+\([^)]*remix[^)]*\)',  # (Remix)
            r'\s+\[[^\]]*remix[^\]]*\]',  # [Remix]
            r'\s+\([^)]*version[^)]*\)',  # (Version)
            r'\s+\[[^\]]*version[^\]]*\]',  # [Version]
            r'\s+\([^)]*edit[^)]*\)',  # (Edit)
            r'\s+\[[^\]]*edit[^\]]*\]',  # [Edit]
        ]
        
        for pattern in remix_patterns:
            normalized_title = re.sub(pattern, '', normalized_title, flags=re.IGNORECASE)
        
        # Clean up extra whitespace
        normalized_title = re.sub(r'\s+', ' ', normalized_title).strip()
        
        # Normalize artists list
        normalized_artists = []
        if artists:
            for artist in artists:
                artist_clean = artist.strip()
                if artist_clean:
                    # Remove common prefixes/suffixes
                    artist_clean = re.sub(r'^feat\.?\s+', '', artist_clean, flags=re.IGNORECASE)
                    artist_clean = re.sub(r'^ft\.?\s+', '', artist_clean, flags=re.IGNORECASE)
                    artist_clean = artist_clean.strip()
                    if artist_clean and artist_clean not in normalized_artists:
                        normalized_artists.append(artist_clean)
        
        # Generate optimized search queries
        artist_str = " ".join(normalized_artists[:2]) if normalized_artists else ""
        
        queries = []
        if normalized_title and artist_str:
            # Primary queries - prefer official audio
            queries.append(f"{normalized_title} {artist_str} official audio")
            queries.append(f"{normalized_title} {artist_str} official")
            queries.append(f"{normalized_title} {artist_str}")
        elif normalized_title:
            # Fallback if no artist
            queries.append(f"{normalized_title} official audio")
            queries.append(f"{normalized_title} official")
            queries.append(normalized_title)
        
        return {
            "original_title": song_title,
            "normalized_title": normalized_title,
            "original_artists": artists,
            "normalized_artists": normalized_artists,
            "search_queries": queries
        }


def normalize_metadata(song_title: str, artists: List[str]) -> str:
    """
    Convenience function that returns JSON string.
    Used as API endpoint.
    """
    normalizer = MetadataNormalizer()
    result = normalizer.normalize(song_title, artists)
    return json.dumps(result, ensure_ascii=False, indent=2)

