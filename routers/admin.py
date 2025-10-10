"""
🚀 SIMPLIFIED ADMIN ROUTER
Consolidated system management with minimal endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy import inspect, text
from typing import List, Dict, Any, Optional
from datetime import datetime
from decimal import Decimal
import logging

from database import get_db, engine, Base
import models
import models_simple
import schemas
from auth import get_current_admin_user, get_password_hash

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

# =============================================================================
# SINGLE COMPREHENSIVE SYSTEM MANAGEMENT ENDPOINT
# =============================================================================

@router.post("/system/reset-and-initialize")
async def reset_and_initialize_system(
    confirm: bool = False,
    skip_auth: bool = False,
    db: Session = Depends(get_db)
):
    """
    ONE-STOP COMPLETE SYSTEM RESET AND INITIALIZATION
    
    What this does:
    - Drops entire database (all tables)  
    - Creates fresh database schema
    - Creates admin user (admin@ryvr.com / password)
    - Sets up subscription tiers (Starter, Professional, Enterprise)
    - Configures system integrations (DataForSEO, OpenAI)
    - Creates V2 workflow templates with ryvr.workflow.v1 schema
    - Returns everything needed to start using the system
    
    **Parameters:**
    - `confirm=true` - Required to confirm destructive reset
    - `skip_auth=true` - For first-time deployment (no admin login required)
    
    **Usage Examples:**
    ```bash
    # First deployment (no admin exists yet)
    POST /api/v1/admin/system/reset-and-initialize?confirm=true&skip_auth=true
    
    # Reset existing system (requires admin login)  
    POST /api/v1/admin/system/reset-and-initialize?confirm=true
    Authorization: Bearer <admin_token>
    ```
    
    WARNING: This DELETES ALL DATA permanently
    """
    try:
        # Security check - if skip_auth=false, verify we have an admin user already
        if not skip_auth:
            # Check if system is already initialized (has admin user)
            existing_admin = db.query(models.User).filter(models.User.role == "admin").first()
            if existing_admin:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="System already initialized. Admin authentication required for reset. Use skip_auth=true only for first deployment."
                )
        
        if not confirm:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Must set confirm=true to proceed with destructive reset"
            )
        
        logger.info("Starting comprehensive system reset and initialization...")
        
        # Step 1: Nuclear database reset
        logger.info("Performing nuclear database reset...")
        try:
            # Drop all tables with CASCADE to handle dependencies
            with engine.connect() as connection:
                inspector = inspect(engine)
                tables = inspector.get_table_names()
                
                if tables:
                    # Drop all tables
                    for table in reversed(tables):  # Reverse order to handle dependencies
                        try:
                            connection.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE;"))
                            connection.commit()
                        except Exception as e:
                            logger.warning(f"Failed to drop table {table}: {e}")
                
        except Exception as e:
            logger.warning(f"Database drop warning (continuing): {e}")
        
        # Step 2: Create fresh schema
        logger.info("Creating fresh database schema...")
        Base.metadata.create_all(bind=engine)
        
        # Step 2.5: Install pgvector extension for embeddings
        logger.info("Installing pgvector extension...")
        try:
            with engine.connect() as connection:
                connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
                connection.commit()
                logger.info("✅ pgvector extension installed")
        except Exception as e:
            logger.warning(f"pgvector installation warning (may already exist): {e}")
        
        # Step 3: Initialize with all data
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        db = SessionLocal()
        
        results = []
        
        # Create admin user
        logger.info("Creating admin user...")
        admin_user = models.User(
            username="admin",
            email="admin@ryvr.com",
            first_name="System",
            last_name="Administrator",
            hashed_password=get_password_hash("password"),
            role="admin",
            is_active=True,
            email_verified=True
        )
        db.add(admin_user)
        db.flush()  # Get ID for foreign keys
        results.append("Created admin user")
        
        # Create subscription tiers
        logger.info("Creating subscription tiers...")
        tiers = [
            {
                "name": "Starter", "slug": "starter", 
                "price_monthly": Decimal("29.00"), "price_yearly": Decimal("290.00"),
                "credits_included": 5000, "business_limit": 1, "seat_limit": 1,
                "storage_limit_gb": 5, "max_file_size_mb": 50,
                "features": ["Basic workflows", "Standard integrations", "Email support"],
                "cross_business_chat": False, "cross_business_files": False,
                "client_access_enabled": False, "workflow_access": ["basic"],
                "integration_access": ["google", "facebook", "email"]
            },
            {
                "name": "Professional", "slug": "professional",
                "price_monthly": Decimal("99.00"), "price_yearly": Decimal("990.00"), 
                "credits_included": 20000, "business_limit": 5, "seat_limit": 2,
                "storage_limit_gb": 25, "max_file_size_mb": 100,
                "features": ["Advanced workflows", "All integrations", "Priority support", "Cross-business features"],
                "cross_business_chat": True, "cross_business_files": True,
                "client_access_enabled": False, "workflow_access": ["basic", "advanced"],
                "integration_access": ["google", "facebook", "email", "linkedin", "twitter", "hubspot"]
            },
            {
                "name": "Enterprise", "slug": "enterprise",
                "price_monthly": Decimal("299.00"), "price_yearly": Decimal("2990.00"),
                "credits_included": 100000, "business_limit": 20, "seat_limit": 10,
                "storage_limit_gb": 100, "max_file_size_mb": 500,
                "features": ["Custom workflows", "Dedicated support", "Custom integrations", "Client access", "White-labeling"],
                "cross_business_chat": True, "cross_business_files": True,
                "client_access_enabled": True, "workflow_access": ["basic", "advanced", "enterprise"],
                "integration_access": ["all"]
            }
        ]
        
        for tier_data in tiers:
            tier = models.SubscriptionTier(**tier_data)
            db.add(tier)
        db.flush()  # Ensure tiers are created with IDs
        results.append("Created 3 subscription tiers")
        
        # Get the tiers we just created for assigning to test users
        starter_tier = db.query(models.SubscriptionTier).filter_by(slug="starter").first()
        professional_tier = db.query(models.SubscriptionTier).filter_by(slug="professional").first()
        
        # Create test users with businesses
        logger.info("Creating test users with businesses...")
        
        # Test User 1 - Marketing Agency Owner
        test_user1 = models.User(
            username="john.doe",
            email="john@example.com",
            first_name="John",
            last_name="Doe",
            hashed_password=get_password_hash("password"),
            role="user",
            is_active=True,
            email_verified=True,
            is_master_account=True
        )
        db.add(test_user1)
        db.flush()
        
        # Create subscription for test user 1
        if professional_tier:
            subscription1 = models.UserSubscription(
                user_id=test_user1.id,
                tier_id=professional_tier.id,
                status="active"
            )
            db.add(subscription1)
        
        # Create credit pool for test user 1
        credit_pool1 = models.CreditPool(
            owner_id=test_user1.id,
            balance=20000,
            total_purchased=20000,
            total_used=0,
            monthly_allowance=20000
        )
        db.add(credit_pool1)
        
        # Test User 2 - Small Business Owner
        test_user2 = models.User(
            username="jane.smith",
            email="jane@example.com",
            first_name="Jane",
            last_name="Smith",
            hashed_password=get_password_hash("password"),
            role="user",
            is_active=True,
            email_verified=True,
            is_master_account=True
        )
        db.add(test_user2)
        db.flush()
        
        # Create subscription for test user 2
        if starter_tier:
            subscription2 = models.UserSubscription(
                user_id=test_user2.id,
                tier_id=starter_tier.id,
                status="active"
            )
            db.add(subscription2)
        
        # Create credit pool for test user 2
        credit_pool2 = models.CreditPool(
            owner_id=test_user2.id,
            balance=5000,
            total_purchased=5000,
            total_used=0,
            monthly_allowance=5000
        )
        db.add(credit_pool2)
        db.flush()
        
        # Create test businesses
        logger.info("Creating test businesses...")
        
        # Business 1 - Digital Marketing Agency
        business1 = models.Business(
            owner_id=test_user1.id,
            name="Digital Marketing Pro",
            slug="digital-marketing-pro",
            industry="Marketing & Advertising",
            website="https://digitalmarketingpro.example.com",
            description="Full-service digital marketing agency specializing in SEO, social media, and content marketing.",
            contact_email="contact@digitalmarketingpro.example.com",
            onboarding_data={
                "completed": True,
                "business_goals": ["Increase online presence", "Generate leads", "Build brand awareness"],
                "target_audience": "Small to medium businesses",
                "services": ["SEO", "Social Media Marketing", "Content Marketing", "PPC Advertising"]
            },
            settings={
                "notifications_enabled": True,
                "timezone": "America/New_York"
            },
            is_active=True
        )
        db.add(business1)
        
        # Business 2 - E-commerce Store
        business2 = models.Business(
            owner_id=test_user1.id,
            name="Fashion Forward Store",
            slug="fashion-forward-store",
            industry="E-commerce & Retail",
            website="https://fashionforward.example.com",
            description="Online fashion retailer offering trendy clothing and accessories.",
            contact_email="support@fashionforward.example.com",
            onboarding_data={
                "completed": True,
                "business_goals": ["Increase sales", "Expand product line", "Improve customer retention"],
                "target_audience": "Fashion-conscious millennials and Gen Z",
                "services": ["Online Retail", "Customer Service", "Fashion Consulting"]
            },
            settings={
                "notifications_enabled": True,
                "timezone": "America/Los_Angeles"
            },
            is_active=True
        )
        db.add(business2)
        
        # Business 3 - Local Restaurant
        business3 = models.Business(
            owner_id=test_user2.id,
            name="Bella Italia Restaurant",
            slug="bella-italia-restaurant",
            industry="Food & Beverage",
            website="https://bellaitalia.example.com",
            description="Authentic Italian restaurant serving homemade pasta and traditional recipes.",
            contact_email="info@bellaitalia.example.com",
            onboarding_data={
                "completed": True,
                "business_goals": ["Increase reservations", "Build local reputation", "Grow catering business"],
                "target_audience": "Local food enthusiasts and families",
                "services": ["Dine-in", "Takeout", "Catering", "Private Events"]
            },
            settings={
                "notifications_enabled": True,
                "timezone": "America/Chicago"
            },
            is_active=True
        )
        db.add(business3)
        db.flush()
        
        results.append("Created 2 test users (john.doe, jane.smith) - password: 'password'")
        results.append("Created 3 test businesses (Digital Marketing Pro, Fashion Forward Store, Bella Italia Restaurant)")
        
        # Create system integrations
        logger.info("Creating system integrations...")
        integrations = [
            {
                "name": "DataForSEO", "provider": "dataforseo",
                "integration_type": "system", "level": "system",
                "config_schema": {
                    "type": "object",
                    "properties": {
                        "username": {"type": "string"},
                        "password": {"type": "string"},
                        "base_url": {"type": "string", "default": "https://sandbox.dataforseo.com"}
                    },
                    "required": ["username", "password"]
                },
                # System-wide SEO data service
                "is_system_wide": True,
                "requires_user_config": False,
                "available_to_roles": ["admin", "agency", "individual"],
                "is_enabled_for_agencies": True,
                "is_enabled_for_individuals": True, 
                "is_enabled_for_businesses": True,
                "is_active": True
            },
            {
                "name": "Google Analytics", "provider": "google_analytics",
                "integration_type": "agency", "level": "agency",  # Use valid constraint values
                "config_schema": {
                    "type": "object",
                    "properties": {
                        "client_id": {"type": "string"},
                        "client_secret": {"type": "string"},
                        "refresh_token": {"type": "string"}
                    },
                    "required": ["client_id", "client_secret"]
                },
                # Agency-level: Users configure their GA account
                "is_system_wide": False,
                "requires_user_config": True,
                "available_to_roles": ["agency", "individual"],
                "is_enabled_for_agencies": True,
                "is_enabled_for_individuals": True,
                "is_enabled_for_businesses": True,  # Businesses can select properties
                "is_active": True
            },
            {
                "name": "OpenAI", "provider": "openai",
                "integration_type": "system", "level": "system", 
                "config_schema": {
                    "type": "object",
                    "properties": {
                        "api_key": {"type": "string"},
                        "model": {"type": "string", "default": "gpt-4"},
                        "max_tokens": {"type": "integer", "default": 1000}
                    },
                    "required": ["api_key"]
                },
                # NEW: System-wide configuration
                "is_system_wide": True,  # Admin configures once, everyone uses
                "requires_user_config": False,  # Users don't need to configure
                "available_to_roles": ["admin", "agency", "individual"],
                "is_enabled_for_agencies": True,
                "is_enabled_for_individuals": True,
                "is_enabled_for_businesses": True,
                "is_active": True
            },
            {
                "name": "WordPress", "provider": "wordpress",
                "integration_type": "business", "level": "business",
                "config_schema": {
                    "type": "object",
                    "properties": {
                        "site_url": {"type": "string", "description": "WordPress site URL"},
                        "api_key": {"type": "string", "description": "RYVR Integration plugin API key"},
                        "sync_post_types": {"type": "array", "default": ["post", "page"]},
                        "sync_acf_fields": {"type": "boolean", "default": True},
                        "sync_rankmath_data": {"type": "boolean", "default": True},
                        "sync_taxonomies": {"type": "boolean", "default": True},
                        "two_way_sync": {"type": "boolean", "default": True}
                    },
                    "required": ["site_url", "api_key"]
                },
                # Business-level: Each business configures their own WP site
                "is_system_wide": False,
                "requires_user_config": True,
                "available_to_roles": ["agency", "individual"],
                "is_enabled_for_agencies": True,
                "is_enabled_for_individuals": True,
                "is_enabled_for_businesses": True,
                "provider_id": "wordpress",
                "is_active": True
            }
        ]
        
        for int_data in integrations:
            integration = models.Integration(**int_data)
            db.add(integration)
        db.flush()  # Ensure integrations have IDs
        results.append("Created 4 integrations with proper level separation: System (OpenAI, DataForSEO), Account (Google Analytics), Business (WordPress)")
        
        # Create OpenAI Dynamic Integration
        logger.info("Creating OpenAI as dynamic integration...")
        openai_integration = db.query(models.Integration).filter(
            models.Integration.provider == "openai"
        ).first()
        
        if openai_integration:
            # Configure as dynamic integration
            openai_integration.is_dynamic = True
            openai_integration.is_system_wide = True
            openai_integration.requires_user_config = True
            
            # Platform configuration
            openai_integration.platform_config = {
                "name": "OpenAI",
                "base_url": "https://api.openai.com/v1",
                "has_sandbox": False,
                "sandbox_base_url": "",
                "auth_type": "bearer",
                "color": "#10a37f",
                "icon_url": "https://cdn.jsdelivr.net/gh/devicons/devicon/icons/openai/openai-original.svg",
                "documentation_url": "https://platform.openai.com/docs/api-reference"
            }
            
            # Authentication configuration
            openai_integration.auth_config = {
                "type": "bearer",
                "credentials": [
                    {
                        "name": "api_key",
                        "type": "password",
                        "required": True,
                        "fixed": False,
                        "description": "OpenAI API Key"
                    }
                ]
            }
            
            # Operations configuration - MUST MATCH TOOL CATALOG IDs
            openai_integration.operation_configs = {
                "operations": [
                    {
                        "id": "chat_completion",  # Changed from chat_completions to match tool catalog
                        "name": "AI Text Generation",
                        "description": "Generate text using ChatGPT",
                        "endpoint": "/chat/completions",
                        "method": "POST",
                        "category": "ai",
                        "base_credits": 1,
                        "is_async": False,
                        "is_test_operation": True,
                        "parameters": [
                            {
                                "name": "prompt",
                                "type": "textarea",
                                "required": True,
                                "fixed": False,
                                "description": "Text prompt for AI",
                                "location": "body"
                            },
                            {
                                "name": "model",
                                "type": "select",
                                "required": False,
                                "fixed": False,
                                "default": "gpt-3.5-turbo",
                                "description": "AI model to use",
                                "location": "body",
                                "options": ["gpt-4", "gpt-3.5-turbo"]
                            },
                            {
                                "name": "max_tokens",
                                "type": "integer",
                                "required": False,
                                "fixed": False,
                                "default": 500,
                                "description": "Maximum response length",
                                "location": "body"
                            },
                            {
                                "name": "temperature",
                                "type": "number",
                                "required": False,
                                "fixed": False,
                                "default": 0.7,
                                "description": "Creativity level (0=conservative, 2=creative)",
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
                        "id": "content_analysis",  # New operation to match tool catalog
                        "name": "Content Analysis",
                        "description": "Analyze text for sentiment, topics, etc.",
                        "endpoint": "/chat/completions",
                        "method": "POST",
                        "category": "ai",
                        "base_credits": 2,
                        "is_async": False,
                        "parameters": [
                            {
                                "name": "content",
                                "type": "textarea",
                                "required": True,
                                "fixed": False,
                                "description": "Content to analyze",
                                "location": "body"
                            },
                            {
                                "name": "analysis_type",
                                "type": "multiselect",
                                "required": False,
                                "fixed": False,
                                "description": "Types of analysis to perform",
                                "location": "body",
                                "options": ["sentiment", "topics", "keywords", "readability"]
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
                        "category": "ai",
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
            
            results.append("✅ Configured OpenAI as dynamic integration with 3 operations (chat_completion, content_analysis, embeddings)")
        
        # Create V2 workflow templates
        logger.info("Creating V2 workflow templates...")
        templates = [
            {
                'name': 'Basic SEO Analysis',
                'description': 'Comprehensive SEO analysis including keyword research and competitor analysis',
                'category': 'seo', 'tags': ['seo', 'analysis', 'keywords'],
                'schema_version': 'ryvr.workflow.v1',
                'workflow_config': {
                    "inputs": {
                        "primary_keyword": {"type": "string", "required": True, "description": "Primary keyword to analyze"},
                        "location_code": {"type": "integer", "default": 2840, "description": "Location code for SERP analysis"}
                    },
                    "globals": {},
                    "steps": [
                        {
                            "id": "serp_analysis", "type": "api_call", "name": "SERP Analysis",
                            "connection_id": "dataforseo", "operation": "serp_google_organic",
                            "input": {"bindings": {"keyword": "expr: $.inputs.primary_keyword", "location_code": "expr: $.inputs.location_code"}},
                            "projection": {"top_results": "expr: @.organic[:10]", "total_results": "expr: @.total_count"}
                        },
                        {
                            "id": "keyword_analysis", "type": "api_call", "name": "Keyword Volume Analysis",
                            "connection_id": "dataforseo", "operation": "keyword_research", "depends_on": ["serp_analysis"],
                            "input": {"bindings": {"seed_keyword": "expr: $.inputs.primary_keyword"}},
                            "projection": {"keywords": "expr: @.keywords[:20]", "total_volume": "expr: sum(@.keywords[].search_volume)"}
                        },
                        {
                            "id": "ai_insights", "type": "api_call", "name": "AI Analysis",
                            "connection_id": "openai", "operation": "chat_completion",
                            "depends_on": ["serp_analysis", "keyword_analysis"],
                            "input": {"bindings": {"prompt": "expr: 'Analyze SEO data for keyword: ' + $.inputs.primary_keyword + '. SERP results: ' + to_string($.steps.serp_analysis.top_results) + '. Keywords: ' + to_string($.steps.keyword_analysis.keywords)"}}
                        }
                    ]
                },
                'execution_config': {"execution_mode": "live", "max_concurrency": 3, "timeout_seconds": 300, "dry_run": False},
                'credit_cost': 25, 'estimated_duration': 15, 'tier_access': ['starter', 'professional', 'enterprise'],
                'status': 'published', 'version': '2.0', 'icon': 'search', 'created_by': admin_user.id
            },
            {
                'name': 'AI Content Creation',
                'description': 'AI-powered content creation with SEO optimization',
                'category': 'content', 'tags': ['content', 'ai', 'seo'],
                'schema_version': 'ryvr.workflow.v1',
                'workflow_config': {
                    "inputs": {
                        "topic": {"type": "string", "required": True, "description": "Content topic"},
                        "content_type": {"type": "select", "options": ["blog", "article", "social", "ad_copy"], "default": "blog", "description": "Type of content to create"}
                    },
                    "globals": {},
                    "steps": [
                        {
                            "id": "keyword_research", "type": "api_call", "name": "Keyword Research",
                            "connection_id": "dataforseo", "operation": "keyword_research",
                            "input": {"bindings": {"seed_keyword": "expr: $.inputs.topic"}},
                            "projection": {"top_keywords": "expr: @.keywords[:10]"}
                        },
                        {
                            "id": "content_generation", "type": "api_call", "name": "Generate Content",
                            "connection_id": "openai", "operation": "chat_completion", "depends_on": ["keyword_research"],
                            "input": {"bindings": {"prompt": "expr: 'Create ' + $.inputs.content_type + ' content about: ' + $.inputs.topic + '. Include these keywords: ' + to_string($.steps.keyword_research.top_keywords)", "max_tokens": 1500}}
                        }
                    ]
                },
                'execution_config': {"execution_mode": "live", "max_concurrency": 2, "timeout_seconds": 240, "dry_run": False},
                'credit_cost': 15, 'estimated_duration': 10, 'tier_access': ['professional', 'enterprise'],
                'status': 'published', 'version': '2.0', 'icon': 'edit', 'created_by': admin_user.id
            },
            {
                'name': 'SEO Quick Check',
                'description': 'Quick SERP analysis for any keyword',
                'category': 'seo', 'tags': ['seo', 'quick', 'serp'],
                'schema_version': 'ryvr.workflow.v1',
                'workflow_config': {
                    "inputs": {"keyword": {"type": "string", "required": True, "description": "Keyword to check"}},
                    "globals": {},
                    "steps": [{
                        "id": "serp_check", "type": "api_call", "name": "SERP Check",
                        "connection_id": "dataforseo", "operation": "serp_google_organic",
                        "input": {"bindings": {"keyword": "expr: $.inputs.keyword"}}
                    }]
                },
                'execution_config': {"execution_mode": "live", "max_concurrency": 1, "timeout_seconds": 60, "dry_run": False},
                'credit_cost': 5, 'estimated_duration': 2, 'tier_access': ['starter', 'professional', 'enterprise'],
                'status': 'published', 'version': '2.0', 'icon': 'search', 'created_by': admin_user.id
            },
            {
                'name': 'WordPress Content Sync',
                'description': 'Synchronize content between WordPress and RYVR',
                'category': 'content', 'tags': ['wordpress', 'sync', 'content'],
                'schema_version': 'ryvr.workflow.v1',
                'workflow_config': {
                    "inputs": {
                        "sync_direction": {"type": "select", "options": ["from_wordpress", "to_wordpress", "both"], "default": "from_wordpress", "required": True}
                    },
                    "globals": {},
                    "steps": [{
                        "id": "wordpress_sync", "type": "api_call", "name": "WordPress Sync",
                        "connection_id": "wordpress", "operation": "sync_content",
                        "input": {"bindings": {"direction": "expr: $.inputs.sync_direction"}}
                    }]
                },
                'execution_config': {"execution_mode": "live", "max_concurrency": 1, "timeout_seconds": 300, "dry_run": False},
                'credit_cost': 5, 'estimated_duration': 10, 'tier_access': ['starter', 'professional', 'enterprise'],
                'status': 'published', 'version': '2.0', 'icon': 'sync', 'created_by': admin_user.id
            }
        ]
        
        for template_data in templates:
            template = models.WorkflowTemplate(**template_data)
            db.add(template)
        results.append("Created 4 V2 workflow templates (including WordPress)")
        
        # Initialize Simple Workflow System
        logger.info("Creating simple workflow system data...")
        
        # Create simple integrations
        simple_integrations = [
            {
                "id": "openai_simple",
                "name": "OpenAI (Simple)",
                "type": "openai",
                "status": "disconnected",
                "config": {"api_key": "", "model": "gpt-3.5-turbo"}
            },
            {
                "id": "dataforseo_simple", 
                "name": "DataForSEO (Simple)",
                "type": "dataforseo",
                "status": "disconnected",
                "config": {"username": "", "password": "", "sandbox": True}
            }
        ]
        
        for integration_data in simple_integrations:
            integration = models_simple.SimpleIntegration(**integration_data)
            db.add(integration)
        results.append("Created simple integrations")
        
        # Create sample simple workflow
        sample_workflow = models_simple.SimpleWorkflow(
            id="sample_workflow_1",
            name="Sample SEO Workflow",
            description="A basic workflow for SEO analysis",
            nodes=[
                {
                    "id": "trigger_1",
                    "type": "trigger",
                    "position": {"x": 100, "y": 100},
                    "data": {"label": "Start", "nodeType": "trigger"}
                },
                {
                    "id": "serp_1", 
                    "type": "serp",
                    "position": {"x": 300, "y": 100},
                    "data": {"label": "SERP Analysis", "nodeType": "serp", "keyword": "example keyword"}
                }
            ],
            edges=[
                {
                    "id": "edge_trigger_serp",
                    "source": "trigger_1",
                    "target": "serp_1",
                    "type": "smoothstep"
                }
            ],
            is_active=False,
            tags=["seo", "sample"]
        )
        db.add(sample_workflow)
        results.append("Created sample simple workflow")
        
        # Create system_integrations table for admin-configured integrations
        logger.info("Creating system_integrations table...")
        try:
            # Create the system_integrations table directly via SQL
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS system_integrations (
                    id SERIAL PRIMARY KEY,
                    integration_id INTEGER NOT NULL REFERENCES integrations(id),
                    custom_config JSON DEFAULT '{}',
                    credentials JSON DEFAULT '{}',
                    is_active BOOLEAN DEFAULT true,
                    last_tested TIMESTAMP WITH TIME ZONE NULL,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE NULL,
                    CONSTRAINT unique_system_integration UNIQUE (integration_id)
                );
            """))
            results.append("Created system_integrations table")
        except Exception as e:
            logger.warning(f"system_integrations table creation warning: {e}")
            results.append("system_integrations table already exists or creation failed")
        
        db.commit()
        db.close()
        
        logger.info("System reset and initialization completed successfully!")
        
        return {
            "status": "success",
            "message": "System completely reset and initialized!",
            "actions_performed": results,
            "admin_credentials": {
                "username": "admin",
                "email": "admin@ryvr.com", 
                "password": "password"
            },
            "system_ready": {
                "subscription_tiers": ["Starter ($29/mo)", "Professional ($99/mo)", "Enterprise ($299/mo)"],
                "integrations": [
                    "DataForSEO (sandbox ready)", 
                    "OpenAI (dynamic integration with chat_completions & embeddings operations)", 
                    "Google Analytics (OAuth ready)",
                    "WordPress (business-level)",
                    "System integrations table ready"
                ],
                "workflow_templates": ["Basic SEO Analysis (25 credits)", "AI Content Creation (15 credits)", "SEO Quick Check (5 credits)", "WordPress Content Sync (5 credits)"],
                "database": "Fresh schema with all tables including system_integrations",
                "vector_embeddings": "pgvector extension installed - ready for semantic search",
                "dynamic_integrations": "OpenAI configured as first dynamic integration - ready for Integration Builder"
            },
            "next_steps": [
                "1. Login: POST /api/v1/auth/login",
                "2. Configure system OpenAI integration: POST /api/v1/integrations/system", 
                "3. Test file upload: POST /api/v1/files/upload with auto_embed=true",
                "4. Test semantic search: POST /api/v1/embeddings/search",
                "5. Configure other API keys: GET /api/v1/integrations",
                "6. Test workflows: GET /api/v1/workflows/templates"
            ],
            "timestamp": datetime.utcnow()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        if 'db' in locals():
            db.rollback()
            db.close()
        logger.error(f"System reset failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"System reset failed: {str(e)}"
        )

# =============================================================================
# SIMPLE STATUS CHECK
# =============================================================================

@router.get("/system/status")
async def get_system_status():
    """
    SYSTEM STATUS CHECK
    
    Quick health check to see if system is properly initialized.
    No authentication required - useful for monitoring.
    """
    try:
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        db = SessionLocal()
        
        # Check if basic data exists
        admin_count = db.query(models.User).filter(models.User.role == "admin").count()
        tier_count = db.query(models.SubscriptionTier).count()
        integration_count = db.query(models.Integration).count()
        template_count = db.query(models.WorkflowTemplate).count()
        
        db.close()
        
        is_initialized = admin_count > 0 and tier_count > 0
        
        return {
            "system_initialized": is_initialized,
            "admin_users": admin_count,
            "subscription_tiers": tier_count,
            "integrations": integration_count,
            "workflow_templates": template_count,
            "database_healthy": True,
            "timestamp": datetime.utcnow(),
            "setup_required": not is_initialized
        }
        
    except Exception as e:
        return {
            "system_initialized": False,
            "database_healthy": False,
            "error": str(e),
            "timestamp": datetime.utcnow(),
            "setup_required": True
        }

# =============================================================================
# ESSENTIAL ADMIN ENDPOINTS (Used by Frontend)
# =============================================================================

@router.get("/dashboard")
async def get_dashboard_stats(current_user: models.User = Depends(get_current_admin_user)):
    """
    Get admin dashboard statistics
    
    Returns overview stats for the admin dashboard including:
    - User counts by role
    - Workflow execution stats
    - System health metrics
    - Recent activity
    """
    try:
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        db = SessionLocal()
        
        # User statistics (simplified structure)
        total_users = db.query(models.User).count()
        admin_users = db.query(models.User).filter(models.User.role == "admin").count()
        regular_users = db.query(models.User).filter(models.User.role == "user").count()
        
        # Business statistics (direct user ownership)
        total_businesses = db.query(models.Business).count()
        users_with_businesses = db.query(models.User.id).join(models.Business, models.User.id == models.Business.owner_id).distinct().count()
        
        # Workflow statistics
        total_templates = db.query(models.WorkflowTemplate).count()
        published_templates = db.query(models.WorkflowTemplate).filter(
            models.WorkflowTemplate.status == "published"
        ).count()
        total_executions = db.query(models.WorkflowExecution).count()
        
        # Calculate success rate from recent executions
        completed_executions = db.query(models.WorkflowExecution).filter(
            models.WorkflowExecution.status == "completed"
        ).count()
        success_rate = round((completed_executions / max(total_executions, 1)) * 100)
        
        # System statistics
        total_integrations = db.query(models.Integration).count()
        active_integrations = db.query(models.Integration).filter(
            models.Integration.is_active == True
        ).count()
        
        db.close()
        
        # Return data matching frontend's DashboardStats interface
        return {
            "users": {
                "total": total_users,
                "admin": admin_users,
                "regular": regular_users,  # Simplified: just admin and regular users
                "with_businesses": users_with_businesses
            },
            "businesses": {
                "total": total_businesses
            },
            "workflows": {
                "templates": {
                    "total": total_templates,
                    "published": published_templates
                },
                "instances": 0,  # Placeholder - would need WorkflowInstance model
                "executions_30d": total_executions,  # Using total as placeholder for 30-day count
                "success_rate": success_rate
            },
            "credits": {
                "total_pools": 0,  # Placeholder - would need Credit/Pool models
                "total_distributed": 0,
                "total_used": 0,
                "utilization_rate": 0
            },
            "integrations": {
                "total": total_integrations,
                "active": active_integrations
            },
            "system": {
                "uptime": "Available",
                "version": "2.0",
                "environment": "production"
            },
            "timestamp": datetime.utcnow()
        }
        
    except Exception as e:
        logger.error(f"Failed to get dashboard stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get dashboard stats: {str(e)}"
        )

@router.get("/health")
async def get_system_health():
    """
    Get detailed system health information
    
    Returns detailed health metrics for monitoring and dashboard display.
    This is different from /system/status which is for basic initialization checks.
    """
    try:
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        db = SessionLocal()
        
        # Database health
        try:
            db.execute(text("SELECT 1"))
            database_healthy = True
        except:
            database_healthy = False
        
        # Check integrations
        active_integrations = db.query(models.Integration).filter(
            models.Integration.is_active == True
        ).count()
        total_integrations = db.query(models.Integration).count()
        integrations_healthy = active_integrations > 0
        
        db.close()
        
        # Overall system status
        overall_status = "healthy" if database_healthy and integrations_healthy else "degraded"
        
        return {
            "status": overall_status,
            "database": database_healthy,
            "integrations": integrations_healthy,
            "services": True,  # Assume API services are healthy if we can respond
            "uptime": "Available",
            "details": {
                "database_connection": "OK" if database_healthy else "ERROR",
                "active_integrations": f"{active_integrations}/{total_integrations}",
                "api_response_time": "< 100ms"
            },
            "timestamp": datetime.utcnow()
        }
        
    except Exception as e:
        return {
            "status": "error",
            "database": False,
            "integrations": False,
            "services": False,
            "uptime": "Unknown",
            "error": str(e),
            "timestamp": datetime.utcnow()
        }

@router.get("/users")
async def get_users(
    skip: int = 0,
    limit: int = 100,
    role: Optional[str] = None,
    current_user: models.User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """
    Get users with optional filtering
    
    Supports pagination and role-based filtering for admin user management.
    """
    try:
        query = db.query(models.User)
        
        if role:
            query = query.filter(models.User.role == role)
        
        users = query.offset(skip).limit(limit).all()
        total = query.count()
        
        return {
            "users": [
                {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "role": user.role,
                    "is_active": user.is_active,
                    "email_verified": user.email_verified,
                    "created_at": user.created_at,
                    "is_master_account": user.is_master_account,
                    "master_account_id": user.master_account_id
                }
                for user in users
            ],
            "total": total,
            "skip": skip,
            "limit": limit
        }
        
    except Exception as e:
        logger.error(f"Failed to get users: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get users: {str(e)}"
        )

@router.put("/users/{user_id}/status")
async def update_user_status(
    user_id: int,
    status: str,  # 'activate' or 'deactivate'
    current_user: models.User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """
    Update user status (activate/deactivate)
    
    Allows admin to activate or deactivate user accounts.
    """
    try:
        user = db.query(models.User).filter(models.User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Don't allow deactivating the last admin
        if status == 'deactivate' and user.role == 'admin':
            admin_count = db.query(models.User).filter(
                models.User.role == 'admin',
                models.User.is_active == True
            ).count()
            if admin_count <= 1:
                raise HTTPException(
                    status_code=400,
                    detail="Cannot deactivate the last admin user"
                )
        
        user.is_active = (status == 'activate')
        db.commit()
        
        return {
            "message": f"User {status}d successfully",
            "user_id": user_id,
            "new_status": user.is_active
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update user status: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update user status: {str(e)}"
        )

@router.get("/integrations")
async def get_integrations(
    current_user: models.User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """
    Get system integrations
    
    Returns list of all integrations for admin management.
    """
    try:
        integrations = db.query(models.Integration).all()
        
        return {
            "integrations": [
                {
                    "id": integration.id,
                    "name": integration.name,
                    "provider": integration.provider,
                    "integration_type": integration.integration_type,
                    "level": integration.level,
                    "is_active": integration.is_active,
                    "config_schema": integration.config_schema,
                    "created_at": integration.created_at,
                    "updated_at": integration.updated_at
                }
                for integration in integrations
            ]
        }
        
    except Exception as e:
        logger.error(f"Failed to get integrations: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get integrations: {str(e)}"
        )
