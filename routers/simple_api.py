from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import List, Dict, Any
import json
from datetime import datetime

from database import get_db
import models
from models_simple import SimpleIntegration, SimpleWorkflow, SimpleWorkflowExecution

router = APIRouter(prefix="/api/simple", tags=["simple"])

# INTEGRATIONS ENDPOINTS

@router.get("/integrations", response_model=List[Dict[str, Any]])
def get_integrations(db: Session = Depends(get_db)):
    """Get all system-wide integrations"""
    integrations = db.query(SimpleIntegration).all()
    return [
        {
            "id": integration.id,
            "name": integration.name,
            "type": integration.type,
            "status": integration.status,
            "config": integration.config,
            "last_tested": integration.last_tested,
            "created_at": integration.created_at,
            "updated_at": integration.updated_at,
        }
        for integration in integrations
    ]

@router.post("/integrations")
def create_integration(integration_data: Dict[str, Any], db: Session = Depends(get_db)):
    """Create a new system-wide integration"""
    integration = SimpleIntegration(
        id=integration_data.get("id", f"integration_{integration_data['name'].lower().replace(' ', '_')}"),
        name=integration_data["name"],
        type=integration_data.get("type", "custom"),
        status=integration_data.get("status", "disconnected"),
        config=integration_data.get("config", {}),
    )
    
    db.add(integration)
    db.commit()
    db.refresh(integration)
    
    return {"success": True, "integration": integration}

@router.put("/integrations/{integration_id}")
def update_integration(integration_id: str, integration_data: Dict[str, Any], db: Session = Depends(get_db)):
    """Update an existing integration"""
    integration = db.query(SimpleIntegration).filter(SimpleIntegration.id == integration_id).first()
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")
    
    # Update fields
    for key, value in integration_data.items():
        if hasattr(integration, key):
            setattr(integration, key, value)
    
    db.commit()
    db.refresh(integration)
    
    return {"success": True, "integration": integration}

@router.delete("/integrations/{integration_id}")
def delete_integration(integration_id: str, db: Session = Depends(get_db)):
    """Delete an integration"""
    integration = db.query(SimpleIntegration).filter(SimpleIntegration.id == integration_id).first()
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")
    
    db.delete(integration)
    db.commit()
    
    return {"success": True, "message": "Integration deleted"}

# WORKFLOWS ENDPOINTS

@router.get("/workflows", response_model=List[Dict[str, Any]])
def get_workflows(db: Session = Depends(get_db)):
    """Get all workflows"""
    workflows = db.query(SimpleWorkflow).all()
    return [
        {
            "id": workflow.id,
            "name": workflow.name,
            "description": workflow.description,
            "nodes": workflow.nodes,
            "edges": workflow.edges,
            "is_active": workflow.is_active,
            "tags": workflow.tags,
            "execution_count": workflow.execution_count,
            "last_executed": workflow.last_executed,
            "success_rate": workflow.success_rate,
            "created_at": workflow.created_at,
            "updated_at": workflow.updated_at,
        }
        for workflow in workflows
    ]

@router.post("/workflows")
def create_workflow(workflow_data: Dict[str, Any], db: Session = Depends(get_db)):
    """Create a new workflow"""
    workflow = SimpleWorkflow(
        id=workflow_data["id"],
        name=workflow_data["name"],
        description=workflow_data.get("description", ""),
        nodes=workflow_data.get("nodes", []),
        edges=workflow_data.get("edges", []),
        is_active=workflow_data.get("is_active", False),
        tags=workflow_data.get("tags", []),
    )
    
    db.add(workflow)
    db.commit()
    db.refresh(workflow)
    
    return {"success": True, "workflow": workflow}

@router.put("/workflows/{workflow_id}")
def update_workflow(workflow_id: str, workflow_data: Dict[str, Any], db: Session = Depends(get_db)):
    """Update an existing workflow"""
    workflow = db.query(SimpleWorkflow).filter(SimpleWorkflow.id == workflow_id).first()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    # Update fields
    for key, value in workflow_data.items():
        if hasattr(workflow, key):
            setattr(workflow, key, value)
    
    db.commit()
    db.refresh(workflow)
    
    return {"success": True, "workflow": workflow}

@router.delete("/workflows/{workflow_id}")
def delete_workflow(workflow_id: str, db: Session = Depends(get_db)):
    """Delete a workflow"""
    workflow = db.query(SimpleWorkflow).filter(SimpleWorkflow.id == workflow_id).first()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    db.delete(workflow)
    db.commit()
    
    return {"success": True, "message": "Workflow deleted"}

@router.get("/workflows/{workflow_id}")
def get_workflow(workflow_id: str, db: Session = Depends(get_db)):
    """Get a specific workflow by ID"""
    workflow = db.query(SimpleWorkflow).filter(SimpleWorkflow.id == workflow_id).first()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    return {
        "id": workflow.id,
        "name": workflow.name,
        "description": workflow.description,
        "nodes": workflow.nodes,
        "edges": workflow.edges,
        "is_active": workflow.is_active,
        "tags": workflow.tags,
        "execution_count": workflow.execution_count,
        "last_executed": workflow.last_executed,
        "success_rate": workflow.success_rate,
        "created_at": workflow.created_at,
        "updated_at": workflow.updated_at,
    }

# WORKFLOW EXECUTION

@router.post("/workflows/{workflow_id}/execute")
def execute_workflow(workflow_id: str, db: Session = Depends(get_db)):
    """Execute a workflow (simplified)"""
    workflow = db.query(SimpleWorkflow).filter(SimpleWorkflow.id == workflow_id).first()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    # Create execution record
    execution = SimpleWorkflowExecution(
        id=f"exec_{workflow_id}_{int(datetime.now().timestamp())}",
        workflow_id=workflow_id,
        status="running"
    )
    
    db.add(execution)
    db.commit()
    
    # For proof of concept, just mark as completed
    # In real implementation, this would execute the actual workflow
    execution.status = "completed"
    execution.completed_at = datetime.now()
    execution.results = {"message": "Workflow executed successfully (proof of concept)"}
    
    # Update workflow execution count
    workflow.execution_count += 1
    workflow.last_executed = datetime.now()
    
    db.commit()
    
    return {"success": True, "execution_id": execution.id, "status": "completed"} 