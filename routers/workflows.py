from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
import logging

from database import get_db
from auth import (
    get_current_active_user, 
    get_current_admin_user,
    verify_business_access,
    get_user_businesses
)
import models, schemas
from services.workflow_execution_service import workflow_execution_service

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

# Node Execution Endpoints

@router.post("/{workflow_id}/nodes/{node_id}/execute", response_model=schemas.NodeExecutionResponse)
async def execute_workflow_node(
    workflow_id: int,
    node_id: str,
    node_request: schemas.NodeExecutionRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Execute a single node for testing purposes"""
    try:
        # Verify workflow ownership
        workflow = db.query(models.Workflow).join(models.Client).filter(
            models.Workflow.id == workflow_id,
            models.Client.owner_id == current_user.id
        ).first()
        if workflow is None:
            raise HTTPException(status_code=404, detail="Workflow not found")
        
        # Extract node type from config
        node_type = node_request.node_config.get('type', 'unknown')
        
        # Execute the node
        result = await workflow_execution_service.execute_node(
            node_id=node_id,
            node_type=node_type,
            node_config=node_request.node_config,
            input_data=node_request.input_data
        )
        
        if not result['success']:
            raise HTTPException(status_code=500, detail=result.get('error', 'Node execution failed'))
        
        return schemas.NodeExecutionResponse(
            success=True,
            node_id=node_id,
            execution_id=result['execution_id'],
            data=result['data'],
            execution_time_ms=result['execution_time_ms'],
            credits_used=result.get('credits_used', 0)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Node execution error: {e}")
        raise HTTPException(status_code=500, detail="Failed to execute node")

@router.get("/{workflow_id}/node-data", response_model=Dict[str, Any])
async def get_workflow_node_data(
    workflow_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Get stored data from all executed nodes in workflow"""
    try:
        # Verify workflow ownership
        workflow = db.query(models.Workflow).join(models.Client).filter(
            models.Workflow.id == workflow_id,
            models.Client.owner_id == current_user.id
        ).first()
        if workflow is None:
            raise HTTPException(status_code=404, detail="Workflow not found")
        
        # Get all stored node results
        node_results = workflow_execution_service.get_all_node_results()
        
        return {
            "success": True,
            "workflow_id": workflow_id,
            "node_data": node_results,
            "total_nodes": len(node_results)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Get node data error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get node data")

@router.get("/{workflow_id}/nodes/{node_id}/data", response_model=Dict[str, Any])
async def get_node_execution_data(
    workflow_id: int,
    node_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Get stored execution data for a specific node"""
    try:
        # Verify workflow ownership
        workflow = db.query(models.Workflow).join(models.Client).filter(
            models.Workflow.id == workflow_id,
            models.Client.owner_id == current_user.id
        ).first()
        if workflow is None:
            raise HTTPException(status_code=404, detail="Workflow not found")
        
        # Get node execution result
        node_result = workflow_execution_service.get_node_execution_result(node_id)
        
        if node_result is None:
            raise HTTPException(status_code=404, detail="Node data not found")
        
        return {
            "success": True,
            "node_id": node_id,
            "data": node_result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Get node execution data error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get node execution data")

@router.delete("/{workflow_id}/node-data", response_model=Dict[str, Any])
async def clear_workflow_node_data(
    workflow_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Clear all stored node execution data"""
    try:
        # Verify workflow ownership
        workflow = db.query(models.Workflow).join(models.Client).filter(
            models.Workflow.id == workflow_id,
            models.Client.owner_id == current_user.id
        ).first()
        if workflow is None:
            raise HTTPException(status_code=404, detail="Workflow not found")
        
        # Clear node results
        workflow_execution_service.clear_node_results()
        
        return {
            "success": True,
            "message": "All node execution data cleared"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Clear node data error: {e}")
        raise HTTPException(status_code=500, detail="Failed to clear node data")

# =============================================================================
# MULTI-TENANT WORKFLOW TEMPLATES (NEW)
# =============================================================================

@router.get("/templates", response_model=List[schemas.WorkflowTemplate])
async def get_workflow_templates(
    category: Optional[str] = None,
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Get available workflow templates based on user's tier and access."""
    query = db.query(models.WorkflowTemplate)
    
    # Filter by category
    if category:
        query = query.filter(models.WorkflowTemplate.category == category)
    
    # Filter by status (admin can see all, others only published/beta)
    if current_user.role == "admin":
        if status:
            query = query.filter(models.WorkflowTemplate.status == status)
    else:
        # Non-admin users can see published templates or beta if they have access
        allowed_statuses = ["published"]
        if status and status in ["published"]:
            query = query.filter(models.WorkflowTemplate.status == status)
        else:
            query = query.filter(models.WorkflowTemplate.status.in_(allowed_statuses))
    
    templates = query.offset(skip).limit(limit).all()
    return templates

@router.post("/templates", response_model=schemas.WorkflowTemplate)
async def create_workflow_template(
    template: schemas.WorkflowTemplateCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user)
):
    """Create a new workflow template (admin only)."""
    db_template = models.WorkflowTemplate(
        **template.dict(),
        created_by=current_user.id
    )
    
    db.add(db_template)
    db.commit()
    db.refresh(db_template)
    return db_template

@router.get("/templates/{template_id}", response_model=schemas.WorkflowTemplate)
async def get_workflow_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Get a specific workflow template."""
    template = db.query(models.WorkflowTemplate).filter(
        models.WorkflowTemplate.id == template_id
    ).first()
    
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    
    # Check access rights
    if current_user.role != "admin" and template.status not in ["published"]:
        # Check if user has beta access
        if template.status == "beta" and current_user.id not in template.beta_users:
            raise HTTPException(status_code=403, detail="Access denied")
    
    return template

@router.put("/templates/{template_id}", response_model=schemas.WorkflowTemplate)
async def update_workflow_template(
    template_id: int,
    template_update: schemas.WorkflowTemplateUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user)
):
    """Update a workflow template (admin only)."""
    template = db.query(models.WorkflowTemplate).filter(
        models.WorkflowTemplate.id == template_id
    ).first()
    
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    
    # Update fields
    for field, value in template_update.dict(exclude_unset=True).items():
        setattr(template, field, value)
    
    db.commit()
    db.refresh(template)
    return template

# =============================================================================
# MULTI-TENANT WORKFLOW INSTANCES (NEW)
# =============================================================================

@router.get("/instances", response_model=List[schemas.WorkflowInstance])
async def get_workflow_instances(
    business_id: Optional[int] = None,
    template_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Get workflow instances for accessible businesses."""
    # Get businesses user has access to
    accessible_businesses = get_user_businesses(db, current_user)
    business_ids = [b.id for b in accessible_businesses]
    
    if not business_ids:
        return []
    
    query = db.query(models.WorkflowInstance).filter(
        models.WorkflowInstance.business_id.in_(business_ids)
    )
    
    # Filter by specific business if provided
    if business_id:
        if business_id not in business_ids:
            raise HTTPException(status_code=403, detail="Access to this business denied")
        query = query.filter(models.WorkflowInstance.business_id == business_id)
    
    # Filter by template
    if template_id:
        query = query.filter(models.WorkflowInstance.template_id == template_id)
    
    instances = query.offset(skip).limit(limit).all()
    return instances

@router.post("/instances", response_model=schemas.WorkflowInstance)
async def create_workflow_instance(
    instance: schemas.WorkflowInstanceCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Create a workflow instance from a template."""
    # Verify business access
    if not verify_business_access(db, current_user, instance.business_id):
        raise HTTPException(status_code=403, detail="Access to this business denied")
    
    # Verify template exists and is accessible
    template = db.query(models.WorkflowTemplate).filter(
        models.WorkflowTemplate.id == instance.template_id
    ).first()
    
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    
    # Check template access
    if current_user.role != "admin" and template.status not in ["published"]:
        if template.status == "beta" and current_user.id not in template.beta_users:
            raise HTTPException(status_code=403, detail="Template access denied")
    
    # Create instance
    db_instance = models.WorkflowInstance(**instance.dict())
    db.add(db_instance)
    db.commit()
    db.refresh(db_instance)
    return db_instance

@router.get("/instances/{instance_id}", response_model=schemas.WorkflowInstance)
async def get_workflow_instance(
    instance_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Get a specific workflow instance."""
    instance = db.query(models.WorkflowInstance).filter(
        models.WorkflowInstance.id == instance_id
    ).first()
    
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")
    
    # Verify business access
    if not verify_business_access(db, current_user, instance.business_id):
        raise HTTPException(status_code=403, detail="Access denied")
    
    return instance

@router.post("/instances/{instance_id}/execute", response_model=schemas.WorkflowExecution)
async def execute_workflow_instance(
    instance_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Execute a workflow instance."""
    instance = db.query(models.WorkflowInstance).filter(
        models.WorkflowInstance.id == instance_id
    ).first()
    
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")
    
    # Verify business access
    if not verify_business_access(db, current_user, instance.business_id):
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Check if business has enough credits
    business = db.query(models.Business).filter(
        models.Business.id == instance.business_id
    ).first()
    
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    
    # Get agency's credit pool
    credit_pool = db.query(models.CreditPool).filter(
        models.CreditPool.owner_id == business.agency_id,
        models.CreditPool.owner_type == "agency"
    ).first()
    
    if not credit_pool:
        raise HTTPException(status_code=400, detail="No credit pool found")
    
    # Get template to check credit cost
    template = instance.template
    estimated_cost = template.credit_cost if template else 10
    
    # Check credit balance
    if credit_pool.balance < estimated_cost:
        if credit_pool.balance + credit_pool.overage_threshold < estimated_cost:
            raise HTTPException(
                status_code=400,
                detail="Insufficient credits to execute workflow"
            )
    
    # Create execution record
    execution = models.WorkflowExecution(
        instance_id=instance_id,
        business_id=instance.business_id,
        status="pending"
    )
    
    db.add(execution)
    db.commit()
    db.refresh(execution)
    
    # Update instance stats
    instance.execution_count += 1
    instance.last_executed_at = execution.started_at
    
    # Deduct credits
    credit_pool.balance -= estimated_cost
    credit_pool.total_used += estimated_cost
    
    # Create credit transaction
    transaction = models.CreditTransaction(
        pool_id=credit_pool.id,
        business_id=instance.business_id,
        workflow_execution_id=execution.id,
        transaction_type="usage",
        amount=-estimated_cost,
        balance_after=credit_pool.balance,
        description=f"Workflow execution: {template.name if template else 'Unknown'}",
        created_by=current_user.id
    )
    
    db.add(transaction)
    
    # Mark execution as completed (TODO: implement actual execution)
    execution.status = "completed"
    execution.credits_used = estimated_cost
    execution.completed_at = execution.started_at
    
    # Update success count
    instance.success_count += 1
    
    db.commit()
    db.refresh(execution)
    
    return execution

@router.get("/instances/{instance_id}/executions", response_model=List[schemas.WorkflowExecution])
async def get_instance_executions(
    instance_id: int,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Get execution history for a workflow instance."""
    instance = db.query(models.WorkflowInstance).filter(
        models.WorkflowInstance.id == instance_id
    ).first()
    
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")
    
    # Verify business access
    if not verify_business_access(db, current_user, instance.business_id):
        raise HTTPException(status_code=403, detail="Access denied")
    
    executions = db.query(models.WorkflowExecution).filter(
        models.WorkflowExecution.instance_id == instance_id
    ).order_by(models.WorkflowExecution.started_at.desc()).offset(skip).limit(limit).all()
    
    return executions 