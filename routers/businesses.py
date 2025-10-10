"""
Business Management Router
Handles business CRUD operations, onboarding, and management
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from database import get_db
from auth import (
    get_current_active_user,
    get_current_agency_user,
    verify_business_access,
    verify_agency_access,
    get_user_businesses
)
import models, schemas

router = APIRouter(prefix="/api/v1/businesses", tags=["businesses"])

@router.get("/onboarding/default", response_model=schemas.OnboardingTemplate)
async def get_default_business_onboarding_template(
    db: Session = Depends(get_db)
):
    """Get default business onboarding template (public endpoint for registration)."""
    template = db.query(models.OnboardingTemplate).filter(
        models.OnboardingTemplate.target_type == "business",
        models.OnboardingTemplate.is_default == True,
        models.OnboardingTemplate.is_active == True
    ).first()
    
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No default onboarding template found"
        )
    
    return template

@router.get("/", response_model=List[schemas.Business])
async def get_businesses(
    agency_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Get businesses accessible by current user."""
    businesses = get_user_businesses(db, current_user, agency_id)
    return businesses[skip:skip + limit]

@router.post("/", response_model=schemas.Business)
async def create_business(
    business: schemas.BusinessCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Create a new business."""
    # Verify user owns this business (or is admin)
    if business.owner_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only create businesses for yourself"
        )
    
    # Check if slug already exists for this owner
    if business.slug:
        existing_business = db.query(models.Business).filter(
            models.Business.owner_id == business.owner_id,
            models.Business.slug == business.slug
        ).first()
        
        if existing_business:
            raise HTTPException(
                status_code=400,
                detail="Business slug already exists for this owner"
            )
    
    # Create business
    db_business = models.Business(**business.dict())
    db.add(db_business)
    db.commit()
    db.refresh(db_business)
    
    return db_business

@router.get("/{business_id}", response_model=schemas.Business)
async def get_business(
    business_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Get a specific business."""
    if not verify_business_access(db, current_user, business_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to this business denied"
        )
    
    business = db.query(models.Business).filter(
        models.Business.id == business_id
    ).first()
    
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    
    return business

@router.put("/{business_id}", response_model=schemas.Business)
async def update_business(
    business_id: int,
    business_update: schemas.BusinessUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Update a business."""
    if not verify_business_access(db, current_user, business_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to this business denied"
        )
    
    business = db.query(models.Business).filter(
        models.Business.id == business_id
    ).first()
    
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    
    # Update fields
    for field, value in business_update.dict(exclude_unset=True).items():
        setattr(business, field, value)
    
    db.commit()
    db.refresh(business)
    return business

@router.delete("/{business_id}")
async def delete_business(
    business_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Delete a business (soft delete)."""
    if not verify_business_access(db, current_user, business_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to this business denied"
        )
    
    business = db.query(models.Business).filter(
        models.Business.id == business_id
    ).first()
    
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    
    # Soft delete
    business.is_active = False
    db.commit()
    
    return {"message": "Business deleted successfully"}

# =============================================================================
# ONBOARDING ENDPOINTS
# =============================================================================

@router.get("/{business_id}/onboarding", response_model=schemas.OnboardingTemplate)
async def get_business_onboarding_template(
    business_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Get onboarding template for business."""
    if not verify_business_access(db, current_user, business_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to this business denied"
        )
    
    # Get default business onboarding template
    template = db.query(models.OnboardingTemplate).filter(
        models.OnboardingTemplate.target_type == "business",
        models.OnboardingTemplate.is_default == True,
        models.OnboardingTemplate.is_active == True
    ).first()
    
    if not template:
        raise HTTPException(
            status_code=404,
            detail="No onboarding template found"
        )
    
    return template

@router.post("/{business_id}/onboarding", response_model=List[schemas.OnboardingResponse])
async def submit_business_onboarding(
    business_id: int,
    responses: List[schemas.OnboardingResponseCreate],
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Submit onboarding responses for business."""
    if not verify_business_access(db, current_user, business_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to this business denied"
        )
    
    business = db.query(models.Business).filter(
        models.Business.id == business_id
    ).first()
    
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    
    # Create responses
    db_responses = []
    completed_responses = {}
    
    for response_data in responses:
        # Update the response data with business info
        response_data.respondent_id = business_id
        response_data.respondent_type = "business"
        
        db_response = models.OnboardingResponse(**response_data.dict())
        db.add(db_response)
        db_responses.append(db_response)
        
        # Collect for business profile update
        question = db.query(models.OnboardingQuestion).filter(
            models.OnboardingQuestion.id == response_data.question_id
        ).first()
        
        if question:
            if question.section not in completed_responses:
                completed_responses[question.section] = {}
            completed_responses[question.section][question.question_key] = response_data.response_value
    
    # Update business onboarding data
    business.onboarding_data = {**business.onboarding_data, **completed_responses}
    
    db.commit()
    
    for response in db_responses:
        db.refresh(response)
    
    return db_responses

@router.get("/{business_id}/onboarding/responses", response_model=List[schemas.OnboardingResponse])
async def get_business_onboarding_responses(
    business_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Get onboarding responses for business."""
    if not verify_business_access(db, current_user, business_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to this business denied"
        )
    
    responses = db.query(models.OnboardingResponse).filter(
        models.OnboardingResponse.respondent_id == business_id,
        models.OnboardingResponse.respondent_type == "business"
    ).all()
    
    return responses

# =============================================================================
# INTEGRATIONS ENDPOINTS
# =============================================================================

@router.get("/{business_id}/integrations", response_model=List[schemas.BusinessIntegration])
async def get_business_integrations(
    business_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Get integrations for business."""
    if not verify_business_access(db, current_user, business_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to this business denied"
        )
    
    integrations = db.query(models.BusinessIntegration).filter(
        models.BusinessIntegration.business_id == business_id,
        models.BusinessIntegration.is_active == True
    ).all()
    
    return integrations

@router.post("/{business_id}/integrations", response_model=schemas.BusinessIntegration)
async def create_business_integration(
    business_id: int,
    integration: schemas.BusinessIntegrationCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Create a business integration instance. Supports multiple named instances per integration."""
    if not verify_business_access(db, current_user, business_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to this business denied"
        )
    
    # Update integration data with business_id
    integration.business_id = business_id
    
    # Check if instance with this name already exists for this business+integration combination
    existing = db.query(models.BusinessIntegration).filter(
        models.BusinessIntegration.business_id == business_id,
        models.BusinessIntegration.integration_id == integration.integration_id,
        models.BusinessIntegration.instance_name == integration.instance_name
    ).first()
    
    if existing:
        # Update existing integration instance
        for key, value in integration.dict(exclude_unset=True).items():
            if key != 'id':  # Don't update ID
                setattr(existing, key, value)
        db.commit()
        db.refresh(existing)
        return existing
    
    # Create new integration instance
    db_integration = models.BusinessIntegration(**integration.dict())
    db.add(db_integration)
    db.commit()
    db.refresh(db_integration)
    
    return db_integration

# =============================================================================
# WORKFLOW INSTANCES ENDPOINTS
# =============================================================================

@router.get("/{business_id}/workflows", response_model=List[schemas.WorkflowInstance])
async def get_business_workflows(
    business_id: int,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Get workflow instances for business."""
    if not verify_business_access(db, current_user, business_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to this business denied"
        )
    
    instances = db.query(models.WorkflowInstance).filter(
        models.WorkflowInstance.business_id == business_id,
        models.WorkflowInstance.is_active == True
    ).offset(skip).limit(limit).all()
    
    return instances

# =============================================================================
# STATISTICS ENDPOINTS
# =============================================================================

@router.get("/{business_id}/stats", response_model=schemas.BusinessStats)
async def get_business_stats(
    business_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Get statistics for business."""
    if not verify_business_access(db, current_user, business_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to this business denied"
        )
    
    # Get credit usage
    credit_transactions = db.query(models.CreditTransaction).filter(
        models.CreditTransaction.business_id == business_id
    ).all()
    
    credits_used = sum(abs(t.amount) for t in credit_transactions if t.amount < 0)
    
    # Get workflow stats
    active_workflows = db.query(models.WorkflowInstance).filter(
        models.WorkflowInstance.business_id == business_id,
        models.WorkflowInstance.is_active == True
    ).count()
    
    total_executions = db.query(models.WorkflowExecution).filter(
        models.WorkflowExecution.business_id == business_id
    ).count()
    
    successful_executions = db.query(models.WorkflowExecution).filter(
        models.WorkflowExecution.business_id == business_id,
        models.WorkflowExecution.status == "completed"
    ).count()
    
    success_rate = (successful_executions / total_executions * 100) if total_executions > 0 else 0
    
    return {
        "business_id": business_id,
        "credits_used": credits_used,
        "active_workflows": active_workflows,
        "total_executions": total_executions,
        "success_rate": success_rate
    }
