#!/usr/bin/env python3
"""
Database initialization script for RYVR platform
"""
import sys
import os
from sqlalchemy import text
from database import engine, Base
from models import User, Client, Workflow, Integration, TaskTemplate
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

def create_default_task_templates():
    """Create default task templates"""
    try:
        from sqlalchemy.orm import sessionmaker
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        db = SessionLocal()
        
        # Check if task templates already exist
        existing_templates = db.query(TaskTemplate).count()
        if existing_templates > 0:
            print("✅ Task templates already exist")
            db.close()
            return True
        
        # Define task templates
        templates = [
            {
                'name': 'SERP Analysis',
                'description': 'Analyze search engine results for keywords',
                'category': 'seo_analysis',
                'credit_cost': 1,
                'config_schema': {
                    'type': 'object',
                    'properties': {
                        'keyword': {'type': 'string', 'description': 'Target keyword'},
                        'locationCode': {'type': 'integer', 'description': 'Location code'},
                        'languageCode': {'type': 'string', 'description': 'Language code'},
                        'device': {'type': 'string', 'enum': ['desktop', 'mobile']},
                        'os': {'type': 'string', 'description': 'Operating system'},
                        'maxResults': {'type': 'integer', 'minimum': 1, 'maximum': 700},
                        'target': {'type': 'string', 'description': 'Target domain filter'},
                        'resultType': {'type': 'string', 'enum': ['all', 'organic_only', 'news', 'shopping', 'images', 'videos']},
                        'dateRange': {'type': 'string', 'enum': ['any', 'past_hour', 'past_24h', 'past_week', 'past_month', 'past_year']}
                    },
                    'required': ['keyword']
                }
            },
            {
                'name': 'Data Filter',
                'description': 'Filter and process data arrays with various operations',
                'category': 'data_processing',
                'credit_cost': 0,
                'config_schema': {
                    'type': 'object',
                    'properties': {
                        'dataSource': {'type': 'string', 'description': 'JSON path to data source'},
                        'filterProperty': {'type': 'string', 'description': 'Property to filter on'},
                        'filterOperation': {
                            'type': 'string', 
                            'enum': ['contains', 'not_contains', 'equals', 'not_equals', 'starts_with', 'ends_with', 'greater_than', 'less_than', 'exists', 'not_exists']
                        },
                        'filterValue': {'type': 'string', 'description': 'Value to filter by'},
                        'caseSensitive': {'type': 'boolean', 'default': False},
                        'maxResults': {'type': 'integer', 'minimum': 0, 'description': '0 = no limit'}
                    },
                    'required': ['dataSource', 'filterProperty', 'filterOperation']
                }
            },
            {
                'name': 'AI Analysis',
                'description': 'Analyze content and data using AI',
                'category': 'ai_processing',
                'credit_cost': 2,
                'config_schema': {
                    'type': 'object',
                    'properties': {
                        'userPrompt': {'type': 'string', 'description': 'Analysis prompt'},
                        'modelOverride': {'type': 'string', 'description': 'AI model to use'},
                        'temperatureOverride': {'type': 'number', 'minimum': 0, 'maximum': 2},
                        'maxTokens': {'type': 'integer', 'minimum': 1, 'maximum': 4000}
                    },
                    'required': ['userPrompt']
                }
            },
            {
                'name': 'Content Extraction',
                'description': 'Extract content from web pages',
                'category': 'content_processing',
                'credit_cost': 1,
                'config_schema': {
                    'type': 'object',
                    'properties': {
                        'inputMapping': {'type': 'string', 'description': 'JSON path to URLs'},
                        'extractionType': {
                            'type': 'string', 
                            'enum': ['full_text', 'title_only', 'meta_data', 'headings', 'custom_selector']
                        },
                        'cssSelector': {'type': 'string', 'description': 'CSS selector for custom extraction'},
                        'maxLength': {'type': 'integer', 'minimum': 100, 'maximum': 50000},
                        'removeHtml': {'type': 'boolean', 'default': True},
                        'batchProcess': {'type': 'boolean', 'default': True}
                    },
                    'required': ['inputMapping']
                }
            }
        ]
        
        # Create task templates
        for template_data in templates:
            template = TaskTemplate(**template_data)
            db.add(template)
        
        db.commit()
        print(f"✅ Created {len(templates)} default task templates")
        db.close()
        return True
        
    except Exception as e:
        print(f"❌ Failed to create task templates: {e}")
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
    
    # Create default task templates
    if not create_default_task_templates():
        sys.exit(1)
    
    print("\n🎉 Database initialization completed successfully!")
    print("\nYou can now:")
    print("1. Start the server with: uvicorn main:app --reload")
    print("2. Login with: admin@ryvr.com / password")
    print("3. Access API docs at: http://localhost:8000/docs")

if __name__ == "__main__":
    main() 