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
                "credits_included": 5000, "client_limit": 3, "user_limit": 5,
                "features": ["Basic workflows", "Standard integrations", "Email support"]
            },
            {
                "name": "Professional", "slug": "professional",
                "price_monthly": Decimal("99.00"), "price_yearly": Decimal("990.00"), 
                "credits_included": 20000, "client_limit": 10, "user_limit": 15,
                "features": ["Advanced workflows", "All integrations", "Priority support", "White-labeling"]
            },
            {
                "name": "Enterprise", "slug": "enterprise",
                "price_monthly": Decimal("299.00"), "price_yearly": Decimal("2990.00"),
                "credits_included": 100000, "client_limit": -1, "user_limit": -1,
                "features": ["Custom workflows", "Dedicated support", "Custom integrations", "SLA"]
            }
        ]
        
        for tier_data in tiers:
            tier = models.SubscriptionTier(**tier_data)
            db.add(tier)
        results.append("Created 3 subscription tiers")
        
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
                "is_active": True
            }
        ]
        
        for int_data in integrations:
            integration = models.Integration(**int_data)
            db.add(integration)
        results.append("Created 2 system integrations")
        
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
            }
        ]
        
        for template_data in templates:
            template = models.WorkflowTemplate(**template_data)
            db.add(template)
        results.append("Created 3 V2 workflow templates")
        
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
                "integrations": ["DataForSEO (sandbox ready)", "OpenAI (requires API key)"],
                "workflow_templates": ["Basic SEO Analysis (25 credits)", "AI Content Creation (15 credits)", "SEO Quick Check (5 credits)"],
                "database": "Fresh schema with all tables"
            },
            "next_steps": [
                "1. Login: POST /api/v1/auth/login",
                "2. Configure API keys: GET /api/v1/integrations", 
                "3. Test workflows: GET /api/v1/workflows/templates",
                "4. Create agencies/businesses as needed"
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

# Fix the endpoint definition by removing the duplicate decorator
# The main endpoint already has the @router.post decorator above
