#!/usr/bin/env python3

import uvicorn
import sys
import os
from pathlib import Path

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    # Try multiple possible .env file locations
    env_paths = [
        Path(__file__).parent / ".env",
        Path(__file__).parent.parent / ".env",
        Path.cwd() / ".env",
    ]
    for env_path in env_paths:
        if env_path.exists():
            load_dotenv(env_path)
            print(f"✓ Loaded environment variables from {env_path}")
            break
    else:
        # Try default location
        load_dotenv()
        print("✓ Attempted to load .env file (if exists)")
except ImportError:
    print("⚠ python-dotenv not installed, skipping .env file loading")
except Exception as e:
    print(f"⚠ Error loading .env file: {e}")

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Initialize database before starting server
try:
    from src.database.models import init_database
    print("Initializing database...")
    init_database()
    print("✓ Database ready")
except Exception as e:
    print(f"⚠ Database initialization: {e}")
    # Continue anyway - database might already exist

if __name__ == "__main__":
    print("=" * 60)
    print("AI Music Recommendation System")
    print("=" * 60)
    print("\nStarting API server...")
    print("API will be available at: http://localhost:8000")
    print("Interactive docs: http://localhost:8000/docs")
    print("\nPress Ctrl+C to stop\n")
    
    uvicorn.run(
        "src.api.main:socketio_asgi",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )

