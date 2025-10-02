from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta, datetime
from typing import List, Optional

from database import get_db, engine, Base
from auth import (
    authenticate_user, 
    create_access_token, 
    get_current_active_user, 
    get_current_admin_user,
    get_current_agency_user,
    create_user,
    get_password_hash,
    get_user_agencies,
    get_user_businesses,
    verify_business_access,
    verify_agency_access,
    create_login_token
)
from config import settings
import models, schemas

router = APIRouter()

@router.post("/login", response_model=schemas.LoginResponse)
async def login_for_access_token(
    form_data: schemas.LoginRequest,
    db: Session = Depends(get_db)
):
    """Simplified login endpoint for user/admin roles."""
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Get user's businesses if they are a user
    businesses = []
    business_id = None
    if user.role == 'user':
        businesses = get_user_businesses(db, user)
        business_id = businesses[0].id if businesses else None
    
    # Create token with business context
    access_token = create_login_token(user, business_id)
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": user,
        "businesses": businesses,
        "current_business_id": business_id
    }

@router.get("/me", response_model=schemas.UserContext)
async def get_user_context(
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get complete user context including subscription, businesses, and seats."""
    # Get subscription tier
    subscription_tier = None
    if current_user.subscription:
        subscription_tier = current_user.subscription.tier
    
    # Get businesses based on role
    businesses = []
    if current_user.role == 'user':
        # Users see their owned businesses + businesses they have access to
        owned_businesses = db.query(models.Business).filter_by(owner_id=current_user.id).all()
        member_businesses = db.query(models.Business).join(models.BusinessUser).filter(
            models.BusinessUser.user_id == current_user.id
        ).all()
        
        # Combine and deduplicate
        business_ids = set()
        for business in owned_businesses + member_businesses:
            if business.id not in business_ids:
                businesses.append(business)
                business_ids.add(business.id)
    elif current_user.role == 'admin':
        # Admins can see all businesses
        businesses = db.query(models.Business).all()
    
    # Get seat users (only for master accounts)
    seat_users = []
    if current_user.is_master_account:
        seat_users = db.query(models.User).filter_by(master_account_id=current_user.id).all()
    
    return {
        "user": current_user,
        "subscription_tier": subscription_tier,
        "businesses": businesses,
        "current_business_id": None,  # Will be set by JWT token
        "seat_users": seat_users
    }

@router.post("/switch-business", response_model=schemas.BusinessSwitchResponse)
async def switch_business_context(
    request: schemas.BusinessSwitchRequest,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Switch business context for the user."""
    business_id = request.business_id
    
    # Verify access to the business if specified
    if business_id:
        if current_user.role == 'user':
            # Check if user owns or has access to this business
            business = db.query(models.Business).filter_by(id=business_id).first()
            if not business:
                raise HTTPException(status_code=404, detail="Business not found")
            
            # Check ownership or membership
            is_owner = business.owner_id == current_user.id
            is_member = db.query(models.BusinessUser).filter_by(
                business_id=business_id, user_id=current_user.id
            ).first() is not None
            
            if not (is_owner or is_member):
                raise HTTPException(status_code=403, detail="Access denied to this business")
        # Admins can access any business
    
    # Create new token with updated business context
    access_token = create_login_token(current_user, business_id)
    
    return {
        "access_token": access_token,
        "current_business_id": business_id,
        "message": "Business context switched successfully"
    }

@router.post("/register", response_model=schemas.User)
async def register_user(
    user: schemas.UserCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user)
):
    """Register a new user (admin only)."""
    # Check if username already exists
    db_user = db.query(models.User).filter(
        (models.User.username == user.username) | (models.User.email == user.email)
    ).first()
    if db_user:
        raise HTTPException(
            status_code=400,
            detail="Username or email already registered"
        )
    
    return create_user(db=db, user=user)

@router.get("/me", response_model=schemas.User)
async def read_users_me(current_user: models.User = Depends(get_current_active_user)):
    """Get current user information."""
    return current_user

@router.get("/users", response_model=List[schemas.User])
async def read_users(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user)
):
    """Get all users (admin only)."""
    users = db.query(models.User).offset(skip).limit(limit).all()
    return users

@router.put("/users/{user_id}", response_model=schemas.User)
async def update_user(
    user_id: int,
    user_update: schemas.UserUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user)
):
    """Update a user (admin only)."""
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if db_user is None:
        raise HTTPException(status_code=404, detail="User not found")
    
    for field, value in user_update.dict(exclude_unset=True).items():
        setattr(db_user, field, value)
    
    db.commit()
    db.refresh(db_user)
    return db_user

@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user)
):
    """Delete a user (admin only)."""
    if user_id == current_user.id:
        raise HTTPException(
            status_code=400, 
            detail="Cannot delete your own account"
        )
    
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if db_user is None:
        raise HTTPException(status_code=404, detail="User not found")
    
    db.delete(db_user)
    db.commit()
    return {"message": "User deleted successfully"}

@router.post("/reset-database")
async def reset_database(
    db: Session = Depends(get_db)
):
    """Reset database and create default admin user (development only)."""
    try:
        # Drop all tables
        Base.metadata.drop_all(bind=engine)
        
        # Create all tables
        Base.metadata.create_all(bind=engine)
        
        # Install pgvector extension for embeddings
        from sqlalchemy import text
        try:
            with engine.connect() as connection:
                connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
                connection.commit()
        except Exception as e:
            logger.warning(f"pgvector installation warning: {e}")
        
        # Create default admin user
        admin_user = models.User(
            email="admin@ryvr.com",
            username="admin",
            hashed_password=get_password_hash("password"),
            full_name="Admin User",
            is_active=True,
            is_admin=True
        )
        
        db.add(admin_user)
        db.commit()
        
        return {
            "message": "Database reset successfully (with pgvector extension)",
            "admin_credentials": {
                "email": "admin@ryvr.com", 
                "username": "admin",
                "password": "password"
            }
        }
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to reset database: {str(e)}"
        )

@router.post("/init-database")
async def init_database(
    db: Session = Depends(get_db)
):
    """Initialize database with default admin user (development only)."""
    try:
        # Check if admin user already exists
        existing_admin = db.query(models.User).filter(
            (models.User.email == "admin@ryvr.com") | (models.User.username == "admin")
        ).first()
        
        if existing_admin:
            return {
                "message": "Admin user already exists",
                "admin_credentials": {
                    "email": "admin@ryvr.com", 
                    "username": "admin",
                    "password": "password"
                }
            }
        
        # Create default admin user
        admin_user = models.User(
            email="admin@ryvr.com",
            username="admin",
            hashed_password=get_password_hash("password"),
            full_name="Admin User",
            is_active=True,
            is_admin=True
        )
        
        db.add(admin_user)
        db.commit()
        
        return {
            "message": "Admin user created successfully",
            "admin_credentials": {
                "email": "admin@ryvr.com", 
                "username": "admin",
                "password": "password"
            }
        }
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to initialize database: {str(e)}"
        )

# =============================================================================
# MULTI-TENANT CONTEXT ENDPOINTS (NEW)
# =============================================================================

@router.get("/context", response_model=schemas.BusinessContext)
async def get_user_context(
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get current user's business and agency context."""
    agencies = get_user_agencies(db, current_user)
    businesses = get_user_businesses(db, current_user)
    
    if not agencies:
        raise HTTPException(
            status_code=404,
            detail="No agencies found for user"
        )
    
    # Return first available context
    agency = agencies[0]
    business = businesses[0] if businesses else None
    
    if not business:
        raise HTTPException(
            status_code=404,
            detail="No businesses found for user"
        )
    
    return {
        "business_id": business.id,
        "business_name": business.name,
        "agency_id": agency.id,
        "agency_name": agency.name,
        "user_role": current_user.role,
        "permissions": {}  # TODO: Add actual permissions
    }

@router.post("/switch-business", response_model=schemas.LoginResponse)
async def switch_business_context(
    request: schemas.BusinessSwitchRequest,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Switch to a different business context."""
    # Verify user has access to this business
    if not verify_business_access(db, current_user, request.business_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to this business is not allowed"
        )
    
    # Get business and agency
    business = db.query(models.Business).filter(
        models.Business.id == request.business_id
    ).first()
    
    if not business:
        raise HTTPException(
            status_code=404,
            detail="Business not found"
        )
    
    # Create new token with updated context
    access_token = create_login_token(current_user, business.agency_id, business.id)
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": current_user,
        "agency_id": business.agency_id,
        "business_id": business.id
    }

@router.get("/agencies", response_model=List[schemas.Agency])
async def get_user_agencies_endpoint(
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get all agencies accessible by current user."""
    agencies = get_user_agencies(db, current_user)
    return agencies

@router.get("/businesses", response_model=List[schemas.Business])
async def get_user_businesses_endpoint(
    agency_id: Optional[int] = None,
    current_user: models.User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get all businesses accessible by current user."""
    businesses = get_user_businesses(db, current_user, agency_id)
    return businesses

@router.post("/agency/register", response_model=schemas.Agency)
async def register_agency(
    agency_data: schemas.AgencyCreate,
    db: Session = Depends(get_db)
):
    """Register a new agency (open registration)."""
    # Check if slug already exists
    existing_agency = db.query(models.Agency).filter(
        models.Agency.slug == agency_data.slug
    ).first()
    
    if existing_agency:
        raise HTTPException(
            status_code=400,
            detail="Agency slug already exists"
        )
    
    # Create agency user first
    agency_user = models.User(
        email=agency_data.name.lower().replace(" ", "") + "@temp.com",  # Temporary email
        username=agency_data.slug + "_owner",
        hashed_password=get_password_hash("temp_password"),  # Will be updated
        role="agency",
        first_name="Agency",
        last_name="Owner",
        is_active=True
    )
    
    db.add(agency_user)
    db.commit()
    db.refresh(agency_user)
    
    # Create agency
    agency = models.Agency(
        name=agency_data.name,
        slug=agency_data.slug,
        website=agency_data.website,
        phone=agency_data.phone,
        address=agency_data.address,
        branding_config=agency_data.branding_config or {},
        settings=agency_data.settings or {},
        created_by=agency_user.id,
        is_active=True
    )
    
    db.add(agency)
    db.commit()
    db.refresh(agency)
    
    # Link user to agency as owner
    agency_membership = models.AgencyUser(
        agency_id=agency.id,
        user_id=agency_user.id,
        role="owner",
        joined_at=datetime.utcnow(),
        is_active=True
    )
    
    db.add(agency_membership)
    
    # Get starter tier for trial
    starter_tier = db.query(models.SubscriptionTier).filter(
        models.SubscriptionTier.slug == "starter"
    ).first()
    
    if starter_tier:
        # Create trial subscription
        trial_subscription = models.UserSubscription(
            user_id=agency_user.id,
            tier_id=starter_tier.id,
            status="trial",
            trial_starts_at=datetime.utcnow(),
            trial_ends_at=datetime.utcnow() + timedelta(days=14)
        )
        
        db.add(trial_subscription)
        
        # Create credit pool with trial credits
        credit_pool = models.CreditPool(
            owner_id=agency.id,
            owner_type="agency",
            balance=5000,  # Trial credits
            total_purchased=5000,
            overage_threshold=100
        )
        
        db.add(credit_pool)
    
    db.commit()
    db.refresh(agency)
    
    return agency 