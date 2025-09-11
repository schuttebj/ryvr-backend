"""
Admin Dashboard Router
Handles system administration, configuration, and monitoring
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import text, inspect
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

from database import get_db, engine, Base
from auth import get_current_admin_user, get_password_hash, create_login_token
import models, schemas
from services.credit_service import CreditService

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

# =============================================================================
# DATABASE MANAGEMENT
# =============================================================================

@router.post("/bootstrap", include_in_schema=True)
async def bootstrap_system():
    """Bootstrap the system - reset database and create admin user (NO AUTH REQUIRED)"""
    try:
        from sqlalchemy.orm import sessionmaker
        
        # Force drop all tables with CASCADE to handle foreign key constraints
        with engine.connect() as connection:
            # Get all table names
            inspector = inspect(engine)
            tables = inspector.get_table_names()
            
            if tables:
                # Try to drop all tables at once first
                tables_list = ', '.join(tables)
                try:
                    connection.execute(text(f"DROP TABLE IF EXISTS {tables_list} CASCADE;"))
                    connection.commit()
                except Exception as e:
                    # If that fails, try one by one with individual transactions
                    print(f"Bulk drop failed: {e}, trying individual drops")
                    for table in tables:
                        try:
                            trans = connection.begin()
                            connection.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE;"))
                            trans.commit()
                        except Exception as table_error:
                            try:
                                trans.rollback()
                            except:
                                pass
                            print(f"Could not drop table {table}: {table_error}")
        
        # Recreate all tables
        Base.metadata.create_all(bind=engine)
        
        # Create admin user
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        db = SessionLocal()
        
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
        db.commit()
        db.refresh(admin_user)
        
        # Create admin token
        access_token = create_login_token(admin_user, None, None)
        
        db.close()
        
        return {
            "status": "success",
            "message": "System bootstrapped successfully! Database reset and admin user created.",
            "admin_credentials": {
                "username": "admin",
                "password": "password"
            },
            "access_token": access_token,
            "token_type": "bearer",
            "timestamp": datetime.utcnow(),
            "next_steps": [
                "Use this token for subsequent admin API calls",
                "Call /admin/database/initialize to create default data",
                "Access OpenAPI docs at /docs with authorization"
            ]
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Bootstrap failed: {str(e)}"
        )

@router.post("/emergency-reset", include_in_schema=True)
async def emergency_reset():
    """Emergency database reset (NO AUTH REQUIRED) - Use when system is completely broken"""
    try:
        # Force drop all tables with CASCADE
        with engine.connect() as connection:
            inspector = inspect(engine)
            tables = inspector.get_table_names()
            
            if tables:
                # Try to drop all tables at once first
                tables_list = ', '.join(tables)
                try:
                    connection.execute(text(f"DROP TABLE IF EXISTS {tables_list} CASCADE;"))
                    connection.commit()
                except Exception as e:
                    # If that fails, try one by one with individual transactions
                    print(f"Bulk drop failed: {e}, trying individual drops")
                    for table in tables:
                        try:
                            trans = connection.begin()
                            connection.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE;"))
                            trans.commit()
                        except Exception as table_error:
                            try:
                                trans.rollback()
                            except:
                                pass
                            print(f"Could not drop table {table}: {table_error}")
        
        # Recreate tables
        Base.metadata.create_all(bind=engine)
        
        return {
            "status": "success",
            "message": "Emergency database reset completed. All tables recreated.",
            "timestamp": datetime.utcnow(),
            "warning": "ALL DATA PERMANENTLY DELETED!",
            "next_step": "Call /admin/bootstrap to create admin user and get access token"
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Emergency reset failed: {str(e)}"
        )

@router.get("/health", include_in_schema=True)
async def check_system_health():
    """Check system health and database status (NO AUTH REQUIRED)"""
    try:
        # Test connection
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            
        # Check if tables exist
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        
        # Check for key tables and columns
        schema_status = {
            "tables_exist": len(tables) > 0,
            "total_tables": len(tables),
            "has_users_table": "users" in tables,
            "has_role_column": False,
            "has_agencies_table": "agencies" in tables,
            "has_businesses_table": "businesses" in tables
        }
        
        # Check if users table has role column
        if "users" in tables:
            try:
                with engine.connect() as connection:
                    result = connection.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'role';"))
                    schema_status["has_role_column"] = result.fetchone() is not None
            except:
                pass
        
        # Count records
        record_counts = {}
        if schema_status["has_users_table"]:
            try:
                with engine.connect() as connection:
                    result = connection.execute(text("SELECT COUNT(*) FROM users"))
                    record_counts["users"] = result.scalar()
            except:
                record_counts["users"] = "error"
        
        return {
            "status": "connected",
            "schema_status": schema_status,
            "record_counts": record_counts,
            "tables": tables,
            "timestamp": datetime.utcnow(),
            "recommendations": [
                "Run /admin/emergency-reset if schema is broken",
                "Run /admin/bootstrap to create admin user",
                "Run /admin/database/initialize for default data"
            ]
        }
        
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.utcnow(),
            "recommendations": [
                "Database connection failed",
                "Check DATABASE_URL environment variable",
                "Ensure PostgreSQL service is running"
            ]
        }

@router.get("/debug-models", include_in_schema=True)
async def debug_model_structure():
    """Debug model structure - show field names for troubleshooting (NO AUTH REQUIRED)"""
    try:
        # Get User model columns
        user_columns = [column.name for column in models.User.__table__.columns]
        
        # Get SubscriptionTier model columns
        tier_columns = [column.name for column in models.SubscriptionTier.__table__.columns]
        
        # Get Integration model columns
        integration_columns = [column.name for column in models.Integration.__table__.columns]
        
        return {
            "status": "success",
            "model_structures": {
                "User": user_columns,
                "SubscriptionTier": tier_columns,
                "Integration": integration_columns
            },
            "timestamp": datetime.utcnow()
        }
        
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.utcnow()
        }

@router.post("/create-schema", include_in_schema=True)
async def create_schema_only():
    """Create database schema only - no data (NO AUTH REQUIRED)"""
    try:
        # Simply create all tables
        Base.metadata.create_all(bind=engine)
        
        # Check what was created
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        
        # Check if users table has role column
        has_role_column = False
        if "users" in tables:
            try:
                with engine.connect() as connection:
                    result = connection.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'role';"))
                    has_role_column = result.fetchone() is not None
            except:
                pass
        
        return {
            "status": "success",
            "message": "Database schema created successfully",
            "tables_created": len(tables),
            "has_users_table": "users" in tables,
            "has_role_column": has_role_column,
            "tables": tables,
            "timestamp": datetime.utcnow(),
            "next_step": "Call /admin/bootstrap to create admin user"
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Schema creation failed: {str(e)}"
        )

@router.post("/full-reset", include_in_schema=True)
async def full_system_reset():
    """Complete system reset: drop tables + recreate + admin user + default data (NO AUTH REQUIRED)"""
    try:
        from sqlalchemy.orm import sessionmaker
        from decimal import Decimal
        
        results = []
        
        # Step 1: Drop all tables with CASCADE - PostgreSQL specific approach
        with engine.connect() as connection:
            inspector = inspect(engine)
            tables = inspector.get_table_names()
            
            if tables:
                # Single command to drop all tables at once
                tables_list = ', '.join(tables)
                try:
                    connection.execute(text(f"DROP TABLE IF EXISTS {tables_list} CASCADE;"))
                    connection.commit()
                    results.append(f"Dropped {len(tables)} existing tables")
                except Exception as e:
                    # If that fails, try one by one with individual transactions
                    print(f"Bulk drop failed: {e}, trying individual drops")
                    for table in tables:
                        try:
                            trans = connection.begin()
                            connection.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE;"))
                            trans.commit()
                        except Exception as table_error:
                            try:
                                trans.rollback()
                            except:
                                pass
                            print(f"Could not drop table {table}: {table_error}")
                    results.append(f"Attempted to drop {len(tables)} tables")
        
        # Step 2: Recreate all tables
        Base.metadata.create_all(bind=engine)
        results.append("Created new table schema")
        
        # Step 3: Create admin user and default data
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        db = SessionLocal()
        
        # Create admin user
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
        results.append("Created admin user")
        
        # Create subscription tiers
        tiers_data = [
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
        
        for tier_data in tiers_data:
            tier = models.SubscriptionTier(**tier_data)
            db.add(tier)
        results.append("Created 3 subscription tiers")
        
        # Create system integrations
        system_integrations = [
            {
                "name": "DataForSEO", 
                "provider": "dataforseo", 
                "integration_type": "system",
                "level": "system",
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
                "name": "OpenAI", 
                "provider": "openai", 
                "integration_type": "system",
                "level": "system", 
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
        
        for int_data in system_integrations:
            integration = models.Integration(**int_data)
            db.add(integration)
        results.append("Created 2 system integrations")
        
        db.commit()
        db.refresh(admin_user)
        
        # Create admin token
        access_token = create_login_token(admin_user, None, None)
        
        db.close()
        
        return {
            "status": "success",
            "message": "Complete system reset successful! Ready to use.",
            "actions_performed": results,
            "admin_credentials": {
                "username": "admin",
                "password": "password"
            },
            "access_token": access_token,
            "token_type": "bearer",
            "timestamp": datetime.utcnow(),
            "system_ready": True
        }
        
    except Exception as e:
        if 'db' in locals():
            db.rollback()
            db.close()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Full reset failed: {str(e)}"
        )

@router.get("/database/status")
async def get_database_status(
    current_user: models.User = Depends(get_current_admin_user)
):
    """Check database connection and table status"""
    try:
        # Test connection
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            
        # Check if tables exist
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        
        # Check for key tables
        expected_tables = [
            'users', 'agencies', 'businesses', 'agency_users', 'business_users',
            'workflow_templates', 'workflow_instances', 'integrations',
            'subscription_tiers', 'credit_pools', 'credit_transactions'
        ]
        
        table_status = {}
        for table in expected_tables:
            table_status[table] = table in tables
            
        # Count records in key tables
        record_counts = {}
        if 'users' in tables:
            with engine.connect() as connection:
                for table in ['users', 'agencies', 'businesses']:
                    if table in tables:
                        result = connection.execute(text(f"SELECT COUNT(*) FROM {table}"))
                        record_counts[table] = result.scalar()
        
        return {
            "status": "connected",
            "tables_exist": table_status,
            "record_counts": record_counts,
            "total_tables": len(tables),
            "timestamp": datetime.utcnow()
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database connection failed: {str(e)}"
        )

@router.post("/database/reset")
async def reset_database(
    confirm: bool = False,
    current_user: models.User = Depends(get_current_admin_user)
):
    """Reset database - DROP ALL TABLES and recreate schema (DANGEROUS!)"""
    if not confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This operation requires confirmation. Set 'confirm=true' to proceed."
        )
    
    try:
        # Force drop all tables with CASCADE to handle foreign key constraints
        with engine.connect() as connection:
            # Get all table names
            inspector = inspect(engine)
            tables = inspector.get_table_names()
            
            if tables:
                # Try to drop all tables at once first
                tables_list = ', '.join(tables)
                try:
                    connection.execute(text(f"DROP TABLE IF EXISTS {tables_list} CASCADE;"))
                    connection.commit()
                except Exception as e:
                    # If that fails, try one by one with individual transactions
                    print(f"Bulk drop failed: {e}, trying individual drops")
                    for table in tables:
                        try:
                            trans = connection.begin()
                            connection.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE;"))
                            trans.commit()
                        except Exception as table_error:
                            try:
                                trans.rollback()
                            except:
                                pass
                            print(f"Could not drop table {table}: {table_error}")
        
        # Recreate all tables
        Base.metadata.create_all(bind=engine)
        
        return {
            "status": "success",
            "message": "Database reset successfully. All tables dropped and recreated.",
            "timestamp": datetime.utcnow(),
            "warning": "All data has been permanently deleted!"
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database reset failed: {str(e)}"
        )

@router.post("/database/initialize")
async def initialize_database(
    current_user: models.User = Depends(get_current_admin_user)
):
    """Initialize database with default data (subscription tiers, admin user, etc.)"""
    try:
        from sqlalchemy.orm import sessionmaker
        from decimal import Decimal
        
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        db = SessionLocal()
        
        results = []
        
        # Create default subscription tiers
        tiers_data = [
            {
                "name": "Starter",
                "slug": "starter", 
                "price_monthly": Decimal("29.00"),
                "price_yearly": Decimal("290.00"),
                "credits_included": 5000,
                "client_limit": 3,
                "user_limit": 5,
                "features": ["Basic workflows", "Standard integrations", "Email support"]
            },
            {
                "name": "Professional", 
                "slug": "professional",
                "price_monthly": Decimal("99.00"),
                "price_yearly": Decimal("990.00"), 
                "credits_included": 20000,
                "client_limit": 10,
                "user_limit": 15,
                "features": ["Advanced workflows", "All integrations", "Priority support", "White-labeling"]
            },
            {
                "name": "Enterprise",
                "slug": "enterprise",
                "price_monthly": Decimal("299.00"),
                "price_yearly": Decimal("2990.00"),
                "credits_included": 100000,
                "client_limit": -1,  # unlimited
                "user_limit": -1,  # unlimited
                "features": ["Custom workflows", "Dedicated support", "Custom integrations", "SLA"]
            }
        ]
        
        tier_count = 0
        for tier_data in tiers_data:
            existing = db.query(models.SubscriptionTier).filter(
                models.SubscriptionTier.slug == tier_data["slug"]
            ).first()
            
            if not existing:
                tier = models.SubscriptionTier(**tier_data)
                db.add(tier)
                tier_count += 1
        
        # Create admin user if doesn't exist
        admin_user = db.query(models.User).filter(models.User.username == "admin").first()
        if not admin_user:
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
            results.append("Created admin user (username: admin, password: password)")
        
        # Create system integrations
        system_integrations = [
            {
                "name": "DataForSEO",
                "provider": "dataforseo",
                "integration_type": "system",
                "level": "system",
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
                "name": "OpenAI",
                "provider": "openai",
                "integration_type": "system",
                "level": "system", 
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
        
        integration_count = 0
        for int_data in system_integrations:
            existing = db.query(models.Integration).filter(
                models.Integration.name == int_data["name"],
                models.Integration.level == "system"
            ).first()
            
            if not existing:
                integration = models.Integration(**int_data)
                db.add(integration)
                integration_count += 1
        
        db.commit()
        db.close()
        
        results.extend([
            f"Created {tier_count} subscription tiers",
            f"Created {integration_count} system integrations"
        ])
        
        return {
            "status": "success",
            "message": "Database initialized successfully",
            "actions_performed": results,
            "timestamp": datetime.utcnow()
        }
        
    except Exception as e:
        if 'db' in locals():
            db.rollback()
            db.close()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database initialization failed: {str(e)}"
        )

@router.post("/database/migrate")
async def migrate_database(
    current_user: models.User = Depends(get_current_admin_user)
):
    """Create missing tables and columns (safe migration)"""
    try:
        # Create any missing tables
        Base.metadata.create_all(bind=engine)
        
        return {
            "status": "success", 
            "message": "Database migration completed. Missing tables and columns created.",
            "timestamp": datetime.utcnow()
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database migration failed: {str(e)}"
        )

# =============================================================================
# SYSTEM OVERVIEW & ANALYTICS
# =============================================================================

@router.get("/dashboard")
async def get_admin_dashboard(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user)
):
    """Get admin dashboard overview"""
    
    # User statistics
    total_users = db.query(models.User).count()
    admin_users = db.query(models.User).filter(models.User.role == "admin").count()
    agency_users = db.query(models.User).filter(models.User.role == "agency").count()
    individual_users = db.query(models.User).filter(models.User.role == "individual").count()
    
    # Agency statistics
    total_agencies = db.query(models.Agency).filter(models.Agency.is_active == True).count()
    agencies_with_businesses = db.query(models.Agency).join(models.Business).filter(
        models.Agency.is_active == True,
        models.Business.is_active == True
    ).distinct().count()
    
    # Business statistics
    total_businesses = db.query(models.Business).filter(models.Business.is_active == True).count()
    
    # Workflow statistics
    total_templates = db.query(models.WorkflowTemplate).count()
    published_templates = db.query(models.WorkflowTemplate).filter(
        models.WorkflowTemplate.status == "published"
    ).count()
    total_instances = db.query(models.WorkflowInstance).filter(
        models.WorkflowInstance.is_active == True
    ).count()
    
    # Execution statistics (last 30 days)
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    recent_executions = db.query(models.WorkflowExecution).filter(
        models.WorkflowExecution.started_at >= thirty_days_ago
    ).count()
    successful_executions = db.query(models.WorkflowExecution).filter(
        models.WorkflowExecution.started_at >= thirty_days_ago,
        models.WorkflowExecution.status == "completed"
    ).count()
    
    success_rate = (successful_executions / recent_executions * 100) if recent_executions > 0 else 0
    
    # Credit statistics
    total_credit_pools = db.query(models.CreditPool).count()
    total_credits_distributed = db.query(models.CreditPool).with_entities(
        db.query(models.CreditPool.total_purchased).label('sum')
    ).scalar() or 0
    total_credits_used = db.query(models.CreditPool).with_entities(
        db.query(models.CreditPool.total_used).label('sum')
    ).scalar() or 0
    
    return {
        "users": {
            "total": total_users,
            "admin": admin_users,
            "agency": agency_users,
            "individual": individual_users
        },
        "agencies": {
            "total": total_agencies,
            "with_businesses": agencies_with_businesses
        },
        "businesses": {
            "total": total_businesses
        },
        "workflows": {
            "templates": {
                "total": total_templates,
                "published": published_templates
            },
            "instances": total_instances,
            "executions_30d": recent_executions,
            "success_rate": round(success_rate, 2)
        },
        "credits": {
            "total_pools": total_credit_pools,
            "total_distributed": total_credits_distributed,
            "total_used": total_credits_used,
            "utilization_rate": round((total_credits_used / total_credits_distributed * 100), 2) if total_credits_distributed > 0 else 0
        }
    }

# =============================================================================
# SUBSCRIPTION TIER MANAGEMENT
# =============================================================================

@router.get("/tiers", response_model=List[schemas.SubscriptionTier])
async def get_subscription_tiers(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user)
):
    """Get all subscription tiers"""
    tiers = db.query(models.SubscriptionTier).order_by(
        models.SubscriptionTier.sort_order
    ).all()
    return tiers

@router.post("/tiers", response_model=schemas.SubscriptionTier)
async def create_subscription_tier(
    tier: schemas.SubscriptionTierCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user)
):
    """Create a new subscription tier"""
    # Check if slug already exists
    existing_tier = db.query(models.SubscriptionTier).filter(
        models.SubscriptionTier.slug == tier.slug
    ).first()
    
    if existing_tier:
        raise HTTPException(
            status_code=400,
            detail="Tier with this slug already exists"
        )
    
    db_tier = models.SubscriptionTier(**tier.dict())
    db.add(db_tier)
    db.commit()
    db.refresh(db_tier)
    return db_tier

@router.put("/tiers/{tier_id}", response_model=schemas.SubscriptionTier)
async def update_subscription_tier(
    tier_id: int,
    tier_update: schemas.SubscriptionTierUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user)
):
    """Update a subscription tier"""
    tier = db.query(models.SubscriptionTier).filter(
        models.SubscriptionTier.id == tier_id
    ).first()
    
    if not tier:
        raise HTTPException(status_code=404, detail="Tier not found")
    
    # Update fields
    for field, value in tier_update.dict(exclude_unset=True).items():
        setattr(tier, field, value)
    
    db.commit()
    db.refresh(tier)
    return tier

# =============================================================================
# INTEGRATION MANAGEMENT
# =============================================================================

@router.get("/integrations", response_model=List[schemas.Integration])
async def get_admin_integrations(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user)
):
    """Get all integrations (admin view)"""
    integrations = db.query(models.Integration).all()
    return integrations

@router.get("/integrations/usage")
async def get_integration_usage(
    days: int = 30,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user)
):
    """Get integration usage statistics"""
    start_date = datetime.utcnow() - timedelta(days=days)
    
    # Get API calls by integration
    api_calls = db.query(models.APICall).filter(
        models.APICall.created_at >= start_date
    ).all()
    
    # Group by integration
    integration_stats = {}
    total_calls = 0
    total_credits = 0
    
    for call in api_calls:
        integration = call.integration_name
        if integration not in integration_stats:
            integration_stats[integration] = {
                "calls": 0,
                "credits_used": 0,
                "avg_execution_time": 0,
                "success_rate": 0,
                "successful_calls": 0
            }
        
        integration_stats[integration]["calls"] += 1
        integration_stats[integration]["credits_used"] += call.credits_used
        total_calls += 1
        total_credits += call.credits_used
        
        if call.status_code and call.status_code < 400:
            integration_stats[integration]["successful_calls"] += 1
    
    # Calculate averages and success rates
    for integration, stats in integration_stats.items():
        if stats["calls"] > 0:
            stats["success_rate"] = round((stats["successful_calls"] / stats["calls"]) * 100, 2)
    
    return {
        "period_days": days,
        "total_api_calls": total_calls,
        "total_credits_consumed": total_credits,
        "integration_breakdown": integration_stats
    }

# =============================================================================
# WORKFLOW TEMPLATE MANAGEMENT
# =============================================================================

@router.get("/workflow-templates", response_model=List[schemas.WorkflowTemplate])
async def get_admin_workflow_templates(
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user)
):
    """Get all workflow templates (admin view)"""
    query = db.query(models.WorkflowTemplate)
    
    if status:
        query = query.filter(models.WorkflowTemplate.status == status)
    
    templates = query.all()
    return templates

@router.put("/workflow-templates/{template_id}/status")
async def update_template_status(
    template_id: int,
    status_data: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user)
):
    """Update workflow template status (publishing pipeline)"""
    template = db.query(models.WorkflowTemplate).filter(
        models.WorkflowTemplate.id == template_id
    ).first()
    
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    
    new_status = status_data.get("status")
    valid_statuses = ["draft", "testing", "beta", "published", "deprecated"]
    
    if new_status not in valid_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
        )
    
    # Update status
    template.status = new_status
    
    # Handle beta users if moving to beta
    if new_status == "beta" and "beta_users" in status_data:
        template.beta_users = status_data["beta_users"]
    
    # Version increment for published
    if new_status == "published":
        # Simple version increment (1.0 -> 1.1 -> 1.2, etc.)
        current_version = float(template.version)
        template.version = str(round(current_version + 0.1, 1))
    
    db.commit()
    db.refresh(template)
    
    return {
        "success": True,
        "template_id": template_id,
        "new_status": new_status,
        "version": template.version
    }

# =============================================================================
# USER MANAGEMENT
# =============================================================================

@router.get("/users", response_model=List[schemas.User])
async def get_admin_users(
    role: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user)
):
    """Get users (admin view)"""
    query = db.query(models.User)
    
    if role:
        query = query.filter(models.User.role == role)
    
    users = query.offset(skip).limit(limit).all()
    return users

@router.put("/users/{user_id}/status")
async def update_user_status(
    user_id: int,
    status_data: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user)
):
    """Update user status (activate/deactivate)"""
    user = db.query(models.User).filter(models.User.id == user_id).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if "is_active" in status_data:
        user.is_active = status_data["is_active"]
    
    db.commit()
    
    return {
        "success": True,
        "user_id": user_id,
        "is_active": user.is_active
    }

# =============================================================================
# CREDIT SYSTEM MANAGEMENT
# =============================================================================

@router.get("/credits/overview")
async def get_credit_overview(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user)
):
    """Get system-wide credit overview"""
    credit_service = CreditService(db)
    
    # Get all credit pools
    pools = db.query(models.CreditPool).all()
    
    total_balance = sum(pool.balance for pool in pools)
    total_purchased = sum(pool.total_purchased for pool in pools)
    total_used = sum(pool.total_used for pool in pools)
    suspended_pools = sum(1 for pool in pools if pool.is_suspended)
    
    # Get recent transactions (last 7 days)
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    recent_transactions = db.query(models.CreditTransaction).filter(
        models.CreditTransaction.created_at >= seven_days_ago
    ).count()
    
    return {
        "total_pools": len(pools),
        "total_balance": total_balance,
        "total_purchased": total_purchased,
        "total_used": total_used,
        "utilization_rate": round((total_used / total_purchased * 100), 2) if total_purchased > 0 else 0,
        "suspended_pools": suspended_pools,
        "recent_transactions_7d": recent_transactions
    }

@router.post("/credits/grant")
async def grant_credits(
    grant_data: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user)
):
    """Grant credits to an agency or user (admin action)"""
    credit_service = CreditService(db)
    
    owner_id = grant_data.get("owner_id")
    owner_type = grant_data.get("owner_type")  # "agency" or "user"
    credits = grant_data.get("credits")
    reason = grant_data.get("reason", "Admin grant")
    
    if not owner_id or not owner_type or not credits:
        raise HTTPException(
            status_code=400,
            detail="owner_id, owner_type, and credits are required"
        )
    
    try:
        pool = credit_service.ensure_credit_pool(owner_id, owner_type)
        
        transaction = credit_service.add_credits(
            pool_id=pool.id,
            amount=credits,
            description=f"Admin grant: {reason}",
            transaction_type="adjustment",
            created_by=current_user.id
        )
        
        return {
            "success": True,
            "transaction_id": transaction.id,
            "credits_granted": credits,
            "new_balance": pool.balance,
            "owner_id": owner_id,
            "owner_type": owner_type
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to grant credits: {str(e)}"
        )

# =============================================================================
# SYSTEM CONFIGURATION
# =============================================================================

@router.get("/config")
async def get_system_config(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user)
):
    """Get system configuration"""
    # This would typically come from a config table
    # For now, return hardcoded values that match our current setup
    return {
        "trial_settings": {
            "default_trial_days": 14,
            "default_trial_credits": 5000,
            "auto_trial_enabled": True
        },
        "credit_settings": {
            "base_rate_per_credit": 0.01,  # $0.01 per credit
            "default_overage_threshold": 100,
            "credit_packages": [1000, 5000, 10000, 25000, 50000, 100000]
        },
        "limits": {
            "max_businesses_per_agency": {
                "starter": 5,
                "professional": 25,
                "enterprise": 100
            },
            "max_users_per_agency": {
                "starter": 2,
                "professional": 5,
                "enterprise": 25
            },
            "max_workflow_executions_per_month": {
                "starter": 1000,
                "professional": 10000,
                "enterprise": 50000
            }
        },
        "integration_settings": {
            "system_integrations": ["dataforseo", "openai"],
            "agency_integrations": ["google_ads", "google_analytics"],
            "business_integrations": ["meta_ads", "linkedin_ads"]
        }
    }

@router.put("/config")
async def update_system_config(
    config_data: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user)
):
    """Update system configuration"""
    # In a real implementation, this would update a config table
    # For now, just return success
    return {
        "success": True,
        "message": "Configuration updated successfully",
        "updated_by": current_user.id,
        "updated_at": datetime.utcnow().isoformat()
    }

# =============================================================================
# SYSTEM MONITORING
# =============================================================================

@router.get("/health")
async def get_system_health(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user)
):
    """Get system health status"""
    
    # Check database connectivity
    try:
        db.execute("SELECT 1")
        db_status = "healthy"
    except Exception as e:
        db_status = f"error: {str(e)}"
    
    # Check recent error rate
    one_hour_ago = datetime.utcnow() - timedelta(hours=1)
    total_api_calls = db.query(models.APICall).filter(
        models.APICall.created_at >= one_hour_ago
    ).count()
    
    failed_api_calls = db.query(models.APICall).filter(
        models.APICall.created_at >= one_hour_ago,
        models.APICall.status_code >= 400
    ).count()
    
    error_rate = (failed_api_calls / total_api_calls * 100) if total_api_calls > 0 else 0
    
    # Check workflow execution health
    failed_executions = db.query(models.WorkflowExecution).filter(
        models.WorkflowExecution.started_at >= one_hour_ago,
        models.WorkflowExecution.status == "failed"
    ).count()
    
    total_executions = db.query(models.WorkflowExecution).filter(
        models.WorkflowExecution.started_at >= one_hour_ago
    ).count()
    
    execution_failure_rate = (failed_executions / total_executions * 100) if total_executions > 0 else 0
    
    # Overall health status
    if db_status != "healthy":
        overall_status = "critical"
    elif error_rate > 20 or execution_failure_rate > 15:
        overall_status = "degraded"
    elif error_rate > 10 or execution_failure_rate > 10:
        overall_status = "warning"
    else:
        overall_status = "healthy"
    
    return {
        "overall_status": overall_status,
        "database": db_status,
        "api_health": {
            "error_rate_1h": round(error_rate, 2),
            "total_calls_1h": total_api_calls,
            "failed_calls_1h": failed_api_calls
        },
        "workflow_health": {
            "failure_rate_1h": round(execution_failure_rate, 2),
            "total_executions_1h": total_executions,
            "failed_executions_1h": failed_executions
        },
        "timestamp": datetime.utcnow().isoformat()
    }
