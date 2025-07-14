from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from database import get_db
from auth import get_current_active_user, get_current_admin_user
import models, schemas

router = APIRouter()

@router.get("/", response_model=List[schemas.Integration])
async def read_integrations(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Get all available integrations."""
    integrations = db.query(models.Integration).filter(
        models.Integration.is_active == True
    ).offset(skip).limit(limit).all()
    return integrations

@router.post("/", response_model=schemas.Integration)
async def create_integration(
    integration: schemas.IntegrationCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user)
):
    """Create a new integration (admin only)."""
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
    """Get a specific integration."""
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
    """Update an integration (admin only)."""
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
    """Delete an integration (admin only)."""
    db_integration = db.query(models.Integration).filter(
        models.Integration.id == integration_id
    ).first()
    if db_integration is None:
        raise HTTPException(status_code=404, detail="Integration not found")
    
    db.delete(db_integration)
    db.commit()
    return {"message": "Integration deleted successfully"}

@router.get("/{integration_id}/tasks", response_model=List[schemas.TaskTemplate])
async def read_integration_tasks(
    integration_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Get all task templates for an integration."""
    tasks = db.query(models.TaskTemplate).filter(
        models.TaskTemplate.integration_id == integration_id,
        models.TaskTemplate.is_active == True
    ).all()
    return tasks

@router.post("/test")
async def test_integration(
    integration_id: int,
    test_data: dict,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Test an integration with sample data."""
    integration = db.query(models.Integration).filter(
        models.Integration.id == integration_id
    ).first()
    if integration is None:
        raise HTTPException(status_code=404, detail="Integration not found")
    
    # For now, return mock success response
    # TODO: Implement actual integration testing
    return {
        "success": True,
        "message": f"Integration {integration.name} test completed",
        "test_data": test_data,
        "integration": integration.name
    } 