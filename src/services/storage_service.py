"""
Storage Service
Manages JSON file storage for seed songs and listening history
"""

import json
import os
from typing import List, Dict, Optional
from datetime import datetime


class StorageService:
    """Service for storing seed songs and listening data in JSON"""
    
    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        self.seed_songs_file = os.path.join(data_dir, "seed_songs.json")
        self.user_data_file = os.path.join(data_dir, "user_data.json")
        os.makedirs(data_dir, exist_ok=True)
    
    def _load_json(self, filepath: str, default: dict = None) -> dict:
        """Load JSON file"""
        if default is None:
            default = {}
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading {filepath}: {e}")
                return default
        return default
    
    def _save_json(self, filepath: str, data: dict):
        """Save JSON file"""
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving {filepath}: {e}")
    
    def save_seed_songs(self, user_id: str, seed_songs: List[Dict]):
        """
        Save seed songs for a user.
        
        Args:
            user_id: User identifier
            seed_songs: List of seed songs
        """
        data = self._load_json(self.seed_songs_file, {})
        data[user_id] = {
            "seed_songs": seed_songs,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
        self._save_json(self.seed_songs_file, data)
    
    def get_seed_songs(self, user_id: str) -> List[Dict]:
        """Get seed songs for a user"""
        data = self._load_json(self.seed_songs_file, {})
        return data.get(user_id, {}).get("seed_songs", [])
    
    def save_listening_data(self, user_id: str, song_data: Dict):
        """
        Save a song that user listened to.
        
        Args:
            user_id: User identifier
            song_data: Song data with timestamp
        """
        data = self._load_json(self.user_data_file, {})
        
        if user_id not in data:
            data[user_id] = {
                "listened_songs": [],
                "analysis_history": []
            }
        
        song_data["listened_at"] = datetime.now().isoformat()
        data[user_id]["listened_songs"].append(song_data)
        
        # Keep only last 1000 songs
        if len(data[user_id]["listened_songs"]) > 1000:
            data[user_id]["listened_songs"] = data[user_id]["listened_songs"][-1000:]
        
        self._save_json(self.user_data_file, data)
    
    def get_listening_data(self, user_id: str, limit: Optional[int] = None) -> List[Dict]:
        """Get listening data for a user"""
        data = self._load_json(self.user_data_file, {})
        songs = data.get(user_id, {}).get("listened_songs", [])
        
        if limit:
            songs = songs[-limit:]
        
        return songs
    
    def save_analysis_result(self, user_id: str, analysis_result: Dict):
        """Save analysis result"""
        data = self._load_json(self.user_data_file, {})
        
        if user_id not in data:
            data[user_id] = {
                "listened_songs": [],
                "analysis_history": []
            }
        
        analysis_result["analyzed_at"] = datetime.now().isoformat()
        data[user_id]["analysis_history"].append(analysis_result)
        
        # Keep only last 50 analyses
        if len(data[user_id]["analysis_history"]) > 50:
            data[user_id]["analysis_history"] = data[user_id]["analysis_history"][-50:]
        
        self._save_json(self.user_data_file, data)
    
    def get_latest_analysis(self, user_id: str) -> Optional[Dict]:
        """Get latest analysis result for a user"""
        data = self._load_json(self.user_data_file, {})
        history = data.get(user_id, {}).get("analysis_history", [])
        return history[-1] if history else None
    
    def get_all_user_data(self, user_id: str) -> Dict:
        """Get all data for a user"""
        seed_songs = self.get_seed_songs(user_id)
        listening_data = self.get_listening_data(user_id)
        latest_analysis = self.get_latest_analysis(user_id)
        
        return {
            "user_id": user_id,
            "seed_songs": seed_songs,
            "listened_songs": listening_data,
            "latest_analysis": latest_analysis,
            "total_songs": len(seed_songs) + len(listening_data)
        }


# Singleton instance
_storage_service = None

def get_storage_service() -> StorageService:
    """Get singleton instance of StorageService"""
    global _storage_service
    if _storage_service is None:
        _storage_service = StorageService()
    return _storage_service

