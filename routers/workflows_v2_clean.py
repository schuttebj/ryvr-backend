from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
import logging
import json
from datetime import datetime

from database import get_db
from auth import (
    get_current_active_user, 
    get_current_admin_user,
    verify_business_access,
    get_user_businesses
)
import models, schemas
from services.expression_engine import expression_engine, context_builder
from services.data_transformation_service import data_transformation_service
# from services.async_step_executor import AsyncStepExecutor  # TODO: Enable when integration service is ready

logger = logging.getLogger(__name__)
router = APIRouter()

# =============================================================================
# WORKFLOW V2 ENDPOINTS (Default)
# =============================================================================

@router.get("/templates", response_model=List[Dict[str, Any]])
async def list_workflow_templates(
    business_id: Optional[int] = None,
    category: Optional[str] = None,
    tags: Optional[str] = None,  # Comma-separated
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """List workflow templates with V2 schema filtering"""
    try:
        query = db.query(models.WorkflowTemplate).filter(
            models.WorkflowTemplate.schema_version == "ryvr.workflow.v1"
        )
        
        # Filter by business access if specified
        if business_id:
            if not verify_business_access(db, current_user, business_id):
                raise HTTPException(status_code=403, detail="Access denied to business")
            query = query.filter(
                (models.WorkflowTemplate.business_id == business_id) |
                (models.WorkflowTemplate.business_id.is_(None))  # Include public templates
            )
        
        # Filter by category
        if category:
            query = query.filter(models.WorkflowTemplate.category == category)
        
        # Filter by tags
        if tags:
            tag_list = [tag.strip() for tag in tags.split(",")]
            for tag in tag_list:
                query = query.filter(models.WorkflowTemplate.tags.contains([tag]))
        
        templates = query.offset(skip).limit(limit).all()
        
        return [
            {
                "id": template.id,
                "schema_version": template.schema_version,
                "name": template.name,
                "description": template.description,
                "category": template.category,
                "tags": template.tags,
                "credit_cost": template.credit_cost,
                "estimated_duration": template.estimated_duration,
                "status": template.status,
                "created_at": template.created_at.isoformat(),
                "workflow_config": template.workflow_config,
                "execution_config": template.execution_config
            }
            for template in templates
        ]
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list workflow templates: {e}")
        raise HTTPException(status_code=500, detail="Failed to list templates")


@router.post("/templates", response_model=Dict[str, Any])
async def create_workflow_template(
    template_data: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Create a new workflow template with V2 schema (ryvr.workflow.v1)"""
    try:
        # Validate schema version
        schema_version = template_data.get("schema_version", "ryvr.workflow.v1")
        if schema_version != "ryvr.workflow.v1":
            raise HTTPException(
                status_code=400, 
                detail=f"Unsupported schema version: {schema_version}"
            )
        
        # Extract template metadata
        name = template_data.get("name")
        description = template_data.get("description", "")
        category = template_data.get("category", "general")
        tags = template_data.get("tags", [])
        
        if not name:
            raise HTTPException(status_code=400, detail="Template name is required")
        
        # Validate workflow configuration
        workflow_config = template_data
        if not workflow_config.get("steps"):
            raise HTTPException(status_code=400, detail="Workflow must have at least one step")
        
        # Extract execution configuration
        execution_config = workflow_config.get("execution", {
            "execution_mode": "simulate",
            "dry_run": True
        })
        
        # Create template
        template = models.WorkflowTemplate(
            schema_version=schema_version,
            name=name,
            description=description,
            category=category,
            tags=tags,
            workflow_config=workflow_config,
            execution_config=execution_config,
            created_by=current_user.id
        )
        
        db.add(template)
        db.commit()
        db.refresh(template)
        
        logger.info(f"Created workflow template V2: {template.id} - {name}")
        
        return {
            "id": template.id,
            "schema_version": template.schema_version,
            "name": template.name,
            "description": template.description,
            "category": template.category,
            "tags": template.tags,
            "workflow_config": template.workflow_config,
            "execution_config": template.execution_config,
            "created_at": template.created_at.isoformat(),
            "created_by": template.created_by
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create workflow template V2: {e}")
        raise HTTPException(status_code=500, detail="Failed to create workflow template")


@router.get("/templates/{template_id}", response_model=Dict[str, Any])
async def get_workflow_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Get a specific workflow template with V2 schema"""
    try:
        template = db.query(models.WorkflowTemplate).filter(
            models.WorkflowTemplate.id == template_id,
            models.WorkflowTemplate.schema_version == "ryvr.workflow.v1"
        ).first()
        
        if not template:
            raise HTTPException(status_code=404, detail="Workflow template not found")
        
        # Check access permissions
        if template.business_id:
            if not verify_business_access(db, current_user, template.business_id):
                raise HTTPException(status_code=403, detail="Access denied")
        
        return {
            "id": template.id,
            "schema_version": template.schema_version,
            "name": template.name,
            "description": template.description,
            "category": template.category,
            "tags": template.tags,
            "workflow_config": template.workflow_config,
            "execution_config": template.execution_config,
            "credit_cost": template.credit_cost,
            "estimated_duration": template.estimated_duration,
            "status": template.status,
            "created_at": template.created_at.isoformat(),
            "updated_at": template.updated_at.isoformat() if template.updated_at else None,
            "created_by": template.created_by
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get workflow template V2: {e}")
        raise HTTPException(status_code=500, detail="Failed to get template")


@router.post("/templates/{template_id}/validate")
async def validate_workflow_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Validate workflow template against V2 schema"""
    try:
        template = db.query(models.WorkflowTemplate).filter(
            models.WorkflowTemplate.id == template_id
        ).first()
        
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")
        
        # Check access permissions
        if template.business_id:
            if not verify_business_access(db, current_user, template.business_id):
                raise HTTPException(status_code=403, detail="Access denied")
        
        workflow_config = template.workflow_config
        validation_errors = []
        
        # Basic schema validation
        required_fields = ["steps", "inputs", "globals"]
        for field in required_fields:
            if field not in workflow_config:
                validation_errors.append(f"Missing required field: {field}")
        
        # Validate steps
        steps = workflow_config.get("steps", [])
        if not steps:
            validation_errors.append("Workflow must have at least one step")
        
        for i, step in enumerate(steps):
            step_errors = _validate_step_v2(step, i)
            validation_errors.extend(step_errors)
        
        # Validate dependencies
        dependency_errors = _validate_step_dependencies(steps)
        validation_errors.extend(dependency_errors)
        
        is_valid = len(validation_errors) == 0
        
        return {
            "is_valid": is_valid,
            "errors": validation_errors,
            "step_count": len(steps),
            "schema_version": template.schema_version
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to validate workflow template: {e}")
        raise HTTPException(status_code=500, detail="Validation failed")


@router.post("/templates/{template_id}/execute")
async def execute_workflow(
    template_id: int,
    execution_request: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Execute a workflow template with V2 engine"""
    try:
        # Get template
        template = db.query(models.WorkflowTemplate).filter(
            models.WorkflowTemplate.id == template_id
        ).first()
        
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")
        
        # Extract execution parameters
        business_id = execution_request.get("business_id")
        execution_mode = execution_request.get("execution_mode", "simulate")
        inputs = execution_request.get("inputs", {})
        
        # Get or create default business if not provided
        if not business_id:
            # Try to get user's first business
            businesses = get_user_businesses(db, current_user)
            if businesses:
                business_id = businesses[0].id
            else:
                # Create a default business for testing
                default_business = models.Business(
                    name=f"{current_user.username}'s Business",
                    owner_id=current_user.id,
                    business_type="default"
                )
                db.add(default_business)
                db.commit()
                db.refresh(default_business)
                business_id = default_business.id
                logger.info(f"Created default business {business_id} for user {current_user.id}")
        
        # Verify business access
        if not verify_business_access(db, current_user, business_id):
            raise HTTPException(status_code=403, detail="Access denied to business")
        
        # Create execution record
        execution = models.WorkflowExecution(
            template_id=template.id,
            business_id=business_id,
            execution_mode=execution_mode,
            runtime_state={
                "inputs": inputs,
                "globals": template.workflow_config.get("globals", {}),
                "steps": {},
                "runtime": {
                    "business_id": business_id,
                    "user_id": current_user.id,
                    "execution_mode": execution_mode
                }
            },
            status="pending",
            total_steps=len(template.workflow_config.get("steps", []))
        )
        
        db.add(execution)
        db.commit()
        db.refresh(execution)
        
        # Start execution (this would be async in production)
        execution_result = await _execute_workflow_steps_v2(
            template, execution, db
        )
        
        return {
            "execution_id": execution.id,
            "business_id": business_id,
            "status": execution.status,
            "execution_mode": execution_mode,
            "started_at": execution.started_at.isoformat() if execution.started_at else None,
            "result": execution_result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to execute workflow: {e}")
        raise HTTPException(status_code=500, detail="Execution failed")


@router.get("/executions/{execution_id}")
async def get_execution_status(
    execution_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Get workflow execution status and results"""
    try:
        execution = db.query(models.WorkflowExecution).filter(
            models.WorkflowExecution.id == execution_id
        ).first()
        
        if not execution:
            raise HTTPException(status_code=404, detail="Execution not found")
        
        # Verify business access
        if not verify_business_access(db, current_user, execution.business_id):
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Get step executions
        step_executions = db.query(models.WorkflowStepExecution).filter(
            models.WorkflowStepExecution.execution_id == execution_id
        ).order_by(models.WorkflowStepExecution.created_at).all()
        
        return {
            "execution_id": execution.id,
            "template_id": execution.template_id,
            "business_id": execution.business_id,
            "status": execution.status,
            "execution_mode": execution.execution_mode,
            "current_step": execution.current_step,
            "completed_steps": execution.completed_steps,
            "total_steps": execution.total_steps,
            "credits_used": execution.credits_used,
            "execution_time_ms": execution.execution_time_ms,
            "started_at": execution.started_at.isoformat() if execution.started_at else None,
            "completed_at": execution.completed_at.isoformat() if execution.completed_at else None,
            "runtime_state": execution.runtime_state,
            "step_results": execution.step_results,
            "error_message": execution.error_message,
            "step_executions": [
                {
                    "step_id": step.step_id,
                    "step_type": step.step_type,
                    "status": step.status,
                    "credits_used": step.credits_used,
                    "execution_time_ms": step.execution_time_ms,
                    "started_at": step.started_at.isoformat() if step.started_at else None,
                    "completed_at": step.completed_at.isoformat() if step.completed_at else None,
                    "output_data": step.output_data,
                    "error_data": step.error_data
                }
                for step in step_executions
            ]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get execution status: {e}")
        raise HTTPException(status_code=500, detail="Failed to get execution status")


# Helper functions for V2 workflow processing
def _validate_step_v2(step: Dict[str, Any], step_index: int) -> List[str]:
    """Validate a single workflow step"""
    errors = []
    
    # Required fields
    if "id" not in step:
        errors.append(f"Step {step_index}: Missing required field 'id'")
    if "type" not in step:
        errors.append(f"Step {step_index}: Missing required field 'type'")
    
    # Valid step types
    valid_types = ["task", "ai", "transform", "foreach", "gate", "condition", "async_task"]
    if step.get("type") not in valid_types:
        errors.append(f"Step {step_index}: Invalid type '{step.get('type')}'")
    
    # Async-specific validation
    if step.get("type") == "async_task":
        if "async_config" not in step:
            errors.append(f"Step {step_index}: async_task requires async_config")
    
    return errors


def _validate_step_dependencies(steps: List[Dict[str, Any]]) -> List[str]:
    """Validate step dependencies don't create cycles"""
    errors = []
    step_ids = set(step.get("id") for step in steps if step.get("id"))
    
    for step in steps:
        depends_on = step.get("depends_on", [])
        for dep in depends_on:
            if dep not in step_ids:
                errors.append(f"Step '{step.get('id')}' depends on non-existent step '{dep}'")
    
    # TODO: Add cycle detection logic
    
    return errors


async def _execute_workflow_steps_v2(
    template: models.WorkflowTemplate, 
    execution: models.WorkflowExecution, 
    db: Session
) -> Dict[str, Any]:
    """Execute workflow steps using V2 engine (simplified version)"""
    try:
        execution.status = "running"
        execution.started_at = datetime.utcnow()
        db.commit()
        
        workflow_config = template.workflow_config
        steps = workflow_config.get("steps", [])
        runtime_state = execution.runtime_state
        
        # Build execution context
        context = context_builder.build_context(
            inputs=runtime_state.get("inputs", {}),
            globals_config=workflow_config.get("globals", {}),
            step_outputs={},
            runtime_context=runtime_state.get("runtime", {})
        )
        
        step_results = {}
        
        for step in steps:
            step_id = step["id"]
            step_type = step["type"]
            
            logger.info(f"Executing step {step_id} ({step_type})")
            
            # Create step execution record
            step_execution = models.WorkflowStepExecution(
                execution_id=execution.id,
                step_id=step_id,
                step_type=step_type,
                step_name=step.get("name", step_id),
                status="running",
                started_at=datetime.utcnow()
            )
            db.add(step_execution)
            db.commit()
            
            try:
                # Execute based on step type
                if step_type == "transform":
                    result = _execute_transform_step(step, context)
                elif step_type in ["task", "ai"]:
                    result = _execute_api_step(step, context)
                else:
                    result = {"message": f"Step type {step_type} not implemented yet"}
                
                # Update step execution
                step_execution.status = "completed"
                step_execution.completed_at = datetime.utcnow()
                step_execution.output_data = result
                
                # Add to context for next steps
                context = context_builder.add_step_output(context, step_id, result)
                step_results[step_id] = result
                
                execution.completed_steps += 1
                
            except Exception as step_error:
                logger.error(f"Step {step_id} failed: {step_error}")
                
                step_execution.status = "failed"
                step_execution.completed_at = datetime.utcnow()
                step_execution.error_data = {"error": str(step_error)}
                
                execution.status = "failed"
                execution.error_message = f"Step {step_id} failed: {step_error}"
                execution.failed_step = step_id
                break
            
            finally:
                db.commit()
        
        # Complete execution if all steps succeeded
        if execution.status == "running":
            execution.status = "completed"
            execution.completed_at = datetime.utcnow()
        
        execution.step_results = step_results
        db.commit()
        
        return {
            "status": execution.status,
            "step_results": step_results,
            "completed_steps": execution.completed_steps,
            "total_steps": execution.total_steps
        }
        
    except Exception as e:
        execution.status = "failed"
        execution.error_message = str(e)
        execution.completed_at = datetime.utcnow()
        db.commit()
        raise


def _execute_transform_step(step: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a data transformation step"""
    transform_config = step.get("transform", {})
    
    # For transform steps, the input is usually from depends_on steps
    depends_on = step.get("depends_on", [])
    if depends_on:
        # Get data from first dependency
        source_step = depends_on[0]
        input_data = context.get("steps", {}).get(source_step, {}).get("output")
    else:
        # Use test data if no dependencies
        input_data = [{"id": 1, "value": 150}, {"id": 2, "value": 250}]
    
    # Apply transformations
    result = data_transformation_service.apply_transformations(
        data=input_data,
        transform_config=transform_config,
        runtime_context=context
    )
    
    return result


def _execute_api_step(step: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """Execute an API call step (simplified mock)"""
    # This would integrate with the actual integration service
    step_type = step.get("type")
    operation = step.get("operation")
    
    # Mock result for demonstration
    return {
        "step_type": step_type,
        "operation": operation,
        "status": "completed",
        "mock_data": "This would be real API response data"
    }
