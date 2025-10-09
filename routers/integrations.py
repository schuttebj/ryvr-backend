"""
Enhanced Multi-Tier Integration System
Supports System, Agency, and Business level integrations with preserved functionality
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import datetime
import logging

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

# Configure logger
logger = logging.getLogger(__name__)

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
# SYSTEM-LEVEL INTEGRATIONS (ADMIN MANAGED CONFIGURATIONS)
# =============================================================================

@router.get("/system", response_model=List[schemas.SystemIntegration])
async def get_system_integrations(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user)
):
    """Get all system-level integration configurations (admin only)."""
    integrations = db.query(models.SystemIntegration).filter(
        models.SystemIntegration.is_active == True
    ).all()
    return integrations

@router.post("/system", response_model=schemas.SystemIntegration)
async def create_system_integration(
    integration_data: schemas.SystemIntegrationCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user)
):
    """Configure a system-level integration (admin only)."""
    
    # Verify the base integration exists
    base_integration = db.query(models.Integration).filter(
        models.Integration.id == integration_data.integration_id,
        models.Integration.is_active == True
    ).first()
    
    if not base_integration:
        raise HTTPException(
            status_code=404,
            detail="Integration not found"
        )
    
    # Check if system integration already exists
    existing = db.query(models.SystemIntegration).filter(
        models.SystemIntegration.integration_id == integration_data.integration_id
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=400,
            detail="System integration already configured for this integration"
        )
    
    # Create system integration
    db_integration = models.SystemIntegration(**integration_data.dict())
    db.add(db_integration)
    db.commit()
    db.refresh(db_integration)
    
    return db_integration

@router.put("/system/{integration_id}", response_model=schemas.SystemIntegration)
async def update_system_integration(
    integration_id: int,
    integration_data: schemas.SystemIntegrationCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user)
):
    """Update a system-level integration (admin only)."""
    
    # Get existing system integration
    db_integration = db.query(models.SystemIntegration).filter(
        models.SystemIntegration.integration_id == integration_id
    ).first()
    
    if not db_integration:
        raise HTTPException(status_code=404, detail="System integration not found")
    
    # Update fields
    for field, value in integration_data.dict().items():
        setattr(db_integration, field, value)
    
    db.commit()
    db.refresh(db_integration)
    
    return db_integration

@router.delete("/system/{integration_id}")
async def delete_system_integration(
    integration_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user)
):
    """Delete a system-level integration (admin only)."""
    
    db_integration = db.query(models.SystemIntegration).filter(
        models.SystemIntegration.integration_id == integration_id
    ).first()
    
    if not db_integration:
        raise HTTPException(status_code=404, detail="System integration not found")
    
    db.delete(db_integration)
    db.commit()
    
    return {"message": "System integration deleted successfully"}

@router.post("/{integration_id}/toggle-system", response_model=Dict[str, Any])
async def toggle_system_integration(
    integration_id: int,
    request_data: Dict[str, Any] = {},
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user)
):
    """Toggle system integration status (admin only)"""
    
    # Verify the base integration exists
    base_integration = db.query(models.Integration).filter(
        models.Integration.id == integration_id,
        models.Integration.is_active == True
    ).first()
    
    if not base_integration:
        raise HTTPException(status_code=404, detail="Integration not found")
    
    # Check if system integration already exists
    existing_system_integration = db.query(models.SystemIntegration).filter(
        models.SystemIntegration.integration_id == integration_id
    ).first()
    
    if existing_system_integration:
        # Toggle off - remove system integration
        db.delete(existing_system_integration)
        db.commit()
        
        return {
            "success": True,
            "action": "disabled",
            "message": f"{base_integration.name} removed from system integrations",
            "is_system_integration": False
        }
    else:
        # Toggle on - create system integration
        credentials = request_data.get("credentials", {})
        custom_config = request_data.get("custom_config", {})
        
        if not credentials and base_integration.name.lower() == "openai":
            # For OpenAI, require API key
            raise HTTPException(
                status_code=400, 
                detail="OpenAI API key is required in credentials field"
            )
        
        system_integration = models.SystemIntegration(
            integration_id=integration_id,
            credentials=credentials,
            custom_config=custom_config,
            is_active=True
        )
        
        db.add(system_integration)
        db.commit()
        db.refresh(system_integration)
        
        return {
            "success": True,
            "action": "enabled",
            "message": f"{base_integration.name} configured as system integration",
            "is_system_integration": True,
            "system_integration_id": system_integration.id
        }

@router.get("/{integration_id}/system-status", response_model=Dict[str, Any])
async def get_system_integration_status(
    integration_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user)
):
    """Get system integration status for an integration (admin only)"""
    
    # Check if system integration exists
    system_integration = db.query(models.SystemIntegration).filter(
        models.SystemIntegration.integration_id == integration_id,
        models.SystemIntegration.is_active == True
    ).first()
    
    return {
        "integration_id": integration_id,
        "is_system_integration": system_integration is not None,
        "system_integration_id": system_integration.id if system_integration else None,
        "has_credentials": bool(system_integration.credentials) if system_integration else False
    }

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
# WORDPRESS-SPECIFIC ENDPOINTS
# =============================================================================

@router.post("/business/{business_id}/wordpress/register")
async def register_wordpress_site(
    business_id: int,
    site_data: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Register a WordPress site with RYVR business integration"""
    if not verify_business_access(db, current_user, business_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to this business denied"
        )
    
    try:
        # Get WordPress integration definition
        wordpress_integration = db.query(models.Integration).filter(
            models.Integration.provider == "wordpress",
            models.Integration.is_active == True
        ).first()
        
        if not wordpress_integration:
            raise HTTPException(
                status_code=404,
                detail="WordPress integration not found"
            )
        
        # Check if WordPress integration already exists for this business
        existing = db.query(models.BusinessIntegration).filter(
            models.BusinessIntegration.business_id == business_id,
            models.BusinessIntegration.integration_id == wordpress_integration.id
        ).first()
        
        # Prepare configuration
        custom_config = {
            'site_url': site_data.get('url'),
            'site_name': site_data.get('name'),
            'wordpress_version': site_data.get('wordpress_version'),
            'plugin_version': site_data.get('plugin_version'),
            'supported_post_types': site_data.get('supported_post_types', []),
            'acf_active': site_data.get('acf_active', False),
            'rankmath_active': site_data.get('rankmath_active', False),
            'sync_capabilities': site_data.get('sync_capabilities', {}),
            'sync_post_types': site_data.get('sync_post_types', ['post', 'page']),
            'sync_acf_fields': site_data.get('sync_acf_fields', True),
            'sync_rankmath_data': site_data.get('sync_rankmath_data', True),
            'sync_taxonomies': site_data.get('sync_taxonomies', True),
            'two_way_sync': site_data.get('two_way_sync', True),
            'registered_at': datetime.utcnow().isoformat()
        }
        
        # Generate API key for WordPress plugin
        import secrets
        api_key = f"ryvr_wp_{secrets.token_urlsafe(32)}"
        
        credentials = {
            'api_key': api_key,
            'site_url': site_data.get('url'),
            'admin_url': site_data.get('admin_url')
        }
        
        if existing:
            # Update existing integration
            existing.custom_config = custom_config
            existing.credentials = credentials
            existing.is_active = True
            existing.last_tested = datetime.utcnow()
            db.commit()
            db.refresh(existing)
            business_integration = existing
        else:
            # Create new business integration
            business_integration = models.BusinessIntegration(
                business_id=business_id,
                integration_id=wordpress_integration.id,
                custom_config=custom_config,
                credentials=credentials,
                is_active=True
            )
            db.add(business_integration)
            db.commit()
            db.refresh(business_integration)
        
        return {
            "success": True,
            "message": "WordPress site registered successfully",
            "integration_id": business_integration.id,
            "api_key": api_key,
            "business_id": business_id,
            "site_url": site_data.get('url'),
            "registered": True
        }
        
    except Exception as e:
        logger.error(f"Failed to register WordPress site: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to register WordPress site: {str(e)}"
        )

@router.get("/business/{business_id}/wordpress/content")
async def get_wordpress_content(
    business_id: int,
    content_id: Optional[str] = None,
    post_type: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Get content from RYVR to be published to WordPress"""
    if not verify_business_access(db, current_user, business_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to this business denied"
        )
    
    try:
        # This would typically get content from RYVR's content management system
        # For now, return a placeholder structure
        content_items = []
        
        # TODO: Implement actual content retrieval from RYVR's content system
        # This might involve querying generated content, AI outputs, etc.
        
        return {
            "success": True,
            "data": content_items,
            "total": len(content_items),
            "business_id": business_id
        }
        
    except Exception as e:
        logger.error(f"Failed to get WordPress content: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get content: {str(e)}"
        )

@router.post("/business/{business_id}/wordpress/content")
async def wordpress_content_operation(
    business_id: int,
    content_data: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Handle WordPress content operations - both receiving from and publishing to WordPress"""
    if not verify_business_access(db, current_user, business_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to this business denied"
        )
    
    try:
        # Check if this is a publishing request (from RYVR workflow to WordPress)
        if all(key in content_data for key in ['title', 'content', 'post_type']):
            # This is a publish operation - RYVR is publishing TO WordPress
            logger.info(f"Publishing content to WordPress for business {business_id}: {content_data.get('title', 'Untitled')}")
            
            # Get WordPress integration for this business
            integration_service = IntegrationService(db)
            try:
                result = await integration_service.execute_integration(
                    integration_name="wordpress",
                    business_id=business_id,
                    node_config={"operation": "publish_content"},
                    input_data=content_data,
                    user_id=current_user.id
                )
                
                return {
                    "success": True,
                    "message": "Content published successfully to WordPress",
                    "post": result.get("post", {}),
                    "operation": "publish",
                    "business_id": business_id
                }
                
            except Exception as integration_error:
                logger.error(f"WordPress integration error: {integration_error}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to publish to WordPress: {str(integration_error)}"
                )
        
        else:
            # This is a receive operation - WordPress is sending content TO RYVR
            operation = content_data.get('operation', 'create')
            content = content_data.get('content', {})
            
            logger.info(f"Receiving WordPress content {operation} for business {business_id}: {content.get('title', 'Untitled')}")
            
            # TODO: Process and store the WordPress content in RYVR's content system
            # This might involve:
            # - Storing in a content table
            # - Triggering workflows
            # - Processing ACF and SEO data
            # - Creating content relationships
            
            # For now, acknowledge receipt
            return {
                "success": True,
                "message": f"Content {operation} processed successfully",
                "ryvr_post_id": f"ryvr_{business_id}_{content.get('wordpress_post_id', 'unknown')}",
                "operation": operation,
                "business_id": business_id
            }
        
    except Exception as e:
        logger.error(f"Failed to process WordPress content: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process content: {str(e)}"
        )

@router.post("/business/{business_id}/wordpress/webhook")
async def wordpress_webhook(
    business_id: int,
    webhook_data: Dict[str, Any],
    db: Session = Depends(get_db)
):
    """Handle webhooks from WordPress plugin (no auth required for webhooks)"""
    try:
        event = webhook_data.get('event')
        post_id = webhook_data.get('post_id')
        change_type = webhook_data.get('change_type')
        
        logger.info(f"WordPress webhook: {event} for business {business_id}, post {post_id}, change: {change_type}")
        
        # TODO: Process webhook events
        # This might involve:
        # - Triggering automatic syncs
        # - Notifying users
        # - Updating content status
        # - Logging changes
        
        return {
            "success": True,
            "message": "Webhook processed successfully",
            "event": event,
            "business_id": business_id
        }
        
    except Exception as e:
        logger.error(f"Failed to process WordPress webhook: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process webhook: {str(e)}"
        )

@router.get("/business/{business_id}/wordpress/status")
async def get_wordpress_integration_status(
    business_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Get WordPress integration status for a business"""
    if not verify_business_access(db, current_user, business_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to this business denied"
        )
    
    try:
        # Get WordPress integration
        wordpress_integration = db.query(models.Integration).filter(
            models.Integration.provider == "wordpress",
            models.Integration.is_active == True
        ).first()
        
        if not wordpress_integration:
            return {
                "configured": False,
                "message": "WordPress integration not available"
            }
        
        # Get business integration
        business_integration = db.query(models.BusinessIntegration).filter(
            models.BusinessIntegration.business_id == business_id,
            models.BusinessIntegration.integration_id == wordpress_integration.id,
            models.BusinessIntegration.is_active == True
        ).first()
        
        if not business_integration:
            return {
                "configured": False,
                "message": "WordPress not configured for this business"
            }
        
        config = business_integration.custom_config or {}
        
        return {
            "configured": True,
            "site_url": config.get('site_url'),
            "site_name": config.get('site_name'),
            "wordpress_version": config.get('wordpress_version'),
            "plugin_version": config.get('plugin_version'),
            "acf_active": config.get('acf_active', False),
            "rankmath_active": config.get('rankmath_active', False),
            "last_tested": business_integration.last_tested,
            "sync_capabilities": config.get('sync_capabilities', {}),
            "integration_id": business_integration.id
        }
        
    except Exception as e:
        logger.error(f"Failed to get WordPress status: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get status: {str(e)}"
        )

# =============================================================================
# DYNAMIC INTEGRATION BUILDER ENDPOINTS
# =============================================================================

@router.post("/builder/create")
async def create_dynamic_integration(
    integration_data: schemas.IntegrationBuilderCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user)
):
    """Create a new integration via Integration Builder (admin only)"""
    try:
        # Create integration record
        db_integration = models.Integration(
            name=integration_data.name,
            provider=integration_data.provider.lower().replace(" ", "_"),
            integration_type=integration_data.integration_type,
            level=integration_data.level,
            is_system_wide=integration_data.is_system_wide,
            requires_user_config=integration_data.requires_user_config,
            is_dynamic=True,  # Mark as dynamically configured
            platform_config=integration_data.platform_config,
            auth_config=integration_data.auth_config,
            oauth_config=integration_data.oauth_config,
            operation_configs={"operations": [op.dict() for op in integration_data.operations]},
            is_active=True
        )
        
        db.add(db_integration)
        db.commit()
        db.refresh(db_integration)
        
        logger.info(f"Created dynamic integration: {integration_data.name} (ID: {db_integration.id})")
        
        return {
            "success": True,
            "integration_id": db_integration.id,
            "message": f"Integration '{integration_data.name}' created successfully",
            "integration": db_integration
        }
        
    except Exception as e:
        logger.error(f"Failed to create dynamic integration: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create integration: {str(e)}"
        )

@router.put("/builder/{integration_id}")
async def update_dynamic_integration(
    integration_id: int,
    integration_data: schemas.IntegrationBuilderUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user)
):
    """Update an integration via Integration Builder (admin only)"""
    try:
        db_integration = db.query(models.Integration).filter(
            models.Integration.id == integration_id
        ).first()
        
        if not db_integration:
            raise HTTPException(status_code=404, detail="Integration not found")
        
        # Update fields
        if integration_data.name:
            db_integration.name = integration_data.name
        if integration_data.platform_config:
            db_integration.platform_config = integration_data.platform_config
        if integration_data.auth_config:
            db_integration.auth_config = integration_data.auth_config
        if integration_data.oauth_config:
            db_integration.oauth_config = integration_data.oauth_config
        if integration_data.operations:
            db_integration.operation_configs = {"operations": [op.dict() for op in integration_data.operations]}
        if integration_data.is_system_wide is not None:
            db_integration.is_system_wide = integration_data.is_system_wide
        if integration_data.requires_user_config is not None:
            db_integration.requires_user_config = integration_data.requires_user_config
        if integration_data.is_active is not None:
            db_integration.is_active = integration_data.is_active
        
        db_integration.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(db_integration)
        
        logger.info(f"Updated dynamic integration: {db_integration.name} (ID: {integration_id})")
        
        return {
            "success": True,
            "integration_id": integration_id,
            "message": f"Integration '{db_integration.name}' updated successfully",
            "integration": db_integration
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update dynamic integration: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update integration: {str(e)}"
        )

@router.post("/builder/parse-docs")
async def parse_api_documentation(
    parse_request: schemas.IntegrationParseRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user)
):
    """Parse API documentation using AI (admin only)"""
    try:
        from services.integration_parser_service import IntegrationParserService
        
        # Get OpenAI API key from system integration
        openai_key = None
        openai_integration = db.query(models.Integration).filter(
            models.Integration.name == "OpenAI",
            models.Integration.is_active == True
        ).first()
        
        if openai_integration:
            system_integration = db.query(models.SystemIntegration).filter(
                models.SystemIntegration.integration_id == openai_integration.id
            ).first()
            if system_integration:
                openai_key = system_integration.credentials.get("api_key")
        
        if not openai_key:
            raise HTTPException(
                status_code=400,
                detail="OpenAI API key not configured. Please configure OpenAI system integration first."
            )
        
        # Parse documentation
        parser = IntegrationParserService(api_key=openai_key)
        result = await parser.parse_documentation(
            platform_name=parse_request.platform_name,
            documentation=parse_request.documentation,
            instructions=parse_request.instructions
        )
        
        if not result.get("success"):
            return result
        
        # Validate parsed config
        config = result["config"]
        validation = parser.validate_parsed_config(config)
        
        return {
            "success": True,
            "config": config,
            "validation": validation,
            "tokens_used": result.get("tokens_used", 0)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to parse documentation: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to parse documentation: {str(e)}"
        )

@router.post("/builder/{integration_id}/operations/{operation_id}/test")
async def test_integration_operation(
    integration_id: int,
    operation_id: str,
    test_request: schemas.IntegrationOperationTest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user)
):
    """Test a specific integration operation with live API call (admin only)"""
    try:
        from services.dynamic_integration_service import DynamicIntegrationService
        
        # Use business_id from request or default to first business
        business_id = test_request.business_id
        if not business_id:
            # Get first business for testing
            business = db.query(models.Business).first()
            if not business:
                raise HTTPException(
                    status_code=400,
                    detail="No business found for testing. Please specify business_id."
                )
            business_id = business.id
        
        # Execute operation
        service = DynamicIntegrationService(db)
        result = await service.execute_operation(
            integration_id=integration_id,
            operation_id=operation_id,
            business_id=business_id,
            parameters=test_request.test_parameters,
            user_id=current_user.id
        )
        
        return {
            "success": result.get("success", False),
            "data": result.get("data", {}),
            "raw_response": result.get("raw_response", {}),
            "error": result.get("error"),
            "credits_used": result.get("credits_used", 0)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to test operation: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to test operation: {str(e)}"
        )

@router.get("/{integration_id}/operations")
async def get_integration_operations(
    integration_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Get all operations for an integration (for workflow builder)"""
    try:
        integration = db.query(models.Integration).filter(
            models.Integration.id == integration_id,
            models.Integration.is_active == True
        ).first()
        
        if not integration:
            raise HTTPException(status_code=404, detail="Integration not found")
        
        operations = integration.operation_configs.get("operations", [])
        
        return {
            "integration_id": integration_id,
            "integration_name": integration.name,
            "platform_config": integration.platform_config,
            "auth_config": integration.auth_config,
            "operations": operations
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get operations: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get operations: {str(e)}"
        )

# =============================================================================
# OAUTH ENDPOINTS
# =============================================================================

@router.get("/oauth/authorize/{integration_id}")
async def start_oauth_flow(
    integration_id: int,
    business_id: int,
    redirect_uri: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Start OAuth authorization flow"""
    try:
        from services.oauth_service import OAuthService
        
        # Verify business access
        if not verify_business_access(db, current_user, business_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access to this business denied"
            )
        
        oauth_service = OAuthService(db)
        result = oauth_service.generate_authorization_url(
            integration_id=integration_id,
            business_id=business_id,
            redirect_uri=redirect_uri,
            user_id=current_user.id
        )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start OAuth flow: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start OAuth flow: {str(e)}"
        )

@router.get("/oauth/callback")
async def oauth_callback(
    code: str,
    state: str,
    db: Session = Depends(get_db)
):
    """Handle OAuth callback (no auth required as this is callback from provider)"""
    try:
        from services.oauth_service import OAuthService
        
        # Get redirect URI from environment or config
        from config import settings
        backend_url = getattr(settings, 'backend_url', 'http://localhost:8000')
        redirect_uri = f"{backend_url}/api/v1/integrations/oauth/callback"
        
        oauth_service = OAuthService(db)
        result = await oauth_service.handle_callback(
            code=code,
            state=state,
            redirect_uri=redirect_uri
        )
        
        if result.get("success"):
            # Redirect to frontend success page
            frontend_url = getattr(settings, 'frontend_url', 'http://localhost:5173')
            return {
                "success": True,
                "message": f"Successfully connected {result.get('integration_name')}",
                "redirect_url": f"{frontend_url}/integrations?success=true&integration={result.get('integration_name')}"
            }
        else:
            return result
        
    except Exception as e:
        logger.error(f"OAuth callback failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"OAuth callback failed: {str(e)}"
        )

@router.post("/business/{business_id}/oauth/disconnect/{integration_id}")
async def disconnect_oauth_integration(
    business_id: int,
    integration_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Disconnect OAuth integration"""
    try:
        if not verify_business_access(db, current_user, business_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access to this business denied"
            )
        
        from services.oauth_service import OAuthService
        
        oauth_service = OAuthService(db)
        success = oauth_service.disconnect_integration(business_id, integration_id)
        
        if success:
            return {
                "success": True,
                "message": "Integration disconnected successfully"
            }
        else:
            return {
                "success": False,
                "message": "Integration not found or already disconnected"
            }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to disconnect integration: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to disconnect integration: {str(e)}"
        )

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