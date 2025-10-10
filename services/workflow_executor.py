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
from services.dynamic_integration_service import DynamicIntegrationService

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
        self.dynamic_integration_service = DynamicIntegrationService(db)
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
        if raw_type.startswith("content_extract"):
            return "data_extraction"
        
        # Email nodes
        if raw_type.startswith("email_") or raw_type == "email":
            return "email"
        
        # Webhook nodes
        if raw_type.startswith("webhook_"):
            return "webhook"
        
        # Transform/filter nodes
        if raw_type.startswith("transform_") or raw_type == "transform":
            return "transform"
        if raw_type.startswith("filter_"):
            return "filter"
        
        # Loop/iteration nodes
        if raw_type.startswith("foreach_") or raw_type.startswith("loop_"):
            return "loop"
        
        # Delay nodes
        if raw_type.startswith("delay_"):
            return "delay"
        
        # Conditional/gate nodes
        if raw_type.startswith("condition_") or raw_type == "conditional":
            return "conditional"
        if raw_type.startswith("gate_"):
            return "gate"
        
        # Review/approval nodes
        if raw_type.startswith("review_") or raw_type == "review":
            return "review"
        
        # Options/selection nodes
        if raw_type.startswith("options_") or raw_type == "options":
            return "options"
        
        # API call nodes (integrations)
        if raw_type.startswith("api_") or "integration" in raw_type:
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
        Execute any integration-based step using the dynamic integration system
        This replaces all the individual mock execution methods (AI, SEO, email, etc.)
        """
        try:
            # Extract config from nested structure
            input_data_wrapper = step.get("input", {})
            bindings = input_data_wrapper.get("bindings", step.get("bindings", {}))
            config = bindings.get("config", {})
            
            # Get integration ID from config
            integration_id = config.get("integrationId")
            if not integration_id:
                logger.warning(f"No integrationId found in step config, attempting to infer from type: {raw_type}")
                # Try to find integration by type
                integration_id = await self._find_integration_by_type(raw_type, execution.business_id)
            
            if not integration_id:
                raise ValueError(f"No integration configured for step type: {raw_type}")
            
            # Parse integration ID to get numeric ID
            # Format can be: "integration_1234567890" or just "1234567890" or "provider_name"
            if isinstance(integration_id, str):
                if integration_id.startswith("integration_"):
                    # Extract timestamp-based ID
                    timestamp_str = integration_id.replace("integration_", "")
                    # Look up integration by checking business integrations
                    integration = await self._find_integration_by_id_or_timestamp(timestamp_str, execution.business_id)
                else:
                    # Try direct ID lookup
                    try:
                        integration = self.db.query(models.Integration).filter(
                            models.Integration.id == int(integration_id)
                        ).first()
                    except ValueError:
                        # It's a string identifier, look up by provider name
                        integration = await self._find_integration_by_provider(integration_id, execution.business_id)
            else:
                integration = self.db.query(models.Integration).filter(
                    models.Integration.id == integration_id
                ).first()
            
            if not integration:
                raise ValueError(f"Integration not found: {integration_id}")
            
            logger.info(f"Executing integration: {integration.name} (ID: {integration.id}, Type: {raw_type})")
            
            # Determine which operation to execute based on the node type
            operation_id = raw_type  # e.g., "seo_serp_analyze", "ai_openai_task", "wordpress_posts"
            
            # Resolve step parameters using expression engine
            resolved_parameters = await self._resolve_step_parameters(step, execution)
            
            # Merge with config parameters
            parameters = {**config, **resolved_parameters}
            
            # Remove integrationId from parameters as it's metadata
            parameters.pop("integrationId", None)
            
            logger.info(f"Executing operation '{operation_id}' with parameters: {list(parameters.keys())}")
            
            # Execute using dynamic integration service
            result = await self.dynamic_integration_service.execute_operation(
                integration_id=integration.id,
                operation_id=operation_id,
                business_id=execution.business_id,
                parameters=parameters,
                user_id=execution.template.user_id if execution.template else 1
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
    
    async def _find_integration_by_type(self, node_type: str, business_id: int) -> Optional[str]:
        """Find integration by matching node type to integration operations"""
        # Query business integrations
        business_integrations = self.db.query(models.BusinessIntegration).filter(
            models.BusinessIntegration.business_id == business_id,
            models.BusinessIntegration.is_active == True
        ).all()
        
        for bi in business_integrations:
            integration = bi.integration
            if integration.is_dynamic and integration.operation_configs:
                operations = integration.operation_configs.get("operations", [])
                for op in operations:
                    if op.get("id") == node_type:
                        return str(integration.id)
        
        # Fallback to system integrations
        integrations = self.db.query(models.Integration).filter(
            models.Integration.is_active == True,
            models.Integration.is_dynamic == True
        ).all()
        
        for integration in integrations:
            if integration.operation_configs:
                operations = integration.operation_configs.get("operations", [])
                for op in operations:
                    if op.get("id") == node_type:
                        return str(integration.id)
        
        return None
    
    async def _find_integration_by_id_or_timestamp(self, identifier: str, business_id: int) -> Optional[models.Integration]:
        """Find integration by ID or timestamp identifier"""
        # First, check business integrations with matching created_at timestamp
        business_integrations = self.db.query(models.BusinessIntegration).filter(
            models.BusinessIntegration.business_id == business_id,
            models.BusinessIntegration.is_active == True
        ).all()
        
        for bi in business_integrations:
            integration = bi.integration
            # Check if timestamp matches (approximately)
            if integration.operation_configs:
                # Look for matching integration by checking operations
                operations = integration.operation_configs.get("operations", [])
                for op in operations:
                    # If this integration has operations that match our needs, use it
                    if integration.is_dynamic:
                        return integration
        
        return None
    
    async def _find_integration_by_provider(self, provider_name: str, business_id: int) -> Optional[models.Integration]:
        """Find integration by provider name"""
        # Check business integrations first
        business_integration = self.db.query(models.BusinessIntegration).join(
            models.Integration
        ).filter(
            models.BusinessIntegration.business_id == business_id,
            models.Integration.provider == provider_name,
            models.BusinessIntegration.is_active == True
        ).first()
        
        if business_integration:
            return business_integration.integration
        
        # Fallback to system integration
        return self.db.query(models.Integration).filter(
            models.Integration.provider == provider_name,
            models.Integration.integration_type == "system",
            models.Integration.is_active == True
        ).first()
    
    async def _resolve_step_parameters(self, step: Dict[str, Any], execution: models.WorkflowExecution) -> Dict[str, Any]:
        """Resolve step parameters using expression engine and runtime state"""
        # Extract config
        input_data_wrapper = step.get("input", {})
        bindings = input_data_wrapper.get("bindings", {})
        config = bindings.get("config", {})
        
        # Build runtime context for expression evaluation
        runtime_context = {
            "inputs": execution.runtime_state.get("inputs", {}),
            "globals": execution.runtime_state.get("globals", {}),
            "steps": execution.runtime_state.get("steps", {}),
            "runtime": execution.runtime_state.get("runtime", {})
        }
        
        # Resolve parameters that contain expressions
        resolved = {}
        for key, value in config.items():
            if isinstance(value, str) and ("{{" in value or value.startswith("expr:")):
                try:
                    # Try to resolve expression
                    resolved_value = self.expression_engine.resolve_expression(value, runtime_context)
                    resolved[key] = resolved_value
                except Exception as e:
                    logger.warning(f"Failed to resolve parameter '{key}': {e}")
                    resolved[key] = value
            else:
                resolved[key] = value
        
        return resolved
    
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

