"""
Workflow Executor Service
Handles complete workflow execution from start to finish with progress tracking
"""

import logging
import asyncio
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from database import SessionLocal
import models
from services.credit_service import CreditService
from services.integration_service import IntegrationService
from services.expression_engine import ExpressionEngine

logger = logging.getLogger(__name__)


async def execute_workflow_async(execution_id: int, db: Session = None):
    """
    Execute a workflow asynchronously in the background
    
    Args:
        execution_id: ID of the WorkflowExecution to run
        db: Database session (will create new one if not provided)
    """
    # Create new session for background task
    if not db:
        db = SessionLocal()
    
    try:
        executor = WorkflowExecutor(db)
        await executor.execute(execution_id)
    except Exception as e:
        logger.error(f"Background workflow execution failed for {execution_id}: {str(e)}", exc_info=True)
    finally:
        if not db:
            db.close()


class WorkflowExecutor:
    """Executes V2 workflows with full progress tracking"""
    
    def __init__(self, db: Session):
        self.db = db
        self.credit_service = CreditService(db)
        self.integration_service = IntegrationService(db)
        self.expression_engine = ExpressionEngine()
    
    async def execute(self, execution_id: int):
        """
        Main execution method - runs the entire workflow
        
        Args:
            execution_id: ID of the WorkflowExecution to run
        """
        try:
            # Get execution and template
            execution = self.db.query(models.WorkflowExecution).filter(
                models.WorkflowExecution.id == execution_id
            ).first()
            
            if not execution:
                logger.error(f"Execution {execution_id} not found")
                return
            
            template = execution.template
            if not template:
                logger.error(f"Template not found for execution {execution_id}")
                self._fail_execution(execution, "Template not found")
                return
            
            logger.info(f"Starting workflow execution {execution_id} from template {template.id}: {template.name}")
            
            # Initialize runtime state
            if not execution.runtime_state:
                execution.runtime_state = {
                    "inputs": template.workflow_config.get("inputs", {}),
                    "globals": template.workflow_config.get("globals", {}),
                    "steps": {},
                    "runtime": {
                        "business_id": execution.business_id,
                        "execution_id": execution_id,
                        "started_at": datetime.now(timezone.utc).isoformat()
                    }
                }
            
            # Get steps from template
            steps = template.workflow_config.get("steps", [])
            
            if not steps:
                logger.warning(f"No steps found in template {template.id}")
                self._complete_execution(execution, "No steps to execute")
                return
            
            # Update total steps
            execution.total_steps = len(steps)
            execution.completed_steps = 0
            self.db.commit()
            
            logger.info(f"Executing {len(steps)} steps for workflow {execution_id}")
            
            # Execute each step
            for step_index, step in enumerate(steps):
                step_id = step.get("id", f"step_{step_index}")
                step_type = step.get("type", "unknown")
                step_name = step.get("name", step_id)
                
                logger.info(f"Executing step {step_index + 1}/{len(steps)}: {step_name} ({step_type})")
                
                # Update current step
                execution.current_step = step_id
                execution.completed_steps = step_index
                self.db.commit()
                
                # Execute the step
                try:
                    result = await self._execute_step(execution, step)
                    
                    # Store step result in runtime state
                    if not execution.runtime_state.get("steps"):
                        execution.runtime_state["steps"] = {}
                    
                    execution.runtime_state["steps"][step_id] = {
                        "result": result,
                        "completed_at": datetime.now(timezone.utc).isoformat(),
                        "status": "success"
                    }
                    
                    # Update step results
                    if not execution.step_results:
                        execution.step_results = {}
                    execution.step_results[step_id] = result
                    
                    # Track credits
                    credits_used = result.get("credits_used", 0)
                    execution.credits_used += credits_used
                    
                    self.db.commit()
                    
                    logger.info(f"Step {step_name} completed successfully")
                    
                except Exception as step_error:
                    logger.error(f"Step {step_name} failed: {str(step_error)}", exc_info=True)
                    
                    # Record step failure
                    execution.failed_step = step_id
                    execution.error_message = str(step_error)
                    
                    # Store error in runtime state
                    if not execution.runtime_state.get("steps"):
                        execution.runtime_state["steps"] = {}
                    execution.runtime_state["steps"][step_id] = {
                        "error": str(step_error),
                        "failed_at": datetime.now(timezone.utc).isoformat(),
                        "status": "failed"
                    }
                    
                    self._fail_execution(execution, f"Step '{step_name}' failed: {str(step_error)}")
                    return
            
            # All steps completed successfully
            execution.completed_steps = len(steps)
            self._complete_execution(execution, "All steps completed successfully")
            
        except Exception as e:
            logger.error(f"Workflow execution {execution_id} failed: {str(e)}", exc_info=True)
            execution = self.db.query(models.WorkflowExecution).filter(
                models.WorkflowExecution.id == execution_id
            ).first()
            if execution:
                self._fail_execution(execution, str(e))
    
    async def _execute_step(self, execution: models.WorkflowExecution, step: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a single workflow step using dynamic integration system
        
        Args:
            execution: WorkflowExecution instance
            step: Step configuration from workflow_config
            
        Returns:
            Step execution result
        """
        # Extract step info - handle both direct and nested structures
        step_id = step.get("id")
        step_name = step.get("name", step_id)
        
        # Get the actual step type - check top-level first, then nested bindings
        raw_type = step.get("type")
        
        # If top-level type is missing or generic, try to get more specific type from bindings
        if not raw_type or raw_type in ["email", "task", "unknown"]:
            # Check nested structure
            input_data = step.get("input", {})
            bindings = input_data.get("bindings", {})
            if bindings.get("type"):
                raw_type = bindings.get("type")
        
        # Map specific node types to generic step types
        step_type = self._map_node_type_to_step_type(raw_type)
        
        logger.info(f"Executing step {step_id}: raw_type={raw_type}, mapped_type={step_type}")
        
        # Create step execution record
        step_execution = models.WorkflowStepExecution(
            execution_id=execution.id,
            step_id=step_id,
            step_type=step_type,
            step_name=step_name,
            status="running",
            input_data=step,  # Store the full step config
            started_at=datetime.now(timezone.utc)
        )
        self.db.add(step_execution)
        self.db.commit()
        
        try:
            result = {}
            
            # Route execution based on step type
            if step_type == "trigger":
                result = await self._execute_trigger_step(execution, step)
            elif step_type in ["api_call", "task", "ai", "seo", "data_extraction", "email"]:
                # Use unified integration execution for all integration-based steps
                result = await self._execute_integration_step(execution, step, raw_type)
            elif step_type == "transform":
                result = await self._execute_transform_step(execution, step)
            elif step_type == "review":
                result = await self._execute_review_step(execution, step)
            elif step_type == "options":
                result = await self._execute_options_step(execution, step)
            elif step_type == "conditional":
                result = await self._execute_conditional_step(execution, step)
            else:
                result = {
                    "success": False,
                    "error": f"Unsupported step type: {step_type}",
                    "step_type": step_type
                }
            
            # Update step execution
            step_execution.status = "completed" if result.get("success", True) else "failed"
            step_execution.output_data = result
            step_execution.completed_at = datetime.now(timezone.utc)
            step_execution.credits_used = result.get("credits_used", 0)
            self.db.commit()
            
            return result
            
        except Exception as e:
            step_execution.status = "failed"
            step_execution.error_data = {"error": str(e)}
            step_execution.completed_at = datetime.now(timezone.utc)
            self.db.commit()
            raise
    
    def _map_node_type_to_step_type(self, raw_type: str) -> str:
        """
        Map specific node types to generic step types for execution routing
        
        Args:
            raw_type: The raw type from the workflow node (e.g. 'seo_serp_analyze', 'ai_openai_task')
            
        Returns:
            Generic step type (e.g. 'seo', 'ai', 'task')
        """
        if not raw_type:
            return "task"
        
        # Trigger nodes
        if raw_type == "trigger" or "trigger" in raw_type:
            return "trigger"
        
        # SEO nodes
        if raw_type.startswith("seo_"):
            return "seo"
        
        # AI nodes (OpenAI, Claude, etc.)
        if raw_type.startswith("ai_") or "openai" in raw_type or "claude" in raw_type or "anthropic" in raw_type:
            return "ai"
        
        # Content extraction
        if raw_type.startswith("content_extract") or raw_type == "content_extract":
            return "data_extraction"
        
        # WordPress nodes
        if raw_type.startswith("wordpress_") or raw_type == "wordpress_posts":
            return "api_call"
        
        # Email nodes
        if raw_type.startswith("email_") or raw_type == "email":
            return "email"
        
        # Webhook nodes
        if raw_type.startswith("webhook_"):
            return "api_call"
        
        # Transform/filter nodes
        if raw_type.startswith("transform_") or raw_type == "transform":
            return "transform"
        if raw_type.startswith("filter_"):
            return "api_call"
        
        # Loop/iteration nodes
        if raw_type.startswith("foreach_") or raw_type.startswith("loop_"):
            return "api_call"
        
        # Delay nodes
        if raw_type.startswith("delay_"):
            return "api_call"
        
        # Conditional/gate nodes
        if raw_type.startswith("condition_") or raw_type == "conditional":
            return "conditional"
        if raw_type.startswith("gate_"):
            return "api_call"
        
        # Review/approval nodes
        if raw_type.startswith("review_") or raw_type == "review":
            return "review"
        
        # Options/selection nodes
        if raw_type.startswith("options_") or raw_type == "options":
            return "options"
        
        # API call nodes (integrations) - catch all for dynamic integrations
        if raw_type.startswith("api_") or "integration" in raw_type or "_" in raw_type:
            return "api_call"
        
        # Default to task
        logger.warning(f"Unknown node type '{raw_type}', defaulting to 'task'")
        return "task"
    
    async def _execute_trigger_step(self, execution: models.WorkflowExecution, step: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a trigger step (initiates the workflow)"""
        logger.info("Executing trigger step - workflow initiated")
        
        # Trigger steps just mark the workflow as started
        # They pass through any input data to subsequent steps
        return {
            "success": True,
            "triggered": True,
            "message": "Workflow triggered successfully",
            "triggered_at": datetime.now(timezone.utc).isoformat(),
            "credits_used": 0
        }
    
    async def _execute_integration_step(self, execution: models.WorkflowExecution, step: Dict[str, Any], raw_type: str) -> Dict[str, Any]:
        """
        Execute any integration-based step using IntegrationService
        This uses the same approach as the working test workflow functionality
        """
        try:
            # Extract config from nested structure
            input_data_wrapper = step.get("input", {})
            bindings = input_data_wrapper.get("bindings", step.get("bindings", {}))
            config = bindings.get("config", {})
            
            # Get integration ID from config and determine provider name
            integration_id = config.get("integrationId")
            
            # Determine integration name/provider from integrationId or node type
            if integration_id:
                # Try to look up the integration to get its provider name
                if isinstance(integration_id, str) and integration_id.startswith("integration_"):
                    # Find the integration by matching it to business integrations
                    business_integrations = self.db.query(models.BusinessIntegration).filter(
                        models.BusinessIntegration.business_id == execution.business_id,
                        models.BusinessIntegration.is_active == True
                    ).all()
                    
                    # Try to find matching integration
                    integration_name = None
                    for bi in business_integrations:
                        # Check if this is a DataForSEO, OpenAI, WordPress, etc. integration
                        provider = bi.integration.provider
                        if provider:
                            integration_name = provider
                            break
                    
                    if not integration_name:
                        # Fallback: infer from node type
                        integration_name = self._infer_provider_from_node_type(raw_type)
                else:
                    # Direct provider name
                    integration_name = integration_id
            else:
                # No integrationId, infer from node type
                integration_name = self._infer_provider_from_node_type(raw_type)
            
            logger.info(f"Executing integration step: provider={integration_name}, type={raw_type}")
            
            # Build runtime context for parameter resolution
            runtime_context = {
                "inputs": execution.runtime_state.get("inputs", {}),
                "globals": execution.runtime_state.get("globals", {}),
                "steps": execution.runtime_state.get("steps", {}),
                "runtime": execution.runtime_state.get("runtime", {})
            }
            
            # Prepare node_config (the configuration for this specific node)
            node_config = {}
            for key, value in config.items():
                if key != "integrationId":  # Skip metadata
                    # Resolve any expressions in the config values
                    if isinstance(value, str) and ("{{" in value or value.startswith("expr:")):
                        try:
                            node_config[key] = self.expression_engine.resolve_expression(value, runtime_context)
                        except Exception as e:
                            logger.warning(f"Failed to resolve config parameter '{key}': {e}")
                            node_config[key] = value
                    else:
                        node_config[key] = value
            
            # Prepare input_data (data from previous steps)
            input_data = {
                "node_type": raw_type,
                "step_id": step.get("id"),
                **bindings  # Include all bindings as input data
            }
            
            logger.info(f"Executing operation with config keys: {list(node_config.keys())}")
            
            # Execute using IntegrationService (same as working test workflow)
            result = await self.integration_service.execute_integration(
                integration_name=integration_name,
                business_id=execution.business_id,
                node_config=node_config,
                input_data=input_data,
                user_id=execution.template.created_by if (execution.template and execution.template.created_by) else 1
            )
            
            logger.info(f"Integration execution result: success={result.get('success')}, credits={result.get('credits_used', 0)}")
            
            return result
            
        except Exception as e:
            logger.error(f"Integration step execution failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "operation": raw_type,
                "credits_used": 0
            }
    
    def _infer_provider_from_node_type(self, node_type: str) -> str:
        """Infer integration provider name from node type"""
        if node_type.startswith("seo_"):
            return "dataforseo"
        elif node_type.startswith("ai_openai") or node_type.startswith("openai"):
            return "openai"
        elif node_type.startswith("wordpress_"):
            return "wordpress"
        elif node_type.startswith("content_extract"):
            return "content_extraction"
        elif node_type.startswith("email_"):
            return "email"
        else:
            # Default: use the node type as provider name
            return node_type.split("_")[0] if "_" in node_type else node_type
    
    async def _execute_transform_step(self, execution: models.WorkflowExecution, step: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a transform step"""
        logger.info("Executing transform step")
        
        return {
            "success": True,
            "result": {"message": "Transform executed (mock)"},
            "credits_used": 0
        }
    
    async def _execute_review_step(self, execution: models.WorkflowExecution, step: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a review step (pauses workflow)"""
        logger.info("Executing review step - pausing workflow")
        
        # TODO: Implement review pause logic
        return {
            "success": True,
            "paused": True,
            "message": "Waiting for review",
            "credits_used": 0
        }
    
    async def _execute_options_step(self, execution: models.WorkflowExecution, step: Dict[str, Any]) -> Dict[str, Any]:
        """Execute an options step (pauses for selection)"""
        logger.info("Executing options step - pausing workflow")
        
        # TODO: Implement options pause logic
        return {
            "success": True,
            "paused": True,
            "message": "Waiting for option selection",
            "credits_used": 0
        }
    
    async def _execute_conditional_step(self, execution: models.WorkflowExecution, step: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a conditional step"""
        logger.info("Executing conditional step")
        
        return {
            "success": True,
            "result": {"message": "Conditional evaluated (mock)"},
            "credits_used": 0
        }
    
    def _complete_execution(self, execution: models.WorkflowExecution, message: str):
        """Mark execution as completed"""
        execution.status = "completed"
        execution.flow_status = "complete"
        execution.completed_at = datetime.now(timezone.utc)
        execution.current_step = None
        
        logger.info(f"Workflow execution {execution.id} completed: {message}")
        self.db.commit()
    
    def _fail_execution(self, execution: models.WorkflowExecution, error_message: str):
        """Mark execution as failed"""
        execution.status = "failed"
        execution.flow_status = "error"
        execution.error_message = error_message
        execution.completed_at = datetime.now(timezone.utc)
        
        logger.error(f"Workflow execution {execution.id} failed: {error_message}")
        self.db.commit()

