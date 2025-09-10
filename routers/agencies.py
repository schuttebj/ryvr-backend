"""
Agency Management Router
Handles agency CRUD operations, user management, and agency-level features
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from database import get_db
from auth import (
    get_current_active_user,
    get_current_agency_user,
    get_current_admin_user,
    verify_agency_access,
    get_user_agencies,
    get_user_role_in_agency
)
import models, schemas

router = APIRouter(prefix="/api/v1/agencies", tags=["agencies"])

@router.get("/", response_model=List[schemas.Agency])
async def get_agencies(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Get agencies accessible by current user."""
    agencies = get_user_agencies(db, current_user)
    return agencies[skip:skip + limit]

@router.get("/{agency_id}", response_model=schemas.Agency)
async def get_agency(
    agency_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Get a specific agency."""
    if not verify_agency_access(db, current_user, agency_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to this agency denied"
        )
    
    agency = db.query(models.Agency).filter(
        models.Agency.id == agency_id
    ).first()
    
    if not agency:
        raise HTTPException(status_code=404, detail="Agency not found")
    
    return agency

@router.put("/{agency_id}", response_model=schemas.Agency)
async def update_agency(
    agency_id: int,
    agency_update: schemas.AgencyUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Update an agency."""
    if not verify_agency_access(db, current_user, agency_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to this agency denied"
        )
    
    # Check if user has permission to update
    user_role = get_user_role_in_agency(db, current_user, agency_id)
    if user_role not in ["owner", "manager", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to update agency"
        )
    
    agency = db.query(models.Agency).filter(
        models.Agency.id == agency_id
    ).first()
    
    if not agency:
        raise HTTPException(status_code=404, detail="Agency not found")
    
    # Update fields
    for field, value in agency_update.dict(exclude_unset=True).items():
        setattr(agency, field, value)
    
    db.commit()
    db.refresh(agency)
    return agency

# =============================================================================
# AGENCY USERS MANAGEMENT
# =============================================================================

@router.get("/{agency_id}/users", response_model=List[schemas.AgencyUser])
async def get_agency_users(
    agency_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Get users in an agency."""
    if not verify_agency_access(db, current_user, agency_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to this agency denied"
        )
    
    users = db.query(models.AgencyUser).filter(
        models.AgencyUser.agency_id == agency_id,
        models.AgencyUser.is_active == True
    ).all()
    
    return users

@router.post("/{agency_id}/users", response_model=schemas.AgencyUser)
async def add_agency_user(
    agency_id: int,
    user_data: schemas.AgencyUserCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Add a user to an agency."""
    if not verify_agency_access(db, current_user, agency_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to this agency denied"
        )
    
    # Check if current user has permission to add users
    user_role = get_user_role_in_agency(db, current_user, agency_id)
    if user_role not in ["owner", "manager", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to add users"
        )
    
    # Update user_data with agency_id
    user_data.agency_id = agency_id
    
    # Check if user already exists in agency
    existing = db.query(models.AgencyUser).filter(
        models.AgencyUser.agency_id == agency_id,
        models.AgencyUser.user_id == user_data.user_id
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=400,
            detail="User already exists in this agency"
        )
    
    # Create agency user relationship
    db_agency_user = models.AgencyUser(
        **user_data.dict(),
        invited_by=current_user.id,
        invited_at=datetime.utcnow()
    )
    
    db.add(db_agency_user)
    db.commit()
    db.refresh(db_agency_user)
    
    return db_agency_user

@router.put("/{agency_id}/users/{user_id}", response_model=schemas.AgencyUser)
async def update_agency_user(
    agency_id: int,
    user_id: int,
    user_update: schemas.AgencyUserBase,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Update a user's role in an agency."""
    if not verify_agency_access(db, current_user, agency_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to this agency denied"
        )
    
    # Check permissions
    current_user_role = get_user_role_in_agency(db, current_user, agency_id)
    if current_user_role not in ["owner", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only owners can update user roles"
        )
    
    agency_user = db.query(models.AgencyUser).filter(
        models.AgencyUser.agency_id == agency_id,
        models.AgencyUser.user_id == user_id
    ).first()
    
    if not agency_user:
        raise HTTPException(status_code=404, detail="User not found in agency")
    
    # Update fields
    for field, value in user_update.dict(exclude_unset=True).items():
        setattr(agency_user, field, value)
    
    db.commit()
    db.refresh(agency_user)
    return agency_user

@router.delete("/{agency_id}/users/{user_id}")
async def remove_agency_user(
    agency_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Remove a user from an agency."""
    if not verify_agency_access(db, current_user, agency_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to this agency denied"
        )
    
    # Check permissions
    current_user_role = get_user_role_in_agency(db, current_user, agency_id)
    if current_user_role not in ["owner", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only owners can remove users"
        )
    
    # Can't remove yourself if you're the owner
    if user_id == current_user.id and current_user_role == "owner":
        raise HTTPException(
            status_code=400,
            detail="Cannot remove yourself as owner"
        )
    
    agency_user = db.query(models.AgencyUser).filter(
        models.AgencyUser.agency_id == agency_id,
        models.AgencyUser.user_id == user_id
    ).first()
    
    if not agency_user:
        raise HTTPException(status_code=404, detail="User not found in agency")
    
    # Soft delete
    agency_user.is_active = False
    db.commit()
    
    return {"message": "User removed from agency"}

# =============================================================================
# AGENCY BUSINESSES
# =============================================================================

@router.get("/{agency_id}/businesses", response_model=List[schemas.Business])
async def get_agency_businesses(
    agency_id: int,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Get businesses in an agency."""
    if not verify_agency_access(db, current_user, agency_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to this agency denied"
        )
    
    businesses = db.query(models.Business).filter(
        models.Business.agency_id == agency_id,
        models.Business.is_active == True
    ).offset(skip).limit(limit).all()
    
    return businesses

# =============================================================================
# AGENCY INTEGRATIONS
# =============================================================================

@router.get("/{agency_id}/integrations", response_model=List[schemas.AgencyIntegration])
async def get_agency_integrations(
    agency_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Get integrations for agency."""
    if not verify_agency_access(db, current_user, agency_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to this agency denied"
        )
    
    integrations = db.query(models.AgencyIntegration).filter(
        models.AgencyIntegration.agency_id == agency_id,
        models.AgencyIntegration.is_active == True
    ).all()
    
    return integrations

@router.post("/{agency_id}/integrations", response_model=schemas.AgencyIntegration)
async def create_agency_integration(
    agency_id: int,
    integration: schemas.AgencyIntegrationCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Create an agency integration."""
    if not verify_agency_access(db, current_user, agency_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to this agency denied"
        )
    
    # Check permissions
    user_role = get_user_role_in_agency(db, current_user, agency_id)
    if user_role not in ["owner", "manager", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to manage integrations"
        )
    
    # Update integration data with agency_id
    integration.agency_id = agency_id
    
    # Check if integration already exists
    existing = db.query(models.AgencyIntegration).filter(
        models.AgencyIntegration.agency_id == agency_id,
        models.AgencyIntegration.integration_id == integration.integration_id
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=400,
            detail="Integration already exists for this agency"
        )
    
    db_integration = models.AgencyIntegration(**integration.dict())
    db.add(db_integration)
    db.commit()
    db.refresh(db_integration)
    
    return db_integration

# =============================================================================
# AGENCY STATISTICS
# =============================================================================

@router.get("/{agency_id}/stats", response_model=schemas.AgencyStats)
async def get_agency_stats(
    agency_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Get statistics for agency."""
    if not verify_agency_access(db, current_user, agency_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to this agency denied"
        )
    
    # Get business count
    total_businesses = db.query(models.Business).filter(
        models.Business.agency_id == agency_id,
        models.Business.is_active == True
    ).count()
    
    # Get credit usage across all businesses
    business_ids = [b.id for b in db.query(models.Business).filter(
        models.Business.agency_id == agency_id
    ).all()]
    
    credit_transactions = db.query(models.CreditTransaction).filter(
        models.CreditTransaction.business_id.in_(business_ids)
    ).all()
    
    total_credits_used = sum(abs(t.amount) for t in credit_transactions if t.amount < 0)
    
    # Get workflow stats
    active_workflows = db.query(models.WorkflowInstance).filter(
        models.WorkflowInstance.business_id.in_(business_ids),
        models.WorkflowInstance.is_active == True
    ).count()
    
    # Get execution stats
    total_executions = db.query(models.WorkflowExecution).filter(
        models.WorkflowExecution.business_id.in_(business_ids)
    ).count()
    
    successful_executions = db.query(models.WorkflowExecution).filter(
        models.WorkflowExecution.business_id.in_(business_ids),
        models.WorkflowExecution.status == "completed"
    ).count()
    
    success_rate = (successful_executions / total_executions * 100) if total_executions > 0 else 0
    
    return {
        "agency_id": agency_id,
        "total_businesses": total_businesses,
        "total_credits_used": total_credits_used,
        "active_workflows": active_workflows,
        "success_rate": success_rate
    }

# =============================================================================
# AGENCY CREDIT MANAGEMENT
# =============================================================================

@router.get("/{agency_id}/credits", response_model=schemas.CreditPool)
async def get_agency_credits(
    agency_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Get agency credit pool."""
    if not verify_agency_access(db, current_user, agency_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to this agency denied"
        )
    
    credit_pool = db.query(models.CreditPool).filter(
        models.CreditPool.owner_id == agency_id,
        models.CreditPool.owner_type == "agency"
    ).first()
    
    if not credit_pool:
        raise HTTPException(status_code=404, detail="Credit pool not found")
    
    return credit_pool

@router.get("/{agency_id}/credits/transactions", response_model=List[schemas.CreditTransaction])
async def get_agency_credit_transactions(
    agency_id: int,
    business_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Get credit transactions for agency."""
    if not verify_agency_access(db, current_user, agency_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to this agency denied"
        )
    
    # Get credit pool
    credit_pool = db.query(models.CreditPool).filter(
        models.CreditPool.owner_id == agency_id,
        models.CreditPool.owner_type == "agency"
    ).first()
    
    if not credit_pool:
        raise HTTPException(status_code=404, detail="Credit pool not found")
    
    query = db.query(models.CreditTransaction).filter(
        models.CreditTransaction.pool_id == credit_pool.id
    )
    
    # Filter by business if specified
    if business_id:
        query = query.filter(models.CreditTransaction.business_id == business_id)
    
    transactions = query.order_by(
        models.CreditTransaction.created_at.desc()
    ).offset(skip).limit(limit).all()
    
    return transactions
