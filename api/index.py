"""
Vercel Serverless Function Handler for FastAPI App
"""
import sys
import os

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# Import the FastAPI app
from src.api.main import app
from mangum import Mangum

# Create ASGI handler for Vercel
handler = Mangum(app, lifespan="off")

