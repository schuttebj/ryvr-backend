"""
Workflow Executor Service  
Handles complete workflow execution from start to finish with progress tracking
Uses the proven execution logic from the test workflow functionality
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
                    
                    # Store step result in runtime state WITH FULL OUTPUT DATA
                    # This matches the test workflow pattern for variable bindings
                    if not execution.runtime_state.get("steps"):
                        execution.runtime_state["steps"] = {}
                    
                    execution.runtime_state["steps"][step_id] = {
                        "output": result,  # Store full result as "output" for variable binding
                        "result": result,   # Also store as "result" for backward compatibility
                        "data": result.get("data", {}),  # Extract data field
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
                    
                    # Mark the execution.runtime_state as modified for SQLAlchemy
                    from sqlalchemy.orm.attributes import flag_modified
                    flag_modified(execution, "runtime_state")
                    
                    self.db.commit()
                    
                    logger.info(f"Step {step_name} completed successfully - stored in runtime_state")
                    
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
        Execute integration step using the EXACT same logic as the working test workflow
        This replicates _execute_api_step from workflows.py router
        """
        try:
            # Special handling for content_extract - it's a backend service, not an integration
            if raw_type == "content_extract" or raw_type.startswith("content_extract"):
                logger.info(f"Content extraction detected - using backend service instead of integration")
                return await self._execute_content_extraction(execution, step, raw_type)
            
            # Build runtime context for expression resolution
            context = {
                "inputs": execution.runtime_state.get("inputs", {}),
                "globals": execution.runtime_state.get("globals", {}),
                "steps": execution.runtime_state.get("steps", {}),
                "runtime": execution.runtime_state.get("runtime", {})
            }
            
            # Extract step configuration using the EXACT same structure as test workflow
            step_input = step.get("input", {})
            input_bindings = step_input.get("bindings", {})
            static_data = step_input.get("static", {})
            
            # Get connection_id and operation from step (test workflow pattern)
            # For our workflow format, we need to extract from bindings
            integration_id = input_bindings.get("config", {}).get("integrationId")
            operation = input_bindings.get("type", raw_type)
            
            # Convert integrationId to provider name
            # ALWAYS infer provider from node type - this uses system integrations which work
            # The integrationId is mainly for UI reference, the actual execution uses system credentials
            connection_id = self._infer_provider_from_node_type(raw_type)
            
            logger.info(f"Executing API step: connection_id={connection_id} (inferred from {raw_type}), operation={operation}, integrationId={integration_id}")
            
            # Build input_data from bindings and static data (test workflow pattern)
            input_data = {}
            
            # Add static data first
            if static_data:
                input_data.update(static_data)
            
            # Resolve input bindings using expression engine (test workflow pattern)
            if input_bindings:
                config = input_bindings.get("config", {})
                logger.info(f"🔍 Original config from bindings: {config}")
                logger.info(f"🔑 Config keys: {list(config.keys())}")
                
                for key, expr in config.items():
                    if key == "integrationId":  # Skip metadata
                        continue
                    try:
                        if isinstance(expr, str) and expr.startswith("expr:"):
                            # Evaluate JMESPath expression against context
                            value = self.expression_engine.evaluate(expr[5:].strip(), context)
                            logger.info(f"✅ Resolved JMESPath {key}: {expr} → {value}")
                        elif isinstance(expr, str) and ("{{" in expr and "}}" in expr):
                            # Resolve template expression
                            logger.info(f"🔧 Resolving template for {key}: {expr[:100]}...")
                            value = self.expression_engine.resolve_expression(expr, context)
                            logger.info(f"✅ Resolved {key} to: {str(value)[:100]}...")
                        else:
                            # Use literal value
                            value = expr
                            logger.info(f"📌 Using literal value for {key}: {value}")
                        input_data[key] = value
                    except Exception as e:
                        logger.warning(f"⚠️ Failed to resolve input binding {key}: {e}")
                        input_data[key] = expr
            
            logger.info(f"📦 Raw input_data before mapping: {input_data}")
            
            # Map workflow builder parameters to integration handler parameters
            # This handles differences like userPrompt -> prompt, systemPrompt -> system_prompt
            mapped_config = self._map_parameters_to_handler(input_data, connection_id)
            
            logger.info(f"Mapped config keys: {list(mapped_config.keys())}")
            if connection_id == "openai":
                logger.info(f"OpenAI prompt preview: {mapped_config.get('prompt', '')[:100]}...")
                logger.info(f"OpenAI system_prompt preview: {mapped_config.get('system_prompt', '')[:100]}...")
            
            # Execute the integration using IntegrationService (test workflow pattern)
            # IMPORTANT: input_data should contain the resolved parameters, NOT the full context
            # The handlers expect the actual parameter values in input_data
            result = await self.integration_service.execute_integration(
                integration_name=connection_id,
                business_id=execution.business_id,
                node_config=mapped_config,  # Configuration like model, temperature, etc.
                input_data=mapped_config,   # Also pass as input_data - handlers look here for params
                user_id=execution.template.created_by if (execution.template and execution.template.created_by) else 1,
                execution_id=execution.id  # Pass execution ID for API call logging
            )
            
            logger.info(f"Integration result: success={result.get('success')}, credits={result.get('credits_used', 0)}")
            
            # Return in the same format as test workflow
            if result.get("success"):
                return {
                    "status": "completed",
                    "success": True,
                    "provider": result.get("provider"),
                    "data": result.get("data"),
                    "credits_used": result.get("credits_used", 0),
                    "operation": operation
                }
            else:
                raise Exception(result.get("error", "Integration execution failed"))
            
        except Exception as e:
            logger.error(f"API step execution failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "operation": raw_type,
                "credits_used": 0
            }
    
    def _infer_provider_from_node_type(self, node_type: str) -> str:
        """
        Infer integration provider name from node type
        Maps to actual integration handlers available in IntegrationService
        """
        if node_type.startswith("seo_"):
            return "dataforseo"
        elif node_type.startswith("ai_openai") or node_type.startswith("openai") or node_type.startswith("ai_"):
            return "openai"
        elif node_type.startswith("wordpress_"):
            return "wordpress"
        elif node_type.startswith("content_extract"):
            return "content_extraction"  # Handled separately in _execute_content_extraction
        elif node_type.startswith("email_"):
            return "email"
        elif node_type.startswith("google_ads"):
            return "google_ads"
        elif node_type.startswith("google_analytics") or node_type.startswith("ga_"):
            return "google_analytics"
        elif node_type.startswith("meta_ads") or node_type.startswith("facebook_"):
            return "meta_ads"
        else:
            # Default: use the first part of the node type as provider name
            provider = node_type.split("_")[0] if "_" in node_type else node_type
            logger.warning(f"Unknown node type '{node_type}', inferred provider: '{provider}'")
            return provider
    
    def _map_parameters_to_handler(self, config: Dict[str, Any], provider: str) -> Dict[str, Any]:
        """Map workflow builder parameters to integration handler parameters"""
        mapped = config.copy()
        
        logger.info(f"🗺️ Mapping parameters for provider: {provider}")
        logger.info(f"   Input config: {config}")
        
        if provider == "openai":
            # Map workflow builder parameters to OpenAI handler parameters
            if "userPrompt" in mapped:
                mapped["prompt"] = mapped.pop("userPrompt")
            if "systemPrompt" in mapped:
                mapped["system_prompt"] = mapped.pop("systemPrompt")
            if "modelOverride" in mapped:
                mapped["model"] = mapped.pop("modelOverride")
            if "maxTokens" in mapped:
                mapped["max_tokens"] = mapped.pop("maxTokens")
            if "maxCompletionTokens" in mapped:
                mapped["max_completion_tokens"] = mapped.pop("maxCompletionTokens")
            # jsonResponse and jsonSchema are now supported - keep them as-is
        elif provider == "dataforseo":
            # DataForSEO parameter mapping - most params should pass through as-is
            # The service expects: keyword, location_code, language_code, device, depth
            # Just log to verify we have the keyword
            logger.info(f"   DataForSEO keyword: {mapped.get('keyword', 'NOT FOUND')}")
        elif provider == "wordpress":
            # WordPress parameter mapping
            if "operation" in mapped:
                # Keep operation as-is
                pass
        
        logger.info(f"   Mapped config: {mapped}")
        return mapped
    
    async def _execute_content_extraction(self, execution: models.WorkflowExecution, step: Dict[str, Any], raw_type: str) -> Dict[str, Any]:
        """Execute content extraction using backend service (not an integration)"""
        try:
            logger.info("🔍 Executing content extraction - backend service")
            
            # Build runtime context for variable resolution
            context = {
                "inputs": execution.runtime_state.get("inputs", {}),
                "globals": execution.runtime_state.get("globals", {}),
                "steps": execution.runtime_state.get("steps", {}),
                "runtime": execution.runtime_state.get("runtime", {})
            }
            
            # Extract URL source from config
            step_input = step.get("input", {})
            bindings = step_input.get("bindings", {})
            config = bindings.get("config", {})
            
            url_source = config.get("urlSource", "")
            max_urls = config.get("maxUrls", 10)
            max_length = config.get("maxLength", 8000)
            
            logger.info(f"📋 Config: urlSource={url_source}, maxUrls={max_urls}")
            
            # Extract URLs from the URL source (which may contain variable references)
            urls = []
            
            if url_source:
                logger.info(f"🔧 Processing urlSource: {url_source}")
                
                # Resolve variables in the URL source using {{variable}} syntax
                processed_url_source = self.expression_engine.resolve_expression(url_source, context)
                logger.info(f"✅ Processed urlSource result: {processed_url_source}")
                
                # Parse the processed result to extract URLs
                if processed_url_source:
                    # Check if result contains actual URLs
                    if 'http' in str(processed_url_source):
                        # Extract URLs using regex
                        import re
                        # First, try to extract URLs directly (handles any format)
                        url_matches = re.findall(r'https?://[^\s+,\n\r\t]+', str(processed_url_source))
                        if url_matches:
                            urls = url_matches
                        else:
                            # Try splitting by common delimiters
                            urls = [
                                url.strip() 
                                for url in re.split(r'\s*[,+\n\r\t]\s*|\s+\+\s+', str(processed_url_source))
                                if url.strip() and 'http' in url
                            ]
                    elif isinstance(processed_url_source, list):
                        # Already a list of URLs
                        urls = [url for url in processed_url_source if url and isinstance(url, str) and 'http' in url]
            
            # Validate we have URLs
            if not urls:
                logger.error("❌ No URLs found to extract content from")
                logger.error(f"Config: urlSource={url_source}")
                logger.error(f"Available context keys: {list(context.get('steps', {}).keys())}")
                raise ValueError("No URLs found to extract content from. Check your URL source configuration.")
            
            # Apply maxUrls limit
            urls = urls[:max_urls]
            
            logger.info(f"✅ Extracted {len(urls)} URLs for content extraction")
            
            # Mock content extraction (TODO: Implement real web scraping)
            extracted_content = []
            for i, url in enumerate(urls):
                extracted_content.append({
                    'url': url,
                    'title': f'Extracted Title {i+1}',
                    'content': f'This is mock extracted content from {url}. In production, this would contain the actual scraped content from the webpage.',
                    'word_count': 250,
                    'extraction_type': config.get('extractionType', 'full_text'),
                    'extracted_at': datetime.now(timezone.utc).isoformat()
                })
            
            return {
                "status": "completed",
                "success": True,
                "data": {
                    "processed": {
                        "extracted_content": extracted_content
                    },
                    "raw": {'urls': urls, 'config': config},
                    "summary": {
                        'urls_processed': len(extracted_content),
                        'total_urls_found': len(urls),
                        'total_words': sum(item['word_count'] for item in extracted_content),
                        'extraction_type': config.get('extractionType', 'full_text')
                    }
                },
                "credits_used": len(extracted_content),
                "operation": raw_type
            }
        except Exception as e:
            logger.error(f"❌ Content extraction failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "operation": raw_type,
                "credits_used": 0
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

