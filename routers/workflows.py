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
# WORKFLOW ENDPOINTS
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
    """List workflow templates with schema filtering"""
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
    """Create a new workflow template (ryvr.workflow.v1 schema)"""
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
        
        logger.info(f"Created workflow template: {template.id} - {name}")
        
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
        logger.error(f"Failed to create workflow template: {e}")
        raise HTTPException(status_code=500, detail="Failed to create workflow template")


@router.get("/templates/{template_id}", response_model=Dict[str, Any])
async def get_workflow_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Get a specific workflow template"""
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
        logger.error(f"Failed to get workflow template: {e}")
        raise HTTPException(status_code=500, detail="Failed to get template")


@router.post("/templates/{template_id}/validate")
async def validate_workflow_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Validate workflow template against schema"""
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
            step_errors = _validate_step(step, i)
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
    """Execute a workflow template"""
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
        execution_result = await _execute_workflow_steps(
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


@router.put("/templates/{template_id}")
async def update_workflow_template(
    template_id: int,
    template_data: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Update an existing workflow template"""
    try:
        # Get existing template
        template = db.query(models.WorkflowTemplate).filter(
            models.WorkflowTemplate.id == template_id
        ).first()
        
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")
        
        # Check permissions - only allow update if user created it or is admin
        if template.created_by != current_user.id and current_user.role != "admin":
            raise HTTPException(status_code=403, detail="Permission denied")
        
        # Update template fields
        if "name" in template_data:
            template.name = template_data["name"]
        if "description" in template_data:
            template.description = template_data["description"]
        if "category" in template_data:
            template.category = template_data["category"]
        if "tags" in template_data:
            template.tags = template_data["tags"]
        if "credit_cost" in template_data:
            template.credit_cost = template_data["credit_cost"]
        if "estimated_duration" in template_data:
            template.estimated_duration = template_data["estimated_duration"]
        if "status" in template_data:
            template.status = template_data["status"]
        
        # Update workflow configuration
        if "workflow_config" in template_data:
            template.workflow_config = template_data["workflow_config"]
        elif "steps" in template_data:
            # Handle legacy format - convert to workflow_config
            template.workflow_config = {
                "schema_version": template_data.get("schema_version", "ryvr.workflow.v1"),
                "inputs": template_data.get("inputs", {}),
                "globals": template_data.get("globals", {}),
                "steps": template_data["steps"]
            }
        
        # Update execution configuration
        if "execution_config" in template_data:
            template.execution_config = template_data["execution_config"]
        elif "execution" in template_data:
            template.execution_config = template_data["execution"]
        
        # Update tool catalog if provided
        if "tool_catalog" in template_data:
            template.tool_catalog = template_data["tool_catalog"]
        
        db.commit()
        db.refresh(template)
        
        logger.info(f"Updated workflow template {template_id} by user {current_user.id}")
        
        # Return updated template in the expected format
        return {
            "id": template.id,
            "schema_version": template.schema_version,
            "name": template.name,
            "description": template.description,
            "category": template.category,
            "tags": template.tags,
            "workflow_config": template.workflow_config,
            "execution_config": template.execution_config,
            "tool_catalog": template.tool_catalog,
            "credit_cost": template.credit_cost,
            "estimated_duration": template.estimated_duration,
            "status": template.status,
            "created_at": template.created_at,
            "updated_at": template.updated_at,
            "created_by": template.created_by
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update workflow template: {e}")
        raise HTTPException(status_code=500, detail="Failed to update template")

@router.delete("/templates/{template_id}")
async def delete_workflow_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Delete a workflow template"""
    try:
        template = db.query(models.WorkflowTemplate).filter(
            models.WorkflowTemplate.id == template_id
        ).first()
        
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")
        
        # Check permissions - only allow delete if user created it or is admin
        if template.created_by != current_user.id and current_user.role != "admin":
            raise HTTPException(status_code=403, detail="Permission denied")
        
        # Check if template has running executions
        running_executions = db.query(models.WorkflowExecution).filter(
            models.WorkflowExecution.template_id == template_id,
            models.WorkflowExecution.status.in_(["pending", "running"])
        ).first()
        
        if running_executions:
            raise HTTPException(
                status_code=400, 
                detail="Cannot delete template with running executions"
            )
        
        # Delete the template
        db.delete(template)
        db.commit()
        
        logger.info(f"Deleted workflow template {template_id} by user {current_user.id}")
        
        return {"message": "Template deleted successfully", "id": template_id}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete workflow template: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete template")


@router.get("/tool-catalog")
async def get_tool_catalog(
    provider: Optional[str] = None,
    category: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Get available tools/integrations with dynamic field definitions"""
    try:
        # This would eventually come from a database or config
        # For now, let's create a comprehensive tool catalog
        
        tool_catalog = {
            "schema_version": "ryvr.tools.v1",
            "providers": {
                "dataforseo": {
                    "name": "DataForSEO",
                    "description": "SEO and SERP data provider",
                    "category": "seo",
                    "auth_type": "api_key",
                    "operations": {
                        "serp_google_organic": {
                            "name": "Google SERP Analysis",
                            "description": "Get Google organic search results",
                            "is_async": True,
                            "base_credits": 5,
                            "fields": [
                                {"name": "keyword", "type": "string", "required": True, "description": "Search keyword"},
                                {"name": "location_code", "type": "integer", "required": False, "default": 2840, "description": "Location code (US=2840)"},
                                {"name": "language_code", "type": "string", "required": False, "default": "en", "description": "Language code"},
                                {"name": "device", "type": "select", "options": ["desktop", "mobile"], "default": "desktop", "description": "Device type"},
                                {"name": "depth", "type": "integer", "required": False, "default": 100, "min": 1, "max": 700, "description": "Number of results to return"}
                            ],
                            "async_config": {
                                "submit_operation": "post_serp_task",
                                "check_operation": "get_serp_results",
                                "polling_interval_seconds": 10,
                                "max_wait_seconds": 300,
                                "completion_check": "expr: @.tasks[0].status == 'completed'",
                                "result_path": "expr: @.tasks[0].result",
                                "task_id_path": "expr: @.tasks[0].id"
                            }
                        },
                        "keyword_research": {
                            "name": "Keyword Research",
                            "description": "Get keyword suggestions and data",
                            "is_async": True,
                            "base_credits": 3,
                            "fields": [
                                {"name": "seed_keyword", "type": "string", "required": True, "description": "Base keyword for research"},
                                {"name": "location_code", "type": "integer", "required": False, "default": 2840},
                                {"name": "include_serp_info", "type": "boolean", "default": True, "description": "Include SERP information"},
                                {"name": "limit", "type": "integer", "default": 1000, "min": 1, "max": 1000, "description": "Max keywords to return"}
                            ]
                        }
                    }
                },
                "openai": {
                    "name": "OpenAI",
                    "description": "AI text generation and analysis",
                    "category": "ai",
                    "auth_type": "api_key",
                    "operations": {
                        "chat_completion": {
                            "name": "AI Text Generation",
                            "description": "Generate text using ChatGPT",
                            "is_async": False,
                            "base_credits": 1,
                            "fields": [
                                {"name": "prompt", "type": "textarea", "required": True, "description": "Text prompt for AI"},
                                {"name": "model", "type": "select", "options": ["gpt-4", "gpt-3.5-turbo"], "default": "gpt-3.5-turbo", "description": "AI model to use"},
                                {"name": "max_tokens", "type": "integer", "default": 500, "min": 1, "max": 4000, "description": "Maximum response length"},
                                {"name": "temperature", "type": "number", "default": 0.7, "min": 0, "max": 2, "step": 0.1, "description": "Creativity level (0=conservative, 2=creative)"}
                            ]
                        },
                        "content_analysis": {
                            "name": "Content Analysis",
                            "description": "Analyze text for sentiment, topics, etc.",
                            "is_async": False,
                            "base_credits": 2,
                            "fields": [
                                {"name": "content", "type": "textarea", "required": True, "description": "Content to analyze"},
                                {"name": "analysis_type", "type": "multiselect", "options": ["sentiment", "topics", "keywords", "readability"], "description": "Types of analysis to perform"}
                            ]
                        }
                    }
                },
                "transform": {
                    "name": "Data Transformation",
                    "description": "Built-in data processing and transformation",
                    "category": "data",
                    "auth_type": "none",
                    "operations": {
                        "extract_data": {
                            "name": "Extract Data Fields",
                            "description": "Extract specific fields from data using JMESPath",
                            "is_async": False,
                            "base_credits": 0,
                            "fields": [
                                {"name": "source_field", "type": "string", "required": True, "description": "Source data field or JMESPath expression"},
                                {"name": "output_name", "type": "string", "required": True, "description": "Name for extracted data"},
                                {"name": "description", "type": "string", "required": False, "description": "Description of extraction"}
                            ]
                        },
                        "aggregate_data": {
                            "name": "Aggregate Data",
                            "description": "Perform calculations on data arrays",
                            "is_async": False,
                            "base_credits": 0,
                            "fields": [
                                {"name": "source_array", "type": "string", "required": True, "description": "Array field to aggregate"},
                                {"name": "function", "type": "select", "options": ["sum", "avg", "count", "min", "max", "first", "last"], "required": True, "description": "Aggregation function"},
                                {"name": "output_name", "type": "string", "required": True, "description": "Name for result"}
                            ]
                        },
                        "format_data": {
                            "name": "Format Data",
                            "description": "Format data as CSV, JSON, or other formats",
                            "is_async": False,
                            "base_credits": 0,
                            "fields": [
                                {"name": "source_data", "type": "string", "required": True, "description": "Data to format"},
                                {"name": "format_type", "type": "select", "options": ["join", "split", "upper", "lower", "csv"], "required": True, "description": "Format operation"},
                                {"name": "separator", "type": "string", "default": ", ", "description": "Separator for join/split operations"},
                                {"name": "output_name", "type": "string", "required": True, "description": "Name for formatted result"}
                            ]
                        }
                    }
                }
            }
        }
        
        # Filter by provider if specified
        if provider:
            if provider in tool_catalog["providers"]:
                tool_catalog["providers"] = {provider: tool_catalog["providers"][provider]}
            else:
                tool_catalog["providers"] = {}
        
        # Filter by category if specified  
        if category:
            filtered_providers = {}
            for provider_id, provider_data in tool_catalog["providers"].items():
                if provider_data.get("category") == category:
                    filtered_providers[provider_id] = provider_data
            tool_catalog["providers"] = filtered_providers
        
        return tool_catalog
        
    except Exception as e:
        logger.error(f"Failed to get tool catalog: {e}")
        raise HTTPException(status_code=500, detail="Failed to get tool catalog")


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


# Helper functions for workflow processing
def _validate_step(step: Dict[str, Any], step_index: int) -> List[str]:
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


async def _execute_workflow_steps(
    template: models.WorkflowTemplate, 
    execution: models.WorkflowExecution, 
    db: Session
) -> Dict[str, Any]:
    """Execute workflow steps using workflow engine"""
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
                elif step_type in ["task", "ai", "async_task"]:
                    result = await _execute_api_step(step, context, db, execution.business_id)
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
        if input_data is None:
            raise ValueError(f"No output data available from dependency step: {source_step}")
    else:
        # Get input data from step's input bindings or workflow inputs
        step_input = step.get("input", {})
        input_bindings = step_input.get("bindings", {})
        static_data = step_input.get("static", {})
        
        # Use static data if provided, otherwise get from context
        if static_data:
            input_data = static_data
        elif input_bindings:
            # Resolve input bindings using expression engine
            input_data = {}
            for key, expr in input_bindings.items():
                try:
                    if isinstance(expr, str) and expr.startswith("expr:"):
                        # Evaluate JMESPath expression
                        value = expression_engine.evaluate(expr[5:].strip(), context)
                    else:
                        # Use literal value
                        value = expr
                    input_data[key] = value
                except Exception as e:
                    logger.warning(f"Failed to resolve input binding {key}: {e}")
                    input_data[key] = expr
        else:
            # Get from workflow inputs as fallback
            input_data = context.get("inputs", {})
    
    if input_data is None:
        raise ValueError("No input data available for transform step")
    
    # Apply transformations
    result = data_transformation_service.apply_transformations(
        data=input_data,
        transform_config=transform_config,
        runtime_context=context
    )
    
    return result


async def _execute_api_step(step: Dict[str, Any], context: Dict[str, Any], 
                            db: Session, business_id: int) -> Dict[str, Any]:
    """Execute an API call step using real integration service"""
    try:
        from services.integration_service import IntegrationService
        
        connection_id = step.get("connection_id")
        operation = step.get("operation")
        
        if not connection_id:
            raise ValueError("API step missing connection_id")
        if not operation:
            raise ValueError("API step missing operation")
        
        # Resolve input data for the API call
        step_input = step.get("input", {})
        input_bindings = step_input.get("bindings", {})
        static_data = step_input.get("static", {})
        
        # Build input data from bindings and static data
        input_data = {}
        
        # Add static data first
        if static_data:
            input_data.update(static_data)
        
        # Resolve input bindings using expression engine
        if input_bindings:
            for key, expr in input_bindings.items():
                try:
                    if isinstance(expr, str) and expr.startswith("expr:"):
                        # Evaluate JMESPath expression against context
                        value = expression_engine.evaluate(expr[5:].strip(), context)
                    else:
                        # Use literal value
                        value = expr
                    input_data[key] = value
                except Exception as e:
                    logger.warning(f"Failed to resolve input binding {key}: {e}")
                    input_data[key] = expr
        
        # Initialize integration service
        integration_service = IntegrationService(db)
        
        # Execute the integration
        result = await integration_service.execute_integration(
            integration_name=connection_id,
            business_id=business_id,
            operation=operation,
            input_data=input_data
        )
        
        if result.get("success"):
            return {
                "status": "completed",
                "provider": result.get("provider"),
                "data": result.get("data"),
                "credits_used": result.get("credits_used", 0),
                "operation": operation
            }
        else:
            raise Exception(result.get("error", "Integration execution failed"))
            
    except ImportError:
        logger.error("IntegrationService not available - using fallback")
        # Fallback for when integration service is not available
        return {
            "status": "completed", 
            "provider": step.get("connection_id", "unknown"),
            "data": {"message": "Integration service not available - using fallback"},
            "credits_used": 0,
            "operation": step.get("operation"),
            "fallback": True
        }
    except Exception as e:
        logger.error(f"API step execution failed: {e}")
        raise Exception(f"API step failed: {str(e)}")
