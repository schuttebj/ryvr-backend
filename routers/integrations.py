"""
Enhanced Multi-Tier Integration System
Supports System, Agency, and Business level integrations with preserved functionality
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import datetime

from database import get_db
from auth import (
    get_current_active_user, 
    get_current_admin_user,
    get_current_agency_user,
    verify_business_access,
    verify_agency_access,
    get_user_businesses,
    get_user_agencies
)
import models, schemas
from services.integration_service import IntegrationService

router = APIRouter()

# =============================================================================
# SYSTEM-LEVEL INTEGRATIONS (ADMIN MANAGED)
# =============================================================================

@router.get("/", response_model=List[schemas.Integration])
async def read_integrations(
    integration_type: Optional[str] = None,
    level: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Get all available integrations based on user access level."""
    query = db.query(models.Integration).filter(
        models.Integration.is_active == True
    )
    
    # Filter by integration type if specified
    if integration_type:
        query = query.filter(models.Integration.integration_type == integration_type)
    
    # Filter by level if specified
    if level:
        query = query.filter(models.Integration.level == level)
    
    # Non-admin users only see published integrations
    if current_user.role != "admin":
        query = query.filter(
            models.Integration.integration_type.in_(["system", "agency", "business"])
        )
    
    integrations = query.offset(skip).limit(limit).all()
    return integrations

@router.post("/", response_model=schemas.Integration)
async def create_integration(
    integration: schemas.IntegrationCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user)
):
    """Create a new system integration (admin only)."""
    db_integration = models.Integration(**integration.dict())
    db.add(db_integration)
    db.commit()
    db.refresh(db_integration)
    return db_integration

@router.get("/{integration_id}", response_model=schemas.Integration)
async def read_integration(
    integration_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Get a specific integration (preserved functionality)."""
    integration = db.query(models.Integration).filter(
        models.Integration.id == integration_id
    ).first()
    if integration is None:
        raise HTTPException(status_code=404, detail="Integration not found")
    return integration

@router.put("/{integration_id}", response_model=schemas.Integration)
async def update_integration(
    integration_id: int,
    integration_update: schemas.IntegrationUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user)
):
    """Update an integration (admin only, preserved functionality)."""
    db_integration = db.query(models.Integration).filter(
        models.Integration.id == integration_id
    ).first()
    if db_integration is None:
        raise HTTPException(status_code=404, detail="Integration not found")
    
    for field, value in integration_update.dict(exclude_unset=True).items():
        setattr(db_integration, field, value)
    
    db.commit()
    db.refresh(db_integration)
    return db_integration

@router.delete("/{integration_id}")
async def delete_integration(
    integration_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user)
):
    """Delete an integration (admin only, preserved functionality)."""
    db_integration = db.query(models.Integration).filter(
        models.Integration.id == integration_id
    ).first()
    if db_integration is None:
        raise HTTPException(status_code=404, detail="Integration not found")
    
    # Soft delete
    db_integration.is_active = False
    db.commit()
    return {"message": "Integration deleted successfully"}

@router.get("/{integration_id}/tasks", response_model=List[schemas.TaskTemplate])
async def read_integration_tasks(
    integration_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Get all task templates for an integration (preserved functionality)."""
    tasks = db.query(models.TaskTemplate).filter(
        models.TaskTemplate.integration_id == integration_id,
        models.TaskTemplate.is_active == True
    ).all()
    return tasks

# =============================================================================
# AGENCY-LEVEL INTEGRATIONS
# =============================================================================

@router.get("/agency/{agency_id}", response_model=List[schemas.AgencyIntegration])
async def get_agency_integrations(
    agency_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Get configured integrations for an agency."""
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

@router.post("/agency/{agency_id}", response_model=schemas.AgencyIntegration)
async def create_agency_integration(
    agency_id: int,
    integration_data: schemas.AgencyIntegrationCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_agency_user)
):
    """Configure an integration for an agency."""
    if not verify_agency_access(db, current_user, agency_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to this agency denied"
        )
    
    # Verify the base integration exists and is agency-configurable
    base_integration = db.query(models.Integration).filter(
        models.Integration.id == integration_data.integration_id,
        models.Integration.level.in_(["agency", "system"]),
        models.Integration.is_active == True
    ).first()
    
    if not base_integration:
        raise HTTPException(
            status_code=404,
            detail="Integration not found or not available for agency configuration"
        )
    
    # Check if integration already exists
    existing = db.query(models.AgencyIntegration).filter(
        models.AgencyIntegration.agency_id == agency_id,
        models.AgencyIntegration.integration_id == integration_data.integration_id
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=400,
            detail="Integration already configured for this agency"
        )
    
    # Create agency integration
    integration_data.agency_id = agency_id
    db_integration = models.AgencyIntegration(**integration_data.dict())
    db.add(db_integration)
    db.commit()
    db.refresh(db_integration)
    
    return db_integration

@router.put("/agency/{agency_id}/{integration_id}", response_model=schemas.AgencyIntegration)
async def update_agency_integration(
    agency_id: int,
    integration_id: int,
    integration_update: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_agency_user)
):
    """Update an agency integration configuration."""
    if not verify_agency_access(db, current_user, agency_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to this agency denied"
        )
    
    agency_integration = db.query(models.AgencyIntegration).filter(
        models.AgencyIntegration.agency_id == agency_id,
        models.AgencyIntegration.id == integration_id
    ).first()
    
    if not agency_integration:
        raise HTTPException(status_code=404, detail="Agency integration not found")
    
    # Update configuration
    if "custom_config" in integration_update:
        agency_integration.custom_config = integration_update["custom_config"]
    if "credentials" in integration_update:
        agency_integration.credentials = integration_update["credentials"]
    
    agency_integration.last_tested = datetime.utcnow()
    
    db.commit()
    db.refresh(agency_integration)
    
    return agency_integration

@router.post("/agency/{agency_id}/{integration_id}/test")
async def test_agency_integration(
    agency_id: int,
    integration_id: int,
    test_data: Optional[Dict[str, Any]] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_agency_user)
):
    """Test an agency integration."""
    if not verify_agency_access(db, current_user, agency_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to this agency denied"
        )
    
    agency_integration = db.query(models.AgencyIntegration).filter(
        models.AgencyIntegration.agency_id == agency_id,
        models.AgencyIntegration.id == integration_id,
        models.AgencyIntegration.is_active == True
    ).first()
    
    if not agency_integration:
        raise HTTPException(status_code=404, detail="Agency integration not found")
    
    # Use integration service to test
    integration_service = IntegrationService(db)
    result = await integration_service.test_agency_integration(
        agency_integration, test_data or {}
    )
    
    # Update last tested timestamp
    agency_integration.last_tested = datetime.utcnow()
    db.commit()
    
    return result

# =============================================================================
# BUSINESS-LEVEL INTEGRATIONS
# =============================================================================

@router.get("/business/{business_id}", response_model=List[schemas.BusinessIntegration])
async def get_business_integrations(
    business_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Get configured integrations for a business."""
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

@router.post("/business/{business_id}", response_model=schemas.BusinessIntegration)
async def create_business_integration(
    business_id: int,
    integration_data: schemas.BusinessIntegrationCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Configure an integration for a business."""
    if not verify_business_access(db, current_user, business_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to this business denied"
        )
    
    # Verify the base integration exists and is business-configurable
    base_integration = db.query(models.Integration).filter(
        models.Integration.id == integration_data.integration_id,
        models.Integration.level.in_(["business", "agency", "system"]),
        models.Integration.is_active == True
    ).first()
    
    if not base_integration:
        raise HTTPException(
            status_code=404,
            detail="Integration not found or not available for business configuration"
        )
    
    # Check if integration already exists
    existing = db.query(models.BusinessIntegration).filter(
        models.BusinessIntegration.business_id == business_id,
        models.BusinessIntegration.integration_id == integration_data.integration_id
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=400,
            detail="Integration already configured for this business"
        )
    
    # Create business integration
    integration_data.business_id = business_id
    db_integration = models.BusinessIntegration(**integration_data.dict())
    db.add(db_integration)
    db.commit()
    db.refresh(db_integration)
    
    return db_integration

@router.put("/business/{business_id}/{integration_id}", response_model=schemas.BusinessIntegration)
async def update_business_integration(
    business_id: int,
    integration_id: int,
    integration_update: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Update a business integration configuration."""
    if not verify_business_access(db, current_user, business_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to this business denied"
        )
    
    business_integration = db.query(models.BusinessIntegration).filter(
        models.BusinessIntegration.business_id == business_id,
        models.BusinessIntegration.id == integration_id
    ).first()
    
    if not business_integration:
        raise HTTPException(status_code=404, detail="Business integration not found")
    
    # Update configuration
    if "custom_config" in integration_update:
        business_integration.custom_config = integration_update["custom_config"]
    if "credentials" in integration_update:
        business_integration.credentials = integration_update["credentials"]
    
    business_integration.last_tested = datetime.utcnow()
    
    db.commit()
    db.refresh(business_integration)
    
    return business_integration

@router.post("/business/{business_id}/{integration_id}/test")
async def test_business_integration(
    business_id: int,
    integration_id: int,
    test_data: Optional[Dict[str, Any]] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Test a business integration."""
    if not verify_business_access(db, current_user, business_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to this business denied"
        )
    
    business_integration = db.query(models.BusinessIntegration).filter(
        models.BusinessIntegration.business_id == business_id,
        models.BusinessIntegration.id == integration_id,
        models.BusinessIntegration.is_active == True
    ).first()
    
    if not business_integration:
        raise HTTPException(status_code=404, detail="Business integration not found")
    
    # Use integration service to test
    integration_service = IntegrationService(db)
    result = await integration_service.test_business_integration(
        business_integration, test_data or {}
    )
    
    # Update last tested timestamp
    business_integration.last_tested = datetime.utcnow()
    db.commit()
    
    return result

# =============================================================================
# INTEGRATION EXECUTION (FOR WORKFLOWS)
# =============================================================================

@router.post("/execute")
async def execute_integration(
    execution_request: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Execute an integration for workflow nodes (preserved functionality)."""
    try:
        integration_service = IntegrationService(db)
        
        # Extract required parameters
        integration_name = execution_request.get("integration_name")
        business_id = execution_request.get("business_id")
        node_config = execution_request.get("node_config", {})
        input_data = execution_request.get("input_data", {})
        
        if not integration_name or not business_id:
            raise HTTPException(
                status_code=400,
                detail="integration_name and business_id are required"
            )
        
        # Verify business access
        if not verify_business_access(db, current_user, business_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access to this business denied"
            )
        
        # Execute integration
        result = await integration_service.execute_integration(
            integration_name=integration_name,
            business_id=business_id,
            node_config=node_config,
            input_data=input_data,
            user_id=current_user.id
        )
        
        return result
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Integration execution failed: {str(e)}"
        )

# =============================================================================
# AVAILABLE INTEGRATIONS (FOR FRONTEND)
# =============================================================================

@router.get("/available/{business_id}")
async def get_available_integrations(
    business_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Get all available integrations for a business (for workflow builder)."""
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
    
    integration_service = IntegrationService(db)
    available_integrations = integration_service.get_available_integrations(business_id)
    
    return {
        "business_id": business_id,
        "integrations": available_integrations
    }

# =============================================================================
# PRESERVED FUNCTIONALITY - LEGACY ENDPOINTS
# =============================================================================

@router.post("/test")
async def test_integration_legacy(
    integration_id: int,
    test_data: dict,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Test an integration with sample data (preserved functionality)."""
    integration = db.query(models.Integration).filter(
        models.Integration.id == integration_id
    ).first()
    if integration is None:
        raise HTTPException(status_code=404, detail="Integration not found")
    
    # Use integration service for actual testing
    integration_service = IntegrationService(db)
    result = await integration_service.test_system_integration(integration, test_data)
    
    return result