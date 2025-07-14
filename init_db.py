#!/usr/bin/env python3
"""
Database initialization script for RYVR platform
"""
import sys
import os
from sqlalchemy import text
from database import engine, Base
from models import User, Client, Workflow, Integration, Credit, Transaction
from auth import get_password_hash

def test_connection():
    """Test database connection"""
    try:
        with engine.connect() as connection:
            result = connection.execute(text("SELECT 1"))
            print("✅ Database connection successful!")
            return True
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return False

def create_tables():
    """Create all tables"""
    try:
        print("Creating database tables...")
        Base.metadata.create_all(bind=engine)
        print("✅ Tables created successfully!")
        return True
    except Exception as e:
        print(f"❌ Failed to create tables: {e}")
        return False

def create_default_admin():
    """Create default admin user"""
    try:
        from sqlalchemy.orm import sessionmaker
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        db = SessionLocal()
        
        # Check if admin user already exists
        existing_admin = db.query(User).filter(User.email == "admin@ryvr.com").first()
        if existing_admin:
            print("✅ Admin user already exists")
            db.close()
            return True
        
        # Create admin user
        admin_user = User(
            email="admin@ryvr.com",
            username="admin",
            hashed_password=get_password_hash("password"),
            is_active=True,
            is_admin=True
        )
        
        db.add(admin_user)
        db.commit()
        
        print("✅ Default admin user created (admin@ryvr.com / password)")
        db.close()
        return True
        
    except Exception as e:
        print(f"❌ Failed to create admin user: {e}")
        return False

def main():
    """Main initialization function"""
    print("🚀 Initializing RYVR Database...")
    print(f"Database URL: {os.getenv('DATABASE_URL', 'Not set')}")
    
    # Test connection
    if not test_connection():
        sys.exit(1)
    
    # Create tables
    if not create_tables():
        sys.exit(1)
    
    # Create default admin
    if not create_default_admin():
        sys.exit(1)
    
    print("\n🎉 Database initialization completed successfully!")
    print("\nYou can now:")
    print("1. Start the server with: uvicorn main:app --reload")
    print("2. Login with: admin@ryvr.com / password")
    print("3. Access API docs at: http://localhost:8000/docs")

if __name__ == "__main__":
    main() 