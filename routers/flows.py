"""
Flow Management API - Kanban-style interface for workflow executions

This provides a user-friendly interface for managing workflow executions
as "flows" with Kanban-style status tracking.
"""

from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc, asc
from datetime import datetime, timezone

from database import get_db
from auth import get_current_active_user
import models
from services.credit_service import CreditService
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/flows", tags=["flows"])

# =============================================================================
# FLOW MANAGEMENT ENDPOINTS
# =============================================================================

@router.get("/businesses/{business_id}/flows")
async def list_flows(
    business_id: int,
    status: Optional[str] = Query(None, description="Filter by flow status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Get all flows for a business with Kanban-style information"""
    try:
        # Verify business access
        business = db.query(models.Business).filter(models.Business.id == business_id).first()
        if not business:
            raise HTTPException(status_code=404, detail="Business not found")
        
        # TODO: Add proper permission checking here
        # For now, allow access if user has any relationship to the business
        
        # Build query
        query = db.query(models.WorkflowExecution).filter(
            models.WorkflowExecution.business_id == business_id
        )
        
        # Filter by status if provided
        if status:
            query = query.filter(models.WorkflowExecution.flow_status == status)
        
        # Order by created_at desc (newest first)
        query = query.order_by(desc(models.WorkflowExecution.created_at))
        
        # Apply pagination
        executions = query.offset(skip).limit(limit).all()
        
        # Transform to flow cards
        flow_cards = []
        for execution in executions:
            # Calculate progress
            progress = 0
            if execution.total_steps > 0:
                progress = int((execution.completed_steps / execution.total_steps) * 100)
            
            # Get pending reviews
            pending_reviews = []
            if execution.flow_status == 'in_review':
                reviews = db.query(models.FlowReviewApproval).filter(
                    and_(
                        models.FlowReviewApproval.execution_id == execution.id,
                        models.FlowReviewApproval.reviewed_at.is_(None)
                    )
                ).all()
                
                for review in reviews:
                    pending_reviews.append({
                        "step_id": review.step_id,
                        "reviewer_needed": review.reviewer_type,
                        "submitted_at": review.submitted_for_review_at.isoformat()
                    })
            
            flow_card = {
                "id": execution.id,
                "title": execution.flow_title or execution.template.name,
                "template_name": execution.template.name,
                "template_id": execution.template_id,
                "business_id": execution.business_id,
                "status": execution.flow_status,
                "progress": progress,
                "current_step": execution.current_step,
                "total_steps": execution.total_steps,
                "completed_steps": execution.completed_steps,
                "created_at": execution.created_at.isoformat(),
                "created_by": execution.template.created_by,  # TODO: Track actual flow creator
                "credits_used": execution.credits_used,
                "estimated_duration": execution.template.estimated_duration,
                "custom_field_values": execution.custom_field_values or {},
                "pending_reviews": pending_reviews,
                "tags": execution.template.tags or [],
                "error_message": execution.error_message
            }
            flow_cards.append(flow_card)
        
        return {
            "flows": flow_cards,
            "total": query.count(),
            "skip": skip,
            "limit": limit
        }
        
    except Exception as e:
        logger.error(f"Error listing flows for business {business_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to list flows")


@router.post("/businesses/{business_id}/flows")
async def create_flow(
    business_id: int,
    flow_request: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Create a new flow from a workflow template"""
    try:
        # Verify business access
        business = db.query(models.Business).filter(models.Business.id == business_id).first()
        if not business:
            raise HTTPException(status_code=404, detail="Business not found")
        
        # Get template
        template_id = flow_request.get("template_id")
        template = db.query(models.WorkflowTemplate).filter(models.WorkflowTemplate.id == template_id).first()
        if not template:
            raise HTTPException(status_code=404, detail="Workflow template not found")
        
        # Check if template is published
        if template.status != 'published':
            raise HTTPException(status_code=400, detail="Template is not published")
        
        # Check credits
        credit_service = CreditService(db)
        if not credit_service.check_business_credits(business_id, template.credit_cost):
            raise HTTPException(status_code=402, detail="Insufficient credits")
        
        # Create runtime state with custom field values
        runtime_state = {
            "inputs": template.workflow_config.get("inputs", {}),
            "globals": template.workflow_config.get("globals", {}),
            "steps": {},
            "runtime": {}
        }
        
        # Apply custom field values if provided
        custom_field_values = flow_request.get("custom_field_values", {})
        if custom_field_values:
            # TODO: Implement proper field value application using editable_fields
            # For now, store them in the execution for later use
            pass
        
        # Create execution
        flow_title = flow_request.get("title", template.name)
        execution_mode = flow_request.get("execution_mode", "live")
        scheduled_for = flow_request.get("scheduled_for")
        
        # Determine initial flow status
        flow_status = "scheduled" if scheduled_for else "new"
        
        execution = models.WorkflowExecution(
            template_id=template_id,
            business_id=business_id,
            execution_mode=execution_mode,
            runtime_state=runtime_state,
            total_steps=len(template.workflow_config.get("steps", [])),
            flow_status=flow_status,
            flow_title=flow_title,
            custom_field_values=custom_field_values
        )
        
        db.add(execution)
        db.commit()
        db.refresh(execution)
        
        logger.info(f"Created flow {execution.id} for business {business_id} from template {template_id}")
        
        return {
            "flow_id": execution.id,
            "status": execution.flow_status,
            "message": "Flow created successfully"
        }
        
    except Exception as e:
        logger.error(f"Error creating flow: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to create flow")


@router.patch("/flows/{flow_id}")
async def update_flow(
    flow_id: int,
    update_request: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Update flow status or other properties"""
    try:
        # Get execution
        execution = db.query(models.WorkflowExecution).filter(models.WorkflowExecution.id == flow_id).first()
        if not execution:
            raise HTTPException(status_code=404, detail="Flow not found")
        
        # TODO: Add proper permission checking
        
        # Update allowed fields
        if "status" in update_request:
            execution.flow_status = update_request["status"]
        
        if "title" in update_request:
            execution.flow_title = update_request["title"]
        
        if "custom_field_values" in update_request:
            execution.custom_field_values = update_request["custom_field_values"]
        
        db.commit()
        db.refresh(execution)
        
        logger.info(f"Updated flow {flow_id}")
        
        return {"message": "Flow updated successfully"}
        
    except Exception as e:
        logger.error(f"Error updating flow {flow_id}: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to update flow")


@router.post("/flows/{flow_id}/start")
async def start_flow(
    flow_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Start execution of a flow"""
    try:
        # Get execution
        execution = db.query(models.WorkflowExecution).filter(models.WorkflowExecution.id == flow_id).first()
        if not execution:
            raise HTTPException(status_code=404, detail="Flow not found")
        
        # Check if flow can be started
        if execution.flow_status not in ['new', 'scheduled', 'error']:
            raise HTTPException(status_code=400, detail="Flow cannot be started from current status")
        
        # Update status and start execution
        execution.flow_status = "in_progress"
        execution.status = "running"
        execution.started_at = datetime.now(timezone.utc)
        
        db.commit()
        
        # TODO: Trigger actual workflow execution here
        # For now, just update the status
        
        logger.info(f"Started flow {flow_id}")
        
        return {"message": "Flow started successfully"}
        
    except Exception as e:
        logger.error(f"Error starting flow {flow_id}: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to start flow")


@router.post("/flows/{flow_id}/reviews/{step_id}/approve")
async def approve_review(
    flow_id: int,
    step_id: str,
    approval_request: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Approve a review step in a flow"""
    try:
        # Get execution
        execution = db.query(models.WorkflowExecution).filter(models.WorkflowExecution.id == flow_id).first()
        if not execution:
            raise HTTPException(status_code=404, detail="Flow not found")
        
        # Find pending review
        review = db.query(models.FlowReviewApproval).filter(
            and_(
                models.FlowReviewApproval.execution_id == flow_id,
                models.FlowReviewApproval.step_id == step_id,
                models.FlowReviewApproval.reviewed_at.is_(None)
            )
        ).first()
        
        if not review:
            raise HTTPException(status_code=404, detail="Pending review not found")
        
        # TODO: Check if user has permission to approve this review
        
        # Record approval
        review.approved = approval_request.get("approved", True)
        review.comments = approval_request.get("comments")
        review.reviewed_by = current_user.id
        review.reviewed_at = datetime.now(timezone.utc)
        
        # Check if all reviews for this execution are complete
        remaining_reviews = db.query(models.FlowReviewApproval).filter(
            and_(
                models.FlowReviewApproval.execution_id == flow_id,
                models.FlowReviewApproval.reviewed_at.is_(None)
            )
        ).count()
        
        # If no more pending reviews, move flow back to in_progress
        if remaining_reviews == 0:
            execution.flow_status = "in_progress"
        
        db.commit()
        
        logger.info(f"Approved review for flow {flow_id}, step {step_id}")
        
        return {"message": "Review approved successfully"}
        
    except Exception as e:
        logger.error(f"Error approving review: {str(e)}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to approve review")


# =============================================================================
# FLOW TEMPLATE ENDPOINTS
# =============================================================================

@router.get("/templates")
async def list_published_templates(
    category: Optional[str] = Query(None),
    tags: Optional[str] = Query(None),
    business_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Get published workflow templates for flow creation"""
    try:
        # Base query for published templates
        query = db.query(models.WorkflowTemplate).filter(
            models.WorkflowTemplate.status == 'published'
        )
        
        # Apply filters
        if category:
            query = query.filter(models.WorkflowTemplate.category == category)
        
        if tags:
            tag_list = [tag.strip() for tag in tags.split(',')]
            # PostgreSQL JSONB array contains any of the tags
            for tag in tag_list:
                query = query.filter(models.WorkflowTemplate.tags.contains([tag]))
        
        # TODO: Add business/agency tier filtering based on tier_access
        
        templates = query.order_by(asc(models.WorkflowTemplate.name)).all()
        
        # Transform to flow template format
        flow_templates = []
        for template in templates:
            # Extract editable fields from workflow config
            editable_fields = []
            steps = template.workflow_config.get("steps", [])
            for step in steps:
                if step.get("editable_fields"):
                    for field_path in step["editable_fields"]:
                        editable_fields.append({
                            "step_id": step["id"],
                            "path": field_path,
                            "label": f"{step.get('name', step['id'])} - {field_path}",
                            "type": "text"  # TODO: Infer type from field
                        })
            
            flow_template = {
                "id": template.id,
                "name": template.name,
                "description": template.description,
                "category": template.category,
                "tags": template.tags or [],
                "icon": template.icon,
                "credit_cost": template.credit_cost,
                "estimated_duration": template.estimated_duration,
                "editable_fields": editable_fields,
                "step_count": len(steps),
                "created_at": template.created_at.isoformat()
            }
            flow_templates.append(flow_template)
        
        return {"templates": flow_templates}
        
    except Exception as e:
        logger.error(f"Error listing published templates: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to list templates")


@router.get("/templates/{template_id}/preview")
async def get_template_preview(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Get a simplified preview of what a template will do"""
    try:
        template = db.query(models.WorkflowTemplate).filter(models.WorkflowTemplate.id == template_id).first()
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")
        
        if template.status != 'published':
            raise HTTPException(status_code=404, detail="Template not available")
        
        # Create simplified step descriptions
        steps = template.workflow_config.get("steps", [])
        preview_steps = []
        
        for i, step in enumerate(steps):
            step_type = step.get("type", "unknown")
            step_name = step.get("name", f"Step {i+1}")
            
            # Create user-friendly descriptions without exposing technical details
            if step_type == "ai":
                description = "AI analysis and content generation"
            elif step_type == "task":
                operation = step.get("operation", "")
                if "seo" in operation.lower():
                    description = "SEO data collection and analysis"
                elif "search" in operation.lower():
                    description = "Search results gathering"
                else:
                    description = "Data collection and processing"
            elif step_type == "transform":
                description = "Data processing and formatting"
            elif step_type == "review":
                description = "Review and approval checkpoint"
            else:
                description = f"Process step ({step_type})"
            
            preview_step = {
                "order": i + 1,
                "name": step_name,
                "description": description,
                "is_review": step_type == "review",
                "is_editable": bool(step.get("editable_fields"))
            }
            preview_steps.append(preview_step)
        
        return {
            "template": {
                "id": template.id,
                "name": template.name,
                "description": template.description,
                "category": template.category,
                "credit_cost": template.credit_cost,
                "estimated_duration": template.estimated_duration
            },
            "steps": preview_steps,
            "total_steps": len(preview_steps),
            "has_reviews": any(step["is_review"] for step in preview_steps),
            "has_editable_fields": any(step["is_editable"] for step in preview_steps)
        }
        
    except Exception as e:
        logger.error(f"Error getting template preview: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get template preview")


# =============================================================================
# OPTIONS SELECTION ENDPOINTS
# =============================================================================

@router.post("/flows/{flow_id}/select-options")
async def submit_options_selection(
    flow_id: int,
    step_id: str,
    selection: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Submit options selection for a flow waiting for input"""
    try:
        from services.flow_control_service import get_flow_control_service
        
        # Get execution
        execution = db.query(models.WorkflowExecution).filter(
            models.WorkflowExecution.id == flow_id
        ).first()
        
        if not execution:
            raise HTTPException(status_code=404, detail="Flow not found")
        
        # Verify business access
        # TODO: Add proper permission checking
        
        # Verify flow is waiting for input
        if execution.flow_status != 'input_required':
            raise HTTPException(
                status_code=400,
                detail=f"Flow is not waiting for input (current status: {execution.flow_status})"
            )
        
        # Process selection
        flow_control = get_flow_control_service(db)
        result = await flow_control.process_options_selection(
            execution_id=flow_id,
            step_id=step_id,
            selected_options=selection.get('selected_options', []),
            user_id=current_user.id
        )
        
        return {
            "success": True,
            "message": "Options selection submitted successfully",
            "flow_id": flow_id,
            "step_id": step_id,
            "result": result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error submitting options selection: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to submit options selection: {str(e)}")


@router.get("/flows/{flow_id}/options/{step_id}")
async def get_flow_options_data(
    flow_id: int,
    step_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Get available options for a flow waiting for selection"""
    try:
        # Get options selection record
        options_selection = db.query(models.FlowOptionsSelection).filter(
            and_(
                models.FlowOptionsSelection.execution_id == flow_id,
                models.FlowOptionsSelection.step_id == step_id,
                models.FlowOptionsSelection.selected_at.is_(None)
            )
        ).first()
        
        if not options_selection:
            raise HTTPException(status_code=404, detail="Options selection not found or already completed")
        
        return {
            "success": True,
            "flow_id": flow_id,
            "step_id": step_id,
            "available_options": options_selection.available_options,
            "selection_mode": options_selection.selection_mode
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting flow options: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get flow options")


# =============================================================================
# REVIEW WITH EDITS ENDPOINTS
# =============================================================================

@router.post("/flows/{flow_id}/review/{step_id}/approve-with-edits")
async def approve_review_with_edits(
    flow_id: int,
    step_id: str,
    approval: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Approve or reject review with optional edits to previous steps"""
    try:
        from services.flow_control_service import get_flow_control_service
        
        # Get execution
        execution = db.query(models.WorkflowExecution).filter(
            models.WorkflowExecution.id == flow_id
        ).first()
        
        if not execution:
            raise HTTPException(status_code=404, detail="Flow not found")
        
        # Verify flow is in review status
        if execution.flow_status != 'in_review':
            raise HTTPException(
                status_code=400,
                detail=f"Flow is not in review (current status: {execution.flow_status})"
            )
        
        # Process review approval
        flow_control = get_flow_control_service(db)
        result = await flow_control.process_review_approval(
            execution_id=flow_id,
            step_id=step_id,
            approval_data=approval,
            user_id=current_user.id
        )
        
        return {
            "success": True,
            "message": "Review processed successfully",
            "flow_id": flow_id,
            "step_id": step_id,
            "approved": approval.get('approved', False),
            "result": result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing review: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to process review: {str(e)}")


@router.get("/flows/{flow_id}/editable-data")
async def get_editable_data(
    flow_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Get editable data from previous steps for review editing"""
    try:
        # Get execution
        execution = db.query(models.WorkflowExecution).filter(
            models.WorkflowExecution.id == flow_id
        ).first()
        
        if not execution:
            raise HTTPException(status_code=404, detail="Flow not found")
        
        # Get pending review to find editable nodes
        review = db.query(models.FlowReviewApproval).filter(
            and_(
                models.FlowReviewApproval.execution_id == flow_id,
                models.FlowReviewApproval.reviewed_at.is_(None)
            )
        ).first()
        
        if not review:
            raise HTTPException(status_code=404, detail="No pending review found")
        
        # Get step executions for the workflow
        step_executions = db.query(models.WorkflowStepExecution).filter(
            models.WorkflowStepExecution.execution_id == flow_id
        ).order_by(models.WorkflowStepExecution.created_at).all()
        
        # Build editable data structure
        editable_steps = []
        for step_exec in step_executions:
            if step_exec.status == 'completed' and step_exec.output_data:
                editable_steps.append({
                    "step_id": step_exec.step_id,
                    "step_name": step_exec.step_name,
                    "step_type": step_exec.step_type,
                    "output_data": step_exec.output_data,
                    "input_data": step_exec.input_data,
                    "editable_fields": step_exec.editable_fields or []
                })
        
        return {
            "success": True,
            "flow_id": flow_id,
            "editable_steps": editable_steps,
            "runtime_state": execution.runtime_state or {}
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting editable data: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get editable data")
