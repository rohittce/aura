#!/usr/bin/env python3
"""
Database Setup Script
Run this script to initialize the database at deployment time
Supports both PostgreSQL and SQLite
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.database.models import init_database, engine, get_database_url
from sqlalchemy import inspect, text

def check_database_exists():
    """Check if database tables already exist"""
    try:
        inspector = inspect(engine)
        existing_tables = inspector.get_table_names()
        return len(existing_tables) > 0
    except Exception as e:
        print(f"Error checking database: {e}")
        return False

def test_connection():
    """Test database connection"""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        print(f"Database connection failed: {e}")
        return False

def main():
    """Main setup function"""
    print("=" * 60)
    print("AURA Music App - Database Setup")
    print("=" * 60)
    
    db_url = get_database_url()
    db_type = "PostgreSQL" if db_url.startswith("postgresql") else "SQLite"
    print(f"\nDatabase Type: {db_type}")
    print(f"Database URL: {db_url.split('@')[-1] if '@' in db_url else db_url}")
    
    # Test connection
    print("\nTesting database connection...")
    if not test_connection():
        print("✗ Failed to connect to database!")
        print("\nPlease check your database configuration:")
        print("  - DATABASE_URL environment variable, or")
        print("  - DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD")
        sys.exit(1)
    print("✓ Database connection successful")
    
    # Check if database already exists
    if check_database_exists():
        print("\n⚠ Database tables already exist.")
        if os.getenv("FORCE_RECREATE") != "true":
            response = input("Do you want to recreate them? This will DELETE ALL DATA! (yes/no): ")
            if response.lower() != 'yes':
                print("Setup cancelled. Database already initialized.")
                return
            print("Recreating database tables...")
        else:
            print("FORCE_RECREATE=true detected. Recreating database tables...")
    
    print("\nInitializing database...")
    try:
        init_database()
        print("\n✓ Database initialized successfully!")
        print(f"Database location: {db_url.split('@')[-1] if '@' in db_url else db_url}")
        print("\nYou can now start the application.")
    except Exception as e:
        print(f"\n✗ Error initializing database: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
