"""
Dynamic Integration Service
Executes API operations configured via Integration Builder
"""

import httpx
import asyncio
import logging
import json
from typing import Dict, List, Optional, Any
from datetime import datetime
from sqlalchemy.orm import Session
import base64
from urllib.parse import urlencode

import models
from services.credit_service import CreditService

logger = logging.getLogger(__name__)


class DynamicIntegrationService:
    """
    Service for executing dynamically configured API integrations.
    Supports multiple auth types, async operations with polling, and flexible parameter mapping.
    """
    
    def __init__(self, db: Session):
        self.db = db
        self.credit_service = CreditService(db)
    
    async def execute_operation(
        self,
        integration_id: int,
        operation_id: str,
        business_id: int,
        parameters: Dict[str, Any],
        user_id: int,
        temp_credentials: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute a dynamically configured integration operation
        
        Args:
            integration_id: ID of the integration
            operation_id: ID of the specific operation to execute
            business_id: Business context for credentials and credit tracking
            parameters: User-provided parameter values
            user_id: User executing the operation
            temp_credentials: Temporary credentials for testing (not stored)
            
        Returns:
            Standardized response with success status, data, and credits used
        """
        try:
            # Load integration configuration
            integration = self.db.query(models.Integration).filter(
                models.Integration.id == integration_id,
                models.Integration.is_active == True,
                models.Integration.is_dynamic == True
            ).first()
            
            if not integration:
                return {
                    "success": False,
                    "error": "Integration not found or not configured as dynamic"
                }
            
            # Get operation configuration
            operations = integration.operation_configs.get("operations", [])
            operation = next((op for op in operations if op["id"] == operation_id), None)
            
            if not operation:
                return {
                    "success": False,
                    "error": f"Operation {operation_id} not found in integration configuration"
                }
            
            # Get credentials
            if temp_credentials:
                credentials = temp_credentials
            else:
                credentials = await self._get_credentials(integration, business_id)
                if not credentials:
                    return {
                        "success": False,
                        "error": "No credentials configured for this integration"
                    }
            
            # Check and deduct credits before execution
            credits_required = operation.get("base_credits", 1)
            credit_check = await self.credit_service.check_and_deduct_credits(
                business_id=business_id,
                credits_required=credits_required,
                operation_type=f"{integration.name} - {operation['name']}",
                metadata={
                    "integration_id": integration_id,
                    "operation_id": operation_id
                }
            )
            
            if not credit_check["success"]:
                return {
                    "success": False,
                    "error": f"Insufficient credits: {credit_check.get('error', 'Unknown error')}"
                }
            
            # Build and execute request
            platform_config = integration.platform_config or {}
            base_url = platform_config.get("base_url", "")
            
            # Execute the operation
            if operation.get("is_async", False):
                result = await self._execute_async_operation(
                    integration,
                    operation,
                    base_url,
                    credentials,
                    parameters
                )
            else:
                result = await self._execute_sync_operation(
                    integration,
                    operation,
                    base_url,
                    credentials,
                    parameters
                )
            
            # Log the API call
            await self._log_api_call(
                integration_id=integration_id,
                operation_id=operation_id,
                business_id=business_id,
                user_id=user_id,
                parameters=parameters,
                result=result,
                credits_used=credits_required
            )
            
            return {
                "success": result.get("success", True),
                "data": result.get("data", {}),
                "raw_response": result.get("raw_response", {}),
                "credits_used": credits_required,
                "operation": operation["name"],
                "integration": integration.name
            }
            
        except Exception as e:
            logger.error(f"Dynamic integration execution failed: {e}", exc_info=True)
            # Refund credits on error
            await self.credit_service.refund_credits(
                business_id=business_id,
                credits_amount=operation.get("base_credits", 1),
                reason=f"Integration execution failed: {str(e)}"
            )
            return {
                "success": False,
                "error": str(e),
                "credits_used": 0
            }
    
    async def _execute_sync_operation(
        self,
        integration: models.Integration,
        operation: Dict[str, Any],
        base_url: str,
        credentials: Dict[str, Any],
        parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a synchronous API operation"""
        
        # Build request components
        url = self._build_url(base_url, operation["endpoint"], parameters, operation.get("parameters", []))
        headers = self._build_headers(integration, operation, credentials)
        body = self._build_body(parameters, operation.get("parameters", []))
        
        # Make HTTP request
        async with httpx.AsyncClient(timeout=integration.default_timeout_seconds) as client:
            method = operation.get("method", "POST").upper()
            
            logger.info(f"Executing {method} {url}")
            
            if method == "GET":
                response = await client.get(url, headers=headers)
            elif method == "POST":
                response = await client.post(url, headers=headers, json=body)
            elif method == "PUT":
                response = await client.put(url, headers=headers, json=body)
            elif method == "DELETE":
                response = await client.delete(url, headers=headers)
            elif method == "PATCH":
                response = await client.patch(url, headers=headers, json=body)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            # Parse response
            try:
                response_data = response.json()
            except:
                response_data = {"raw": response.text}
            
            # Map response according to configuration
            mapped_data = self._map_response(response_data, operation.get("response_mapping", {}))
            
            # Check if request was successful
            response_mapping = operation.get("response_mapping", {})
            is_success = self._check_success(response_data, response_mapping, response.status_code)
            
            return {
                "success": is_success,
                "data": mapped_data,
                "raw_response": response_data,
                "status_code": response.status_code
            }
    
    async def _execute_async_operation(
        self,
        integration: models.Integration,
        operation: Dict[str, Any],
        base_url: str,
        credentials: Dict[str, Any],
        parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute an asynchronous API operation with polling"""
        
        async_config = operation.get("async_config", {})
        
        # Step 1: Submit initial request
        task_endpoint = async_config.get("task_endpoint", operation["endpoint"])
        url = self._build_url(base_url, task_endpoint, parameters, operation.get("parameters", []))
        headers = self._build_headers(integration, operation, credentials)
        body = self._build_body(parameters, operation.get("parameters", []))
        
        async with httpx.AsyncClient(timeout=integration.default_timeout_seconds) as client:
            logger.info(f"Submitting async task: POST {url}")
            response = await client.post(url, headers=headers, json=body)
            
            try:
                initial_response = response.json()
            except:
                return {
                    "success": False,
                    "error": f"Failed to parse initial response: {response.text}"
                }
            
            # Step 2: Extract task ID
            task_id_field = async_config.get("task_id_field", "tasks[0].id")
            task_id = self._extract_field(initial_response, task_id_field)
            
            if not task_id:
                return {
                    "success": False,
                    "error": f"Could not extract task ID from response using field: {task_id_field}",
                    "raw_response": initial_response
                }
            
            logger.info(f"Task submitted with ID: {task_id}")
            
            # Step 3: Poll for completion
            result = await self._poll_task_completion(
                client,
                base_url,
                async_config,
                task_id,
                headers,
                integration.default_timeout_seconds
            )
            
            # Map final response
            if result.get("success"):
                mapped_data = self._map_response(result.get("data", {}), operation.get("response_mapping", {}))
                result["data"] = mapped_data
            
            return result
    
    async def _poll_task_completion(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        async_config: Dict[str, Any],
        task_id: str,
        headers: Dict[str, str],
        timeout: int
    ) -> Dict[str, Any]:
        """Poll for async task completion"""
        
        result_endpoint = async_config["result_endpoint"].replace("{task_id}", str(task_id))
        url = f"{base_url}{result_endpoint}"
        
        polling_interval = async_config.get("polling_interval_seconds", 5)
        max_attempts = async_config.get("max_polling_attempts", 60)
        completion_field = async_config["completion_field"]
        completion_value = async_config["completion_value"]
        
        for attempt in range(max_attempts):
            await asyncio.sleep(polling_interval)
            
            logger.info(f"Polling attempt {attempt + 1}/{max_attempts}: GET {url}")
            
            try:
                response = await client.get(url, headers=headers)
                response_data = response.json()
                
                # Check completion status
                status_value = self._extract_field(response_data, completion_field)
                
                if status_value == completion_value:
                    logger.info(f"Task completed successfully after {attempt + 1} attempts")
                    return {
                        "success": True,
                        "data": response_data,
                        "raw_response": response_data,
                        "polling_attempts": attempt + 1
                    }
                
                logger.debug(f"Task not complete yet. Status: {status_value}, Expected: {completion_value}")
                
            except Exception as e:
                logger.error(f"Error during polling attempt {attempt + 1}: {e}")
                continue
        
        # Timeout reached
        return {
            "success": False,
            "error": f"Task did not complete within {max_attempts} attempts",
            "polling_attempts": max_attempts
        }
    
    def _build_url(
        self,
        base_url: str,
        endpoint: str,
        parameters: Dict[str, Any],
        param_definitions: List[Dict[str, Any]]
    ) -> str:
        """Build complete URL with query parameters and path substitutions"""
        
        url = f"{base_url}{endpoint}"
        
        # Handle path parameters (e.g., /users/{user_id})
        for param_def in param_definitions:
            if param_def.get("location") == "path":
                param_name = param_def["name"]
                if param_name in parameters:
                    placeholder = f"{{{param_name}}}"
                    url = url.replace(placeholder, str(parameters[param_name]))
        
        # Handle query parameters
        query_params = {}
        for param_def in param_definitions:
            if param_def.get("location") == "query":
                param_name = param_def["name"]
                if param_name in parameters:
                    query_params[param_name] = parameters[param_name]
                elif not param_def.get("required", False) and "default" in param_def:
                    query_params[param_name] = param_def["default"]
        
        if query_params:
            url = f"{url}?{urlencode(query_params)}"
        
        return url
    
    def _build_headers(
        self,
        integration: models.Integration,
        operation: Dict[str, Any],
        credentials: Dict[str, Any]
    ) -> Dict[str, str]:
        """Build HTTP headers with authentication"""
        
        headers = {}
        
        # Add configured operation headers
        for header_def in operation.get("headers", []):
            headers[header_def["name"]] = header_def["value"]
        
        # Add authentication headers
        auth_config = integration.auth_config or {}
        auth_type = auth_config.get("type", "").lower()
        
        if auth_type == "basic":
            username = credentials.get("username", "")
            password = credentials.get("password", "")
            auth_string = base64.b64encode(f"{username}:{password}".encode()).decode()
            headers["Authorization"] = f"Basic {auth_string}"
        
        elif auth_type == "bearer":
            api_key = credentials.get("api_key", credentials.get("access_token", ""))
            headers["Authorization"] = f"Bearer {api_key}"
        
        elif auth_type == "api_key":
            # API key in header
            key_name = auth_config.get("header_name", "X-API-Key")
            api_key = credentials.get("api_key", "")
            headers[key_name] = api_key
        
        elif auth_type == "oauth2":
            access_token = credentials.get("access_token", "")
            headers["Authorization"] = f"Bearer {access_token}"
        
        return headers
    
    def _build_body(
        self,
        parameters: Dict[str, Any],
        param_definitions: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Build request body from parameters"""
        
        body = {}
        
        for param_def in param_definitions:
            if param_def.get("location") == "body":
                param_name = param_def["name"]
                
                # Use provided value, or default if not required
                if param_name in parameters:
                    body[param_name] = parameters[param_name]
                elif not param_def.get("required", False) and "default" in param_def:
                    body[param_name] = param_def["default"]
        
        return body
    
    def _map_response(
        self,
        response_data: Dict[str, Any],
        mapping: Dict[str, Any]
    ) -> Any:
        """Extract data from response using configured mapping"""
        
        if not mapping or not mapping.get("data_field"):
            return response_data
        
        data_field = mapping["data_field"]
        return self._extract_field(response_data, data_field) or response_data
    
    def _extract_field(self, data: Any, field_path: str) -> Any:
        """Extract field from nested dict/list using JSONPath-like syntax"""
        
        if not field_path or not data:
            return data
        
        # Simple JSONPath implementation
        # Supports: field.subfield and array[0] notation
        parts = field_path.replace("[", ".").replace("]", "").split(".")
        
        current = data
        for part in parts:
            if not part:
                continue
                
            try:
                if isinstance(current, dict):
                    current = current.get(part)
                elif isinstance(current, list):
                    index = int(part)
                    current = current[index] if index < len(current) else None
                else:
                    return None
                    
                if current is None:
                    return None
            except (KeyError, IndexError, ValueError, TypeError):
                return None
        
        return current
    
    def _check_success(
        self,
        response_data: Dict[str, Any],
        mapping: Dict[str, Any],
        status_code: int
    ) -> bool:
        """Check if request was successful"""
        
        # Check HTTP status code
        if status_code < 200 or status_code >= 300:
            return False
        
        # Check configured success field
        if mapping and mapping.get("success_field"):
            success_value = self._extract_field(response_data, mapping["success_field"])
            expected_value = mapping.get("success_value")
            return success_value == expected_value
        
        return True
    
    async def _get_credentials(
        self,
        integration: models.Integration,
        business_id: int
    ) -> Optional[Dict[str, Any]]:
        """Get credentials for integration (business > agency > system level)"""
        
        # Try business-level credentials first
        business_integration = self.db.query(models.BusinessIntegration).filter(
            models.BusinessIntegration.business_id == business_id,
            models.BusinessIntegration.integration_id == integration.id,
            models.BusinessIntegration.is_active == True
        ).first()
        
        if business_integration and business_integration.credentials:
            return business_integration.credentials
        
        # Try system-level credentials
        if integration.is_system_wide:
            system_integration = self.db.query(models.SystemIntegration).filter(
                models.SystemIntegration.integration_id == integration.id,
                models.SystemIntegration.is_active == True
            ).first()
            
            if system_integration and system_integration.credentials:
                return system_integration.credentials
        
        return None
    
    async def _log_api_call(
        self,
        integration_id: int,
        operation_id: str,
        business_id: int,
        user_id: int,
        parameters: Dict[str, Any],
        result: Dict[str, Any],
        credits_used: int
    ):
        """Log API call for auditing and debugging"""
        
        try:
            api_call = models.APICall(
                integration_id=integration_id,
                business_id=business_id,
                user_id=user_id,
                operation=operation_id,
                request_params=parameters,
                response_data=result.get("raw_response", {}),
                success=result.get("success", False),
                credits_used=credits_used,
                execution_time_ms=0,  # Could be calculated if needed
                error_message=result.get("error")
            )
            
            self.db.add(api_call)
            self.db.commit()
        except Exception as e:
            logger.error(f"Failed to log API call: {e}")

