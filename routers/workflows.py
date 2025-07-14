from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from ..database import get_db
from ..auth import get_current_active_user
from .. import models, schemas

router = APIRouter()

@router.get("/", response_model=List[schemas.Workflow])
async def read_workflows(
    client_id: int = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Get workflows, optionally filtered by client."""
    query = db.query(models.Workflow).join(models.Client).filter(
        models.Client.owner_id == current_user.id
    )
    
    if client_id:
        query = query.filter(models.Workflow.client_id == client_id)
    
    workflows = query.offset(skip).limit(limit).all()
    return workflows

@router.post("/", response_model=schemas.Workflow)
async def create_workflow(
    workflow: schemas.WorkflowCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Create a new workflow."""
    # Verify client ownership
    client = db.query(models.Client).filter(
        models.Client.id == workflow.client_id,
        models.Client.owner_id == current_user.id
    ).first()
    if client is None:
        raise HTTPException(status_code=404, detail="Client not found")
    
    db_workflow = models.Workflow(**workflow.dict())
    db.add(db_workflow)
    db.commit()
    db.refresh(db_workflow)
    return db_workflow

@router.get("/{workflow_id}", response_model=schemas.Workflow)
async def read_workflow(
    workflow_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Get a specific workflow."""
    workflow = db.query(models.Workflow).join(models.Client).filter(
        models.Workflow.id == workflow_id,
        models.Client.owner_id == current_user.id
    ).first()
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return workflow

@router.put("/{workflow_id}", response_model=schemas.Workflow)
async def update_workflow(
    workflow_id: int,
    workflow_update: schemas.WorkflowUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Update a workflow."""
    db_workflow = db.query(models.Workflow).join(models.Client).filter(
        models.Workflow.id == workflow_id,
        models.Client.owner_id == current_user.id
    ).first()
    if db_workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    for field, value in workflow_update.dict(exclude_unset=True).items():
        setattr(db_workflow, field, value)
    
    db.commit()
    db.refresh(db_workflow)
    return db_workflow

@router.delete("/{workflow_id}")
async def delete_workflow(
    workflow_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Delete a workflow."""
    db_workflow = db.query(models.Workflow).join(models.Client).filter(
        models.Workflow.id == workflow_id,
        models.Client.owner_id == current_user.id
    ).first()
    if db_workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    db.delete(db_workflow)
    db.commit()
    return {"message": "Workflow deleted successfully"}

@router.post("/{workflow_id}/execute", response_model=schemas.WorkflowExecution)
async def execute_workflow(
    workflow_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Execute a workflow."""
    workflow = db.query(models.Workflow).join(models.Client).filter(
        models.Workflow.id == workflow_id,
        models.Client.owner_id == current_user.id
    ).first()
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    # Check if client has enough credits (basic check for now)
    client = workflow.client
    # TODO: Calculate actual credit cost based on workflow tasks
    estimated_cost = 10  # Placeholder
    
    if client.credits_balance < estimated_cost:
        raise HTTPException(
            status_code=400, 
            detail="Insufficient credits to execute workflow"
        )
    
    # Create execution record
    execution = models.WorkflowExecution(
        workflow_id=workflow_id,
        status="pending"
    )
    db.add(execution)
    db.commit()
    db.refresh(execution)
    
    # TODO: Implement actual workflow execution logic
    # For now, just mark as completed
    execution.status = "completed"
    execution.credits_used = estimated_cost
    
    # Update client credits
    client.credits_balance -= estimated_cost
    client.credits_used += estimated_cost
    
    # Create credit transaction
    transaction = models.CreditTransaction(
        client_id=client.id,
        workflow_execution_id=execution.id,
        transaction_type="usage",
        amount=-estimated_cost,
        description=f"Workflow execution: {workflow.name}"
    )
    db.add(transaction)
    
    db.commit()
    db.refresh(execution)
    return execution

@router.get("/{workflow_id}/executions", response_model=List[schemas.WorkflowExecution])
async def read_workflow_executions(
    workflow_id: int,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Get execution history for a workflow."""
    # Verify workflow ownership
    workflow = db.query(models.Workflow).join(models.Client).filter(
        models.Workflow.id == workflow_id,
        models.Client.owner_id == current_user.id
    ).first()
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    executions = db.query(models.WorkflowExecution).filter(
        models.WorkflowExecution.workflow_id == workflow_id
    ).order_by(models.WorkflowExecution.started_at.desc()).offset(skip).limit(limit).all()
    return executions

@router.get("/tasks/templates", response_model=List[schemas.TaskTemplate])
async def read_task_templates(
    category: str = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Get available task templates for workflow building."""
    query = db.query(models.TaskTemplate).filter(
        models.TaskTemplate.is_active == True
    )
    
    if category:
        query = query.filter(models.TaskTemplate.category == category)
    
    templates = query.offset(skip).limit(limit).all()
    return templates 