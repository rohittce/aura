import os
import sys
from pathlib import Path
from sqlalchemy import text, inspect
from dotenv import load_dotenv

# Add parent directory to path to allow imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Load environment variables explicitly
env_path = Path(__file__).parent.parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)
    print(f"✓ Loaded environment from {env_path}")
else:
    load_dotenv() # Try default

from src.database.models import engine

def migrate():
    """Run database migrations"""
    print(f"🔄 Checking database schema for: {engine.url} ...")
    
    inspector = inspect(engine)
    
    # Check users table
    if inspector.has_table("users"):
        columns = [c["name"] for c in inspector.get_columns("users")]
        
        # Check for username column
        if "username" not in columns:
            print("⚠ Column 'username' missing in 'users' table. Adding it...")
            with engine.connect() as conn:
                try:
                    # SQLite syntax (and mostly generic SQL)
                    conn.execute(text("ALTER TABLE users ADD COLUMN username VARCHAR(50)"))
                    conn.execute(text("CREATE UNIQUE INDEX ix_users_username ON users (username)"))
                    conn.commit()
                    print("✓ Added 'username' column successfully")
                except Exception as e:
                    print(f"✗ Failed to add username column: {e}")
        else:
            print("✓ 'username' column exists")
            
        # Check for profile column
        if "profile" not in columns:
            print("⚠ Column 'profile' missing in 'users' table. Adding it...")
            with engine.connect() as conn:
                try:
                    if engine.url.get_backend_name() == 'postgresql':
                        conn.execute(text("ALTER TABLE users ADD COLUMN profile JSONB DEFAULT '{}'::jsonb"))
                    else:
                        conn.execute(text("ALTER TABLE users ADD COLUMN profile JSON"))
                    conn.commit()
                    print("✓ Added 'profile' column successfully")
                except Exception as e:
                    print(f"✗ Failed to add profile column: {e}")
        else:
            print("✓ 'profile' column exists")
            
    else:
        print("⚠ 'users' table not found. Run init_database() first.")

if __name__ == "__main__":
    migrate()
