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


@router.get("/templates/{template_id}/export")
async def export_workflow_template(
    template_id: int,
    include_metadata: bool = True,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Export a workflow template with all configurations and integration metadata"""
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
        
        # Build export data structure
        export_data = {
            "export_version": "1.0",
            "exported_at": datetime.utcnow().isoformat(),
            "exported_by": current_user.id,
            "workflow": {
                "name": template.name,
                "description": template.description,
                "category": template.category,
                "tags": template.tags,
                "schema_version": template.schema_version,
                "workflow_config": template.workflow_config,
                "execution_config": template.execution_config,
                "tool_catalog": template.tool_catalog,
                "credit_cost": template.credit_cost,
                "estimated_duration": template.estimated_duration,
                "tier_access": template.tier_access,
                "version": template.version,
                "icon": template.icon
            },
            "integrations": [],
            "dependencies": []
        }
        
        if include_metadata:
            # Collect integration requirements from workflow steps
            integrations_used = set()
            steps = template.workflow_config.get("steps", [])
            
            for step in steps:
                connection_id = step.get("connection_id")
                operation = step.get("operation")
                
                if connection_id:
                    integrations_used.add(connection_id)
            
            # Get integration details for each connection_id
            for integration_name in integrations_used:
                integration = db.query(models.Integration).filter(
                    models.Integration.provider_id == integration_name
                ).first()
                
                if integration:
                    export_data["integrations"].append({
                        "provider_id": integration.provider_id,
                        "name": integration.name,
                        "provider": integration.provider,
                        "integration_type": integration.integration_type,
                        "required": True,
                        "operations_used": [
                            step.get("operation") for step in steps 
                            if step.get("connection_id") == integration_name
                        ]
                    })
                else:
                    # Unknown integration
                    export_data["integrations"].append({
                        "provider_id": integration_name,
                        "name": f"Unknown Integration ({integration_name})",
                        "provider": "unknown",
                        "integration_type": "unknown",
                        "required": True,
                        "operations_used": [
                            step.get("operation") for step in steps 
                            if step.get("connection_id") == integration_name
                        ],
                        "status": "missing"
                    })
        
        return export_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to export workflow template: {e}")
        raise HTTPException(status_code=500, detail="Failed to export template")


@router.post("/templates/import")
async def import_workflow_template(
    import_data: Dict[str, Any],
    business_id: Optional[int] = None,
    override_name: Optional[str] = None,
    validate_only: bool = False,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Import a workflow template with graceful handling of missing integrations"""
    try:
        # Validate import data structure
        if "workflow" not in import_data:
            raise HTTPException(status_code=400, detail="Invalid import data: missing 'workflow' section")
        
        workflow_data = import_data["workflow"]
        required_fields = ["name", "workflow_config", "execution_config"]
        
        for field in required_fields:
            if field not in workflow_data:
                raise HTTPException(status_code=400, detail=f"Invalid import data: missing '{field}' in workflow section")
        
        # Check business access if specified
        if business_id:
            if not verify_business_access(db, current_user, business_id):
                raise HTTPException(status_code=403, detail="Access denied to business")
        
        # Validate integrations and build status report
        integration_status = []
        missing_integrations = []
        workflow_steps = workflow_data["workflow_config"].get("steps", [])
        
        for step in workflow_steps:
            connection_id = step.get("connection_id")
            if connection_id:
                # Check if integration exists in current system
                integration = db.query(models.Integration).filter(
                    models.Integration.provider_id == connection_id
                ).first()
                
                if integration:
                    # Check if business has access to this integration
                    if business_id:
                        business_integration = db.query(models.BusinessIntegration).filter(
                            models.BusinessIntegration.business_id == business_id,
                            models.BusinessIntegration.integration_id == integration.id,
                            models.BusinessIntegration.is_active == True
                        ).first()
                        
                        if business_integration:
                            integration_status.append({
                                "step_id": step.get("id"),
                                "connection_id": connection_id,
                                "integration_name": integration.name,
                                "status": "available",
                                "configured": True
                            })
                        else:
                            integration_status.append({
                                "step_id": step.get("id"),
                                "connection_id": connection_id,
                                "integration_name": integration.name,
                                "status": "not_configured",
                                "configured": False,
                                "message": "Integration exists but not configured for this business"
                            })
                    else:
                        integration_status.append({
                            "step_id": step.get("id"),
                            "connection_id": connection_id,
                            "integration_name": integration.name,
                            "status": "available",
                            "configured": True
                        })
                else:
                    # Integration not found in system
                    missing_integrations.append(connection_id)
                    integration_status.append({
                        "step_id": step.get("id"),
                        "connection_id": connection_id,
                        "integration_name": f"Unknown ({connection_id})",
                        "status": "missing",
                        "configured": False,
                        "message": "Integration not available in this system"
                    })
        
        # If validate_only is True, return status without creating the workflow
        if validate_only:
            return {
                "valid": len(missing_integrations) == 0,
                "integration_status": integration_status,
                "missing_integrations": missing_integrations,
                "workflow_name": workflow_data["name"],
                "total_steps": len(workflow_steps),
                "steps_with_integrations": len([s for s in workflow_steps if s.get("connection_id")])
            }
        
        # Create the workflow template, preserving all settings except missing integrations
        new_template = models.WorkflowTemplate(
            name = override_name or workflow_data["name"],
            description = workflow_data.get("description"),
            category = workflow_data.get("category", "imported"),
            tags = workflow_data.get("tags", []),
            schema_version = workflow_data.get("schema_version", "ryvr.workflow.v1"),
            workflow_config = workflow_data["workflow_config"],
            execution_config = workflow_data["execution_config"],
            tool_catalog = workflow_data.get("tool_catalog"),
            business_id = business_id,
            credit_cost = workflow_data.get("credit_cost", 0),
            estimated_duration = workflow_data.get("estimated_duration"),
            tier_access = workflow_data.get("tier_access", []),
            status = "draft",  # Always import as draft for review
            version = workflow_data.get("version", "1.0"),
            icon = workflow_data.get("icon"),
            created_by = current_user.id
        )
        
        db.add(new_template)
        db.flush()  # Get the ID but don't commit yet
        
        # Add import metadata to track import details
        import_metadata = {
            "imported_at": datetime.utcnow().isoformat(),
            "imported_by": current_user.id,
            "import_source": import_data.get("exported_by"),
            "original_export_date": import_data.get("exported_at"),
            "export_version": import_data.get("export_version"),
            "integration_status": integration_status,
            "missing_integrations": missing_integrations
        }
        
        # Store import metadata in the tool_catalog field if it's empty
        if not new_template.tool_catalog:
            new_template.tool_catalog = {"import_metadata": import_metadata}
        else:
            new_template.tool_catalog["import_metadata"] = import_metadata
        
        db.commit()
        
        return {
            "success": True,
            "template_id": new_template.id,
            "template_name": new_template.name,
            "status": new_template.status,
            "integration_status": integration_status,
            "missing_integrations": missing_integrations,
            "warnings": [
                f"Step '{status['step_id']}' has missing integration '{status['connection_id']}'"
                for status in integration_status if status["status"] == "missing"
            ],
            "message": f"Workflow imported successfully. {len(missing_integrations)} integration(s) need to be reconnected." if missing_integrations else "Workflow imported successfully with all integrations available."
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to import workflow template: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to import template: {str(e)}")


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
        # Get OpenAI models from database for dynamic model options
        openai_models = []
        default_model = "gpt-4o-mini"
        try:
            from services.openai_model_service import OpenAIModelService
            model_service = OpenAIModelService(db)
            models_data = await model_service.get_models_for_dropdown()
            openai_models = [model["id"] for model in models_data if model.get("id")]
            # Get default model
            for model in models_data:
                if model.get("is_default"):
                    default_model = model["id"]
                    break
            logger.info(f"Loaded {len(openai_models)} OpenAI models from database, default: {default_model}")
        except Exception as e:
            logger.warning(f"Failed to fetch OpenAI models from database, using fallback: {e}")
            openai_models = ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-4", "gpt-3.5-turbo"]
        
        # Start with hardcoded tool catalog
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
                                {"name": "system_prompt", "type": "textarea", "required": False, "description": "System message to set AI behavior (optional)"},
                                {"name": "prompt", "type": "textarea", "required": True, "description": "Text prompt for AI"},
                                {
                                    "name": "model", 
                                    "type": "select", 
                                    "options": openai_models,  # Dynamic models from database
                                    "default": default_model, 
                                    "required": False,
                                    "description": "AI model to use"
                                },
                                {"name": "max_tokens", "type": "integer", "default": 2000, "min": 1, "max": 128000, "required": False, "description": "Maximum tokens to generate"},
                                {"name": "temperature", "type": "number", "default": 0.7, "min": 0, "max": 2, "step": 0.1, "required": False, "description": "Creativity level (0=conservative, 2=creative)"},
                                {"name": "top_p", "type": "number", "default": 1.0, "min": 0, "max": 1, "step": 0.1, "required": False, "description": "Nucleus sampling (alternative to temperature)"},
                                {"name": "frequency_penalty", "type": "number", "default": 0.0, "min": -2.0, "max": 2.0, "step": 0.1, "required": False, "description": "Penalize frequent tokens"},
                                {"name": "presence_penalty", "type": "number", "default": 0.0, "min": -2.0, "max": 2.0, "step": 0.1, "required": False, "description": "Penalize repeated topics"}
                            ]
                        },
                        "content_analysis": {
                            "name": "Content Analysis",
                            "description": "Analyze text for sentiment, topics, etc.",
                            "is_async": False,
                            "base_credits": 2,
                            "fields": [
                                {"name": "content", "type": "textarea", "required": True, "description": "Content to analyze"},
                                {"name": "analysis_type", "type": "select", "options": ["seo", "sentiment", "keywords", "general"], "default": "general", "description": "Type of analysis to perform"},
                                {"name": "instructions", "type": "textarea", "required": False, "description": "Additional analysis instructions (optional)"},
                                {
                                    "name": "model", 
                                    "type": "select", 
                                    "options": openai_models,  # Dynamic models from database
                                    "default": default_model, 
                                    "required": False,
                                    "description": "AI model to use"
                                }
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
                },
                "content_extractor": {
                    "name": "Web Content Extractor",
                    "description": "Extract content from web pages",
                    "category": "content",
                    "auth_type": "none",
                    "operations": {
                        "extract_content": {
                            "name": "Extract Web Content",
                            "description": "Extract content from a list of URLs",
                            "is_async": False,
                            "base_credits": 2,
                            "fields": [
                                {"name": "urlSource", "type": "textarea", "required": True, "description": "URL(s) to extract content from (supports variables like {{node.path}})"},
                                {"name": "maxUrls", "type": "integer", "default": 10, "min": 1, "max": 50, "description": "Maximum number of URLs to process"},
                                {"name": "maxLength", "type": "integer", "default": 8000, "min": 100, "max": 50000, "description": "Maximum content length per URL"},
                                {"name": "extractionType", "type": "select", "options": ["full_text", "summary", "metadata"], "default": "full_text", "description": "Type of content to extract"}
                            ]
                        }
                    }
                },
                "wordpress": {
                    "name": "WordPress",
                    "description": "WordPress content management and synchronization",
                    "category": "content",
                    "auth_type": "api_key",
                    "operations": {
                        "extract_posts": {
                            "name": "Extract Posts",
                            "description": "Extract posts and pages from WordPress",
                            "is_async": True,
                            "base_credits": 2,
                            "fields": [
                                {"name": "post_type", "type": "select", "options": ["post", "page", "any"], "default": "post", "description": "Type of content to extract"},
                                {"name": "status", "type": "select", "options": ["publish", "draft", "private", "any"], "default": "any", "description": "Post status filter"},
                                {"name": "limit", "type": "integer", "default": 50, "min": 1, "max": 100, "description": "Number of posts to extract"},
                                {"name": "modified_after", "type": "datetime", "description": "Only extract posts modified after this date"},
                                {"name": "include_acf", "type": "checkbox", "default": True, "description": "Include ACF custom fields"},
                                {"name": "include_seo", "type": "checkbox", "default": True, "description": "Include RankMath SEO data"},
                                {"name": "include_taxonomies", "type": "checkbox", "default": True, "description": "Include categories and tags"}
                            ]
                        },
                        "publish_content": {
                            "name": "Publish Content",
                            "description": "Publish content to WordPress",
                            "is_async": True,
                            "base_credits": 3,
                            "fields": [
                                {"name": "title", "type": "string", "required": True, "description": "Post title"},
                                {"name": "content", "type": "textarea", "required": True, "description": "Post content (HTML allowed)"},
                                {"name": "excerpt", "type": "textarea", "description": "Post excerpt"},
                                {"name": "status", "type": "select", "options": ["draft", "publish", "private"], "default": "draft", "description": "Post status"},
                                {"name": "post_type", "type": "select", "options": ["post", "page"], "default": "post", "description": "Content type"},
                                {"name": "categories", "type": "multiselect", "description": "Post categories"},
                                {"name": "tags", "type": "multiselect", "description": "Post tags"},
                                {"name": "acf_fields", "type": "json", "description": "ACF custom fields (JSON object)"},
                                {"name": "seo_title", "type": "string", "description": "SEO title"},
                                {"name": "meta_description", "type": "textarea", "description": "Meta description"},
                                {"name": "focus_keyword", "type": "string", "description": "Primary SEO keyword"}
                            ]
                        },
                        "sync_content": {
                            "name": "Sync Content",
                            "description": "Bidirectional content synchronization",
                            "is_async": True,
                            "base_credits": 5,
                            "fields": [
                                {"name": "direction", "type": "select", "options": ["to_wordpress", "from_wordpress", "both"], "default": "both", "description": "Sync direction"},
                                {"name": "post_ids", "type": "multiselect", "description": "Specific post IDs to sync (leave empty for all)"},
                                {"name": "sync_acf", "type": "checkbox", "default": True, "description": "Sync ACF fields"},
                                {"name": "sync_seo", "type": "checkbox", "default": True, "description": "Sync SEO data"},
                                {"name": "sync_taxonomies", "type": "checkbox", "default": True, "description": "Sync categories and tags"},
                                {"name": "conflict_resolution", "type": "select", "options": ["skip", "overwrite_wp", "overwrite_ryvr"], "default": "skip", "description": "How to handle conflicts"}
                            ]
                        },
                        "get_site_info": {
                            "name": "Get Site Info",
                            "description": "Get WordPress site information and capabilities",
                            "is_async": False,
                            "base_credits": 1,
                            "fields": []
                        }
                    }
                }
            }
        }
        
        # Add dynamic integrations from database
        dynamic_integrations = db.query(models.Integration).filter(
            models.Integration.is_dynamic == True,
            models.Integration.is_active == True
        ).all()
        
        for integration in dynamic_integrations:
            if not integration.operation_configs or not integration.operation_configs.get('operations'):
                continue
                
            provider_id = integration.provider.lower().replace(' ', '_')
            
            # Skip if this provider already exists in hardcoded catalog
            if provider_id in tool_catalog["providers"]:
                continue
                
            # Build operations dict from operation_configs
            operations = {}
            for op_config in integration.operation_configs['operations']:
                # Convert parameters to fields format
                fields = []
                for param in op_config.get('parameters', []):
                    field = {
                        "name": param['name'],
                        "type": param['type'],
                        "required": param['required'],
                        "description": param.get('description', '')
                    }
                    if param.get('default'):
                        field['default'] = param['default']
                    if param['type'] == 'select' and param.get('options'):
                        field['options'] = param['options']
                    if not param.get('fixed', False):
                        fields.append(field)
                
                # Build async config if operation is async
                operation_data = {
                    "name": op_config['name'],
                    "description": op_config.get('description', ''),
                    "is_async": op_config.get('is_async', False),
                    "base_credits": op_config.get('base_credits', 1),
                    "fields": fields
                }
                
                if op_config.get('is_async') and op_config.get('async_config'):
                    operation_data['async_config'] = op_config['async_config']
                
                operations[op_config['id']] = operation_data
            
            # Add to tool catalog
            tool_catalog["providers"][provider_id] = {
                "name": integration.name,
                "description": integration.platform_config.get('description', f"{integration.name} integration"),
                "category": integration.platform_config.get('category', 'other'),
                "auth_type": integration.platform_config.get('auth_type', 'api_key'),
                "operations": operations,
                "is_dynamic": True,
                "color": integration.platform_config.get('color', '#5f5eff'),
                "icon_url": integration.platform_config.get('icon_url'),
                "documentation_url": integration.platform_config.get('documentation_url')
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
