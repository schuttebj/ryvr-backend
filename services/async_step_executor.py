"""
Universal Async Step Executor for Workflow V2
Handles submit/poll patterns for any integration that requires asynchronous processing

Supports:
- DataForSEO: SERP analysis with task submission and status polling
- OpenAI: Long-running completions with progress tracking
- WordPress: Bulk operations with completion monitoring
- Any custom API: Two-step submit/check pattern
"""

import asyncio
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Callable
from dataclasses import dataclass
import logging

from .expression_engine import expression_engine
from .data_transformation_service import data_transformation_service

logger = logging.getLogger(__name__)


@dataclass
class AsyncTaskResult:
    """Result of an async task execution"""
    success: bool
    task_id: Optional[str]
    result_data: Optional[Any]
    error_message: Optional[str]
    execution_time_ms: int
    polling_attempts: int
    submit_response: Optional[Dict[str, Any]] = None
    check_responses: Optional[List[Dict[str, Any]]] = None


class AsyncStepExecutor:
    """
    Universal async step executor for any integration
    
    Handles the common pattern of:
    1. Submit a task to an API
    2. Poll for completion status
    3. Retrieve final results
    
    Configurable for different providers and their specific async patterns
    """
    
    def __init__(self, integration_service):
        self.integration_service = integration_service
        self.active_tasks = {}  # Track running async tasks
    
    async def execute_async_step(self, step: Dict[str, Any], runtime_state: Dict[str, Any], 
                                business_id: int) -> AsyncTaskResult:
        """
        Execute an async step with universal submit/poll pattern
        
        Args:
            step: Step configuration with async_config
            runtime_state: Current workflow runtime state
            business_id: Business context for integration access
            
        Returns:
            AsyncTaskResult with execution details
            
        Example step configuration:
        {
            "id": "async_api_task",
            "type": "async_task",
            "connection_id": "conn-provider",
            "operation": "long_running_operation",
            "async_config": {
                "submit_operation": "submit_task",
                "check_operation": "check_status",
                "polling_interval_seconds": 5,
                "max_wait_seconds": 300,
                "completion_check": "expr: @.status == 'completed'",
                "result_path": "expr: @.result",
                "task_id_path": "expr: @.task_id",
                "error_check": "expr: @.status == 'failed'",
                "progress_path": "expr: @.progress"
            }
        }
        """
        start_time = time.time()
        async_config = step.get("async_config", {})
        
        if not async_config:
            raise AsyncExecutionError("Step marked as async_task but missing async_config")
        
        try:
            # Step 1: Submit the async task
            logger.info(f"Submitting async task for step {step['id']}")
            submit_result = await self._submit_async_task(step, runtime_state, business_id)
            
            # Extract task ID from submit response
            task_id = self._extract_task_id(submit_result, async_config)
            if not task_id:
                raise AsyncExecutionError("Failed to extract task ID from submit response")
            
            logger.info(f"Async task submitted with ID: {task_id}")
            
            # Step 2: Poll for completion
            poll_result = await self._poll_for_completion(
                step, task_id, runtime_state, business_id, async_config, submit_result
            )
            
            execution_time = int((time.time() - start_time) * 1000)
            
            return AsyncTaskResult(
                success=True,
                task_id=task_id,
                result_data=poll_result["final_result"],
                error_message=None,
                execution_time_ms=execution_time,
                polling_attempts=poll_result["attempts"],
                submit_response=submit_result,
                check_responses=poll_result["check_responses"]
            )
            
        except Exception as e:
            execution_time = int((time.time() - start_time) * 1000)
            logger.error(f"Async step execution failed: {e}")
            
            return AsyncTaskResult(
                success=False,
                task_id=None,
                result_data=None,
                error_message=str(e),
                execution_time_ms=execution_time,
                polling_attempts=0
            )
    
    async def _submit_async_task(self, step: Dict[str, Any], runtime_state: Dict[str, Any], 
                                business_id: int) -> Dict[str, Any]:
        """
        Submit the initial async task
        
        Args:
            step: Step configuration
            runtime_state: Current workflow state
            business_id: Business context
            
        Returns:
            Submit operation response
        """
        async_config = step["async_config"]
        submit_operation = async_config["submit_operation"]
        
        # Resolve input bindings for the submit operation
        input_data = self._resolve_step_inputs(step, runtime_state)
        
        # Execute the submit operation through integration service
        logger.debug(f"Submitting task with operation: {submit_operation}")
        logger.debug(f"Input data: {input_data}")
        
        result = await self.integration_service.execute_integration(
            integration_name=step["connection_id"],
            business_id=business_id,
            operation=submit_operation,
            input_data=input_data
        )
        
        logger.debug(f"Submit result: {result}")
        return result
    
    async def _poll_for_completion(self, step: Dict[str, Any], task_id: str, 
                                  runtime_state: Dict[str, Any], business_id: int,
                                  async_config: Dict[str, Any], submit_response: Dict[str, Any]) -> Dict[str, Any]:
        """
        Poll for task completion with configurable intervals and timeouts
        
        Args:
            step: Step configuration
            task_id: Task ID to monitor
            runtime_state: Current workflow state
            business_id: Business context
            async_config: Async configuration
            submit_response: Original submit response
            
        Returns:
            Polling result with final data and metadata
        """
        check_operation = async_config["check_operation"]
        polling_interval = async_config.get("polling_interval_seconds", 5)
        max_wait = async_config.get("max_wait_seconds", 300)
        completion_check = async_config["completion_check"]
        result_path = async_config.get("result_path", "expr: @")
        error_check = async_config.get("error_check")
        progress_path = async_config.get("progress_path")
        
        start_time = datetime.now()
        max_end_time = start_time + timedelta(seconds=max_wait)
        attempts = 0
        check_responses = []
        
        logger.info(f"Starting polling for task {task_id} (max wait: {max_wait}s)")
        
        while datetime.now() < max_end_time:
            attempts += 1
            
            try:
                # Check task status
                check_input = {"task_id": task_id}
                check_result = await self.integration_service.execute_integration(
                    integration_name=step["connection_id"],
                    business_id=business_id,
                    operation=check_operation,
                    input_data=check_input
                )
                
                check_responses.append({
                    "attempt": attempts,
                    "timestamp": datetime.now().isoformat(),
                    "response": check_result
                })
                
                logger.debug(f"Poll attempt {attempts}: {check_result}")
                
                # Check for errors first
                if error_check:
                    is_error = self._evaluate_condition(check_result, error_check)
                    if is_error:
                        error_msg = self._extract_error_message(check_result, async_config)
                        raise AsyncExecutionError(f"Task failed: {error_msg}")
                
                # Check for completion
                is_complete = self._evaluate_condition(check_result, completion_check)
                
                if is_complete:
                    logger.info(f"Task {task_id} completed after {attempts} attempts")
                    
                    # Extract final result
                    final_result = self._extract_result(check_result, result_path)
                    
                    return {
                        "final_result": final_result,
                        "attempts": attempts,
                        "check_responses": check_responses,
                        "completion_time": datetime.now().isoformat()
                    }
                
                # Log progress if available
                if progress_path:
                    progress = self._extract_progress(check_result, progress_path)
                    if progress:
                        logger.info(f"Task {task_id} progress: {progress}")
                
                # Wait before next poll
                await asyncio.sleep(polling_interval)
                
            except AsyncExecutionError:
                # Re-raise async execution errors (task failures)
                raise
            except Exception as e:
                logger.warning(f"Poll attempt {attempts} failed: {e}")
                # Continue polling unless it's a critical error
                await asyncio.sleep(polling_interval)
        
        # Timeout reached
        raise AsyncTimeoutError(
            f"Task {task_id} timed out after {max_wait} seconds ({attempts} attempts)"
        )
    
    def _extract_task_id(self, submit_response: Dict[str, Any], async_config: Dict[str, Any]) -> Optional[str]:
        """Extract task ID from submit response using configured path"""
        task_id_path = async_config.get("task_id_path", "expr: @.task_id")
        
        try:
            task_id = expression_engine.evaluate(task_id_path, submit_response)
            return str(task_id) if task_id is not None else None
        except Exception as e:
            logger.error(f"Failed to extract task ID: {e}")
            return None
    
    def _evaluate_condition(self, data: Dict[str, Any], condition: str) -> bool:
        """Evaluate completion/error condition using expression engine"""
        try:
            result = expression_engine.evaluate(condition, data)
            return bool(result)
        except Exception as e:
            logger.warning(f"Condition evaluation failed: {e}")
            return False
    
    def _extract_result(self, data: Dict[str, Any], result_path: str) -> Any:
        """Extract final result using configured path"""
        try:
            return expression_engine.evaluate(result_path, data)
        except Exception as e:
            logger.warning(f"Result extraction failed: {e}")
            return data
    
    def _extract_progress(self, data: Dict[str, Any], progress_path: str) -> Optional[Any]:
        """Extract progress information if available"""
        try:
            return expression_engine.evaluate(progress_path, data)
        except Exception:
            return None
    
    def _extract_error_message(self, data: Dict[str, Any], async_config: Dict[str, Any]) -> str:
        """Extract error message from failed response"""
        error_path = async_config.get("error_message_path", "expr: @.error || @.message || 'Unknown error'")
        try:
            return str(expression_engine.evaluate(error_path, data))
        except Exception:
            return "Unknown error occurred"
    
    def _resolve_step_inputs(self, step: Dict[str, Any], runtime_state: Dict[str, Any]) -> Dict[str, Any]:
        """Resolve step input bindings using expression engine"""
        input_config = step.get("input", {})
        bindings = input_config.get("bindings", {})
        static_data = input_config.get("static", {})
        
        # Resolve bindings using expression engine
        resolved_bindings = expression_engine.resolve_bindings(bindings, runtime_state)
        
        # Merge with static data
        return {**static_data, **resolved_bindings}
    
    async def cancel_task(self, task_id: str, integration_name: str, business_id: int) -> bool:
        """
        Cancel a running async task if the integration supports it
        
        Args:
            task_id: Task to cancel
            integration_name: Integration connection ID
            business_id: Business context
            
        Returns:
            True if cancellation was successful
        """
        try:
            # Try to call cancel operation if available
            await self.integration_service.execute_integration(
                integration_name=integration_name,
                business_id=business_id,
                operation="cancel_task",
                input_data={"task_id": task_id}
            )
            
            # Remove from active tasks
            self.active_tasks.pop(task_id, None)
            
            logger.info(f"Successfully cancelled task {task_id}")
            return True
            
        except Exception as e:
            logger.warning(f"Failed to cancel task {task_id}: {e}")
            return False
    
    def get_active_tasks(self) -> Dict[str, Dict[str, Any]]:
        """Get list of currently active async tasks"""
        return self.active_tasks.copy()


class AsyncPresetConfigs:
    """
    Predefined async configurations for common integrations
    Makes it easier to configure standard async patterns
    """
    
    @staticmethod
    def dataforseo_serp() -> Dict[str, Any]:
        """Standard DataForSEO SERP analysis async config"""
        return {
            "submit_operation": "post_serp_task",
            "check_operation": "get_serp_results",
            "polling_interval_seconds": 5,
            "max_wait_seconds": 300,
            "completion_check": "expr: @.tasks[0].status_code == 20000",
            "result_path": "expr: @.tasks[0].result",
            "task_id_path": "expr: @.tasks[0].id",
            "error_check": "expr: @.tasks[0].status_code != 20000 && @.tasks[0].status_code != 20100",
            "error_message_path": "expr: @.tasks[0].status_message"
        }
    
    @staticmethod
    def openai_long_completion() -> Dict[str, Any]:
        """OpenAI long-running completion async config"""
        return {
            "submit_operation": "create_batch_completion",
            "check_operation": "get_batch_status",
            "polling_interval_seconds": 10,
            "max_wait_seconds": 600,
            "completion_check": "expr: @.status == 'completed'",
            "result_path": "expr: @.output",
            "task_id_path": "expr: @.id",
            "error_check": "expr: @.status == 'failed'",
            "progress_path": "expr: @.progress"
        }
    
    @staticmethod
    def wordpress_bulk_operation() -> Dict[str, Any]:
        """WordPress bulk operation async config"""
        return {
            "submit_operation": "sync_content",
            "check_operation": "get_sync_logs",
            "polling_interval_seconds": 5,
            "max_wait_seconds": 300,
            "completion_check": "expr: @.stats.total > 0 && (@.stats.successful + @.stats.failed) == @.stats.total",
            "result_path": "expr: @.results",
            "task_id_path": "expr: 'wordpress_sync_' + to_string(@.stats.total)",
            "error_check": "expr: @.stats.failed > @.stats.successful",
            "progress_path": "expr: @.stats"
        }
    
    @staticmethod
    def custom_api(submit_op: str, check_op: str, completion_expr: str, 
                   result_expr: str = "expr: @.result", task_id_expr: str = "expr: @.id") -> Dict[str, Any]:
        """Create custom async config for any API"""
        return {
            "submit_operation": submit_op,
            "check_operation": check_op,
            "polling_interval_seconds": 5,
            "max_wait_seconds": 300,
            "completion_check": completion_expr,
            "result_path": result_expr,
            "task_id_path": task_id_expr
        }


class AsyncExecutionError(Exception):
    """Raised when async task execution fails"""
    pass


class AsyncTimeoutError(AsyncExecutionError):
    """Raised when async task times out"""
    pass


# Example usage
async def example_async_step():
    """Example of how to use the async step executor"""
    
    # Example step configuration for DataForSEO
    step = {
        "id": "serp_analysis",
        "type": "async_task",
        "connection_id": "conn-dataforseo",
        "operation": "serp_google_organic",
        "async_config": AsyncPresetConfigs.dataforseo_serp(),
        "input": {
            "bindings": {
                "keyword": "expr: $.inputs.target_keyword",
                "location_code": "expr: $.inputs.location || 2840",
                "language_code": "expr: $.inputs.language || 'en'"
            }
        }
    }
    
    runtime_state = {
        "inputs": {
            "target_keyword": "best pizza recipe",
            "location": 2840,
            "language": "en"
        }
    }
    
    # Mock integration service would be injected
    # executor = AsyncStepExecutor(integration_service)
    # result = await executor.execute_async_step(step, runtime_state, business_id=123)
    
    print("Example async step configuration:")
    print(f"Step: {step}")
    print(f"Runtime state: {runtime_state}")


if __name__ == "__main__":
    asyncio.run(example_async_step())
