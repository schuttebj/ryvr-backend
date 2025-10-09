"""
Script to create OpenAI as the first dynamic integration
Run this after database migration
"""

import asyncio
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from database import SessionLocal, engine
import models


def create_openai_dynamic_integration(db: Session):
    """Create OpenAI integration using dynamic configuration"""
    
    # Check if OpenAI integration already exists
    existing = db.query(models.Integration).filter(
        models.Integration.provider == "openai"
    ).first()
    
    if existing:
        print(f"OpenAI integration already exists (ID: {existing.id}). Updating to dynamic configuration...")
        integration = existing
    else:
        print("Creating new OpenAI integration...")
        integration = models.Integration(
            name="OpenAI",
            provider="openai",
            integration_type="system",
            level="system"
        )
    
    # Configure as dynamic integration
    integration.is_dynamic = True
    integration.is_system_wide = True  # Available to all users
    integration.requires_user_config = True  # Each business needs their own API key
    
    # Platform configuration
    integration.platform_config = {
        "name": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "auth_type": "bearer",
        "color": "#10a37f",
        "icon_url": "https://cdn.jsdelivr.net/gh/devicons/devicon/icons/openai/openai-original.svg",
        "documentation_url": "https://platform.openai.com/docs/api-reference"
    }
    
    # Authentication configuration
    integration.auth_config = {
        "type": "bearer",
        "credentials": [
            {
                "name": "api_key",
                "type": "password",
                "required": True,
                "fixed": False,  # Users can configure their own
                "description": "OpenAI API Key"
            }
        ]
    }
    
    # Operations configuration
    integration.operation_configs = {
        "operations": [
            {
                "id": "chat_completions",
                "name": "Chat Completion",
                "description": "Generate text using OpenAI chat models",
                "endpoint": "/chat/completions",
                "method": "POST",
                "category": "AI",
                "base_credits": 2,
                "is_async": False,
                "parameters": [
                    {
                        "name": "model",
                        "type": "select",
                        "required": True,
                        "fixed": False,
                        "default": "gpt-4o-mini",
                        "description": "Model to use for completion",
                        "location": "body",
                        "options": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"]
                    },
                    {
                        "name": "messages",
                        "type": "array",
                        "required": True,
                        "fixed": False,
                        "description": "Array of message objects with role and content",
                        "location": "body"
                    },
                    {
                        "name": "temperature",
                        "type": "number",
                        "required": False,
                        "fixed": False,
                        "default": 0.7,
                        "description": "Sampling temperature between 0 and 2",
                        "location": "body"
                    },
                    {
                        "name": "max_tokens",
                        "type": "number",
                        "required": False,
                        "fixed": False,
                        "description": "Maximum tokens to generate",
                        "location": "body"
                    },
                    {
                        "name": "response_format",
                        "type": "object",
                        "required": False,
                        "fixed": False,
                        "description": "Format for the response (e.g., JSON mode)",
                        "location": "body"
                    }
                ],
                "headers": [
                    {
                        "name": "Content-Type",
                        "value": "application/json",
                        "fixed": True
                    }
                ],
                "response_mapping": {
                    "success_field": None,
                    "success_value": None,
                    "data_field": "choices[0].message.content",
                    "error_field": "error.message"
                }
            },
            {
                "id": "embeddings",
                "name": "Create Embeddings",
                "description": "Create vector embeddings for text",
                "endpoint": "/embeddings",
                "method": "POST",
                "category": "AI",
                "base_credits": 1,
                "is_async": False,
                "parameters": [
                    {
                        "name": "model",
                        "type": "select",
                        "required": True,
                        "fixed": False,
                        "default": "text-embedding-3-small",
                        "description": "Embedding model to use",
                        "location": "body",
                        "options": ["text-embedding-3-small", "text-embedding-3-large", "text-embedding-ada-002"]
                    },
                    {
                        "name": "input",
                        "type": "string",
                        "required": True,
                        "fixed": False,
                        "description": "Text to create embeddings for",
                        "location": "body"
                    }
                ],
                "headers": [
                    {
                        "name": "Content-Type",
                        "value": "application/json",
                        "fixed": True
                    }
                ],
                "response_mapping": {
                    "success_field": None,
                    "success_value": None,
                    "data_field": "data[0].embedding",
                    "error_field": "error.message"
                }
            }
        ]
    }
    
    integration.is_active = True
    
    if not existing:
        db.add(integration)
    
    db.commit()
    db.refresh(integration)
    
    print(f"✓ OpenAI dynamic integration created/updated successfully (ID: {integration.id})")
    print(f"  - Platform: {integration.platform_config['name']}")
    print(f"  - Operations: {len(integration.operation_configs['operations'])}")
    print(f"  - Is Dynamic: {integration.is_dynamic}")
    print(f"  - System Wide: {integration.is_system_wide}")
    
    return integration


def main():
    """Main execution"""
    print("=" * 60)
    print("Creating OpenAI Dynamic Integration")
    print("=" * 60)
    print()
    
    db = SessionLocal()
    try:
        integration = create_openai_dynamic_integration(db)
        
        print()
        print("=" * 60)
        print("SUCCESS: OpenAI is now configured as a dynamic integration!")
        print("=" * 60)
        print()
        print("Next steps:")
        print("1. Configure OpenAI API key in System Integrations (admin panel)")
        print("2. Test the integration using the Integration Builder")
        print("3. Use OpenAI operations in workflows")
        print()
        
    except Exception as e:
        print(f"ERROR: Failed to create OpenAI integration: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    main()

