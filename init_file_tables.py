#!/usr/bin/env python3
"""
Initialize File Management Tables
Creates the new file-related tables and sets up basic configuration
"""

import os
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Add the backend directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import Base, get_db
from models import File, StorageUsage, FilePermission, SubscriptionTier
from config import settings

def init_file_tables():
    """Initialize file management tables"""
    
    # Create engine
    engine = create_engine(settings.database_url)
    
    # Create all tables
    print("Creating file management tables...")
    Base.metadata.create_all(bind=engine)
    print("✅ Tables created successfully!")
    
    # Create a session
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    
    try:
        # Update existing subscription tiers with storage limits if they don't have them
        print("Updating subscription tiers with storage limits...")
        
        # Check if storage_limit_gb column exists, if not add it
        try:
            result = db.execute(text("""
                ALTER TABLE subscription_tiers 
                ADD COLUMN IF NOT EXISTS storage_limit_gb INTEGER DEFAULT 5,
                ADD COLUMN IF NOT EXISTS max_file_size_mb INTEGER DEFAULT 100;
            """))
            db.commit()
            print("✅ Storage limit columns added to subscription_tiers table!")
        except Exception as e:
            print(f"Note: Storage columns might already exist: {e}")
            db.rollback()
        
        # Update existing tiers with default storage limits
        db.execute(text("""
            UPDATE subscription_tiers 
            SET storage_limit_gb = COALESCE(storage_limit_gb, 5),
                max_file_size_mb = COALESCE(max_file_size_mb, 100)
            WHERE storage_limit_gb IS NULL OR max_file_size_mb IS NULL;
        """))
        db.commit()
        
        # Create the files directory structure if it doesn't exist
        files_base_path = "/files"
        if not os.path.exists(files_base_path):
            print(f"Creating files directory: {files_base_path}")
            os.makedirs(files_base_path, exist_ok=True)
            print("✅ Files directory created!")
        
        print("🎉 File management system initialized successfully!")
        print("\nNext steps:")
        print("1. Install required dependencies: pip install -r requirements.txt")
        print("2. Test file upload endpoints")
        print("3. Configure storage limits in subscription tiers")
        
    except Exception as e:
        print(f"❌ Error during initialization: {e}")
        db.rollback()
        raise
    finally:
        db.close()

def create_test_directories():
    """Create test directory structure"""
    base_path = "/files"
    
    # Create some test account directories
    test_accounts = [1, 2, 3]  # User IDs
    
    for account_id in test_accounts:
        account_dir = f"{base_path}/{account_id}"
        account_files_dir = f"{account_dir}/account"
        business_files_dir = f"{account_dir}/business"
        
        os.makedirs(account_files_dir, exist_ok=True)
        os.makedirs(business_files_dir, exist_ok=True)
        
        print(f"✅ Created directory structure for account {account_id}")

if __name__ == "__main__":
    print("🚀 Initializing RYVR File Management System...")
    init_file_tables()
    create_test_directories()
    print("✨ Initialization complete!")
