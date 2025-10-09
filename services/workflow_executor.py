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
        Execute a single workflow step
        
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
        # Priority: step["type"] > step["input"]["bindings"]["type"]
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
            
            # Route to appropriate handler based on step type
            if step_type == "trigger":
                result = await self._execute_trigger_step(execution, step)
            elif step_type == "api_call":
                result = await self._execute_api_call_step(execution, step)
            elif step_type == "task":
                result = await self._execute_task_step(execution, step)
            elif step_type == "ai":
                result = await self._execute_ai_step(execution, step)
            elif step_type == "transform":
                result = await self._execute_transform_step(execution, step)
            elif step_type == "review":
                result = await self._execute_review_step(execution, step)
            elif step_type == "options":
                result = await self._execute_options_step(execution, step)
            elif step_type == "conditional":
                result = await self._execute_conditional_step(execution, step)
            elif step_type == "email":
                result = await self._execute_email_step(execution, step)
            elif step_type == "seo":
                result = await self._execute_seo_step(execution, step)
            elif step_type == "data_extraction":
                result = await self._execute_data_extraction_step(execution, step)
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
    
    async def _execute_api_call_step(self, execution: models.WorkflowExecution, step: Dict[str, Any]) -> Dict[str, Any]:
        """Execute an API call step (integration call)"""
        connection_id = step.get("connection_id")
        operation = step.get("operation")
        
        logger.info(f"Executing API call: {connection_id}.{operation}")
        
        # Check if this is a dynamic integration
        # connection_id format: "integration_name" or "integration_name.operation_id"
        try:
            # Get integration by provider/name
            parts = connection_id.split(".")
            integration_name = parts[0] if parts else connection_id
            operation_id = operation or (parts[1] if len(parts) > 1 else None)
            
            integration = self.db.query(models.Integration).filter(
                models.Integration.provider == integration_name,
                models.Integration.is_active == True
            ).first()
            
            if not integration:
                # Try by name
                integration = self.db.query(models.Integration).filter(
                    models.Integration.name == integration_name,
                    models.Integration.is_active == True
                ).first()
            
            if integration and integration.is_dynamic and operation_id:
                # Use dynamic integration service
                from services.dynamic_integration_service import DynamicIntegrationService
                
                dynamic_service = DynamicIntegrationService(self.db)
                
                # Extract parameters from step configuration
                parameters = step.get("config", {})
                
                # Execute the operation
                result = await dynamic_service.execute_operation(
                    integration_id=integration.id,
                    operation_id=operation_id,
                    business_id=execution.business_id,
                    parameters=parameters,
                    user_id=execution.template.user_id if execution.template else 1
                )
                
                return result
            else:
                # Fall back to legacy integration service
                result = await self.integration_service.execute_integration(
                    integration_name=connection_id,
                    business_id=execution.business_id,
                    node_config=step.get("config", {}),
                    input_data=step.get("input", {}),
                    user_id=execution.template.user_id if execution.template else 1
                )
                
                return result
                
        except Exception as e:
            logger.error(f"API call execution failed: {e}", exc_info=True)
            return {
                "success": False,
                "connection_id": connection_id,
                "operation": operation,
                "error": str(e),
                "credits_used": 0
            }
    
    async def _execute_task_step(self, execution: models.WorkflowExecution, step: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a task step"""
        operation = step.get("operation")
        logger.info(f"Executing task: {operation}")
        
        return {
            "success": True,
            "operation": operation,
            "result": {"message": "Task executed (mock)"},
            "credits_used": 1
        }
    
    async def _execute_ai_step(self, execution: models.WorkflowExecution, step: Dict[str, Any]) -> Dict[str, Any]:
        """Execute an AI step"""
        # Extract config from nested structure
        input_data = step.get("input", {})
        bindings = input_data.get("bindings", step.get("bindings", {}))
        config = bindings.get("config", {})
        operation = bindings.get("type", "ai_task")
        
        logger.info(f"Executing AI step: {operation}")
        
        # Extract AI configuration
        system_prompt = config.get("systemPrompt", "")
        user_prompt = config.get("userPrompt", "")
        model = config.get("modelOverride", "gpt-4")
        json_response = config.get("jsonResponse", False)
        
        # TODO: Integrate with actual AI service (OpenAI, Claude, etc.)
        # For now, return mock data that matches expected JSON schemas
        
        if json_response:
            # Return mock JSON response based on common schemas
            if "topic" in str(config.get("jsonSchema", "")).lower():
                mock_result = {
                    "topic": "Sample Topic Generated from Mock Data",
                    "keywords": ["keyword1", "keyword2", "keyword3", "keyword4"]
                }
            elif "sections" in str(config.get("jsonSchema", "")).lower():
                mock_result = {
                    "title": "Mock Article Title",
                    "sections": [
                        {"heading": "Introduction", "content": "Mock introduction content goes here."},
                        {"heading": "Main Content", "content": "Mock main content section."},
                        {"heading": "Analysis", "content": "Mock analysis section."},
                        {"heading": "Recommendations", "content": "Mock recommendations section."},
                        {"heading": "Conclusion", "content": "Mock conclusion content."}
                    ],
                    "totalWordCount": 2000
                }
            else:
                mock_result = {"result": "Mock AI response"}
        else:
            mock_result = "This is a mock AI-generated text response."
        
        return {
            "success": True,
            "operation": operation,
            "model": model,
            "result": {
                "message": "AI task completed (mock)",
                "raw": {
                    "result": mock_result
                },
                "data": {
                    "processed": {
                        "raw": {
                            "result": mock_result
                        }
                    }
                }
            },
            "credits_used": 10
        }
    
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
    
    async def _execute_email_step(self, execution: models.WorkflowExecution, step: Dict[str, Any]) -> Dict[str, Any]:
        """Execute an email step"""
        logger.info("Executing email step")
        
        # TODO: Integrate with actual email service
        return {
            "success": True,
            "result": {"message": "Email sent (mock)"},
            "credits_used": 1
        }
    
    async def _execute_seo_step(self, execution: models.WorkflowExecution, step: Dict[str, Any]) -> Dict[str, Any]:
        """Execute an SEO analysis step"""
        # Extract config from nested structure
        input_data = step.get("input", {})
        bindings = input_data.get("bindings", step.get("bindings", {}))
        config = bindings.get("config", {})
        operation = bindings.get("type", "seo_analysis")
        
        logger.info(f"Executing SEO step: {operation}")
        
        # TODO: Integrate with DataForSEO or other SEO service
        # Extract parameters from config
        keyword = config.get("keyword", "")
        integration_id = config.get("integrationId", "")
        
        return {
            "success": True,
            "operation": operation,
            "keyword": keyword,
            "result": {
                "message": "SEO analysis completed (mock)",
                "keyword": keyword,
                "integration": integration_id,
                "data": {
                    "processed": {
                        "results": [{
                            "keyword": keyword,
                            "position": 1,
                            "url": "https://example.com"
                        }]
                    }
                }
            },
            "credits_used": 5
        }
    
    async def _execute_data_extraction_step(self, execution: models.WorkflowExecution, step: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a data extraction/content extraction step"""
        # Extract config from nested structure
        input_data = step.get("input", {})
        bindings = input_data.get("bindings", step.get("bindings", {}))
        config = bindings.get("config", {})
        
        logger.info("Executing data extraction step")
        
        # TODO: Integrate with actual content extraction service
        return {
            "success": True,
            "result": {
                "message": "Content extracted (mock)",
                "data": {
                    "processed": {
                        "extracted_content": [
                            {"content": "Sample extracted content 1"},
                            {"content": "Sample extracted content 2"},
                            {"content": "Sample extracted content 3"},
                            {"content": "Sample extracted content 4"},
                            {"content": "Sample extracted content 5"}
                        ]
                    }
                }
            },
            "credits_used": 2
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

