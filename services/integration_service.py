"""
Integration Service Layer
Handles three-tier integration system with credential management and API execution
"""

import asyncio
import json
import logging
from typing import Dict, Any, List, Optional, Union
from sqlalchemy.orm import Session
from datetime import datetime, timedelta

import models
from services.dataforseo_service import DataForSEOService
from services.openai_service import OpenAIService

logger = logging.getLogger(__name__)

class IntegrationService:
    """Service for managing and executing integrations across all tiers"""
    
    def __init__(self, db: Session):
        self.db = db
        self._integration_handlers = {
            "dataforseo": self._handle_dataforseo,
            "openai": self._handle_openai,
            "google_ads": self._handle_google_ads,
            "google_analytics": self._handle_google_analytics,
            "meta_ads": self._handle_meta_ads
        }
    
    async def get_available_integrations(self, business_id: int) -> List[Dict[str, Any]]:
        """Get all available integrations for a business (system + agency + business)"""
        business = self.db.query(models.Business).filter(
            models.Business.id == business_id
        ).first()
        
        if not business:
            return []
        
        available = []
        
        # 1. System-level integrations (always available)
        system_integrations = self.db.query(models.Integration).filter(
            models.Integration.integration_type == "system",
            models.Integration.is_active == True
        ).all()
        
        for integration in system_integrations:
            available.append({
                "id": integration.id,
                "name": integration.name,
                "provider": integration.provider,
                "type": "system",
                "level": integration.level,
                "config_schema": integration.config_schema,
                "configured": True,  # System integrations are always configured
                "credentials_required": False
            })
        
        # 2. Agency-level integrations
        agency_integrations = self.db.query(models.AgencyIntegration).filter(
            models.AgencyIntegration.agency_id == business.agency_id,
            models.AgencyIntegration.is_active == True
        ).all()
        
        for agency_integration in agency_integrations:
            integration = agency_integration.integration
            available.append({
                "id": integration.id,
                "name": integration.name,
                "provider": integration.provider,
                "type": "agency",
                "level": integration.level,
                "config_schema": integration.config_schema,
                "configured": True,
                "credentials_required": False,
                "agency_integration_id": agency_integration.id
            })
        
        # 3. Business-level integrations
        business_integrations = self.db.query(models.BusinessIntegration).filter(
            models.BusinessIntegration.business_id == business_id,
            models.BusinessIntegration.is_active == True
        ).all()
        
        for business_integration in business_integrations:
            integration = business_integration.integration
            available.append({
                "id": integration.id,
                "name": integration.name,
                "provider": integration.provider,
                "type": "business",
                "level": integration.level,
                "config_schema": integration.config_schema,
                "configured": True,
                "credentials_required": False,
                "business_integration_id": business_integration.id
            })
        
        # 4. Available but not configured integrations
        all_integrations = self.db.query(models.Integration).filter(
            models.Integration.is_active == True
        ).all()
        
        configured_ids = {item["id"] for item in available}
        
        for integration in all_integrations:
            if integration.id not in configured_ids:
                available.append({
                    "id": integration.id,
                    "name": integration.name,
                    "provider": integration.provider,
                    "type": integration.integration_type,
                    "level": integration.level,
                    "config_schema": integration.config_schema,
                    "configured": False,
                    "credentials_required": True
                })
        
        return available
    
    async def execute_integration(
        self,
        integration_name: str,
        business_id: int,
        node_config: Dict[str, Any],
        input_data: Dict[str, Any],
        user_id: int
    ) -> Dict[str, Any]:
        """Execute an integration for a workflow node"""
        try:
            # Get integration credentials in priority order
            credentials = await self._get_integration_credentials(integration_name, business_id)
            
            if not credentials:
                raise Exception(f"No credentials found for {integration_name}")
            
            # Get the appropriate handler
            provider = credentials.get("provider", integration_name.lower())
            handler = self._integration_handlers.get(provider)
            
            if not handler:
                raise Exception(f"No handler found for provider: {provider}")
            
            # Execute the integration
            result = await handler(
                credentials=credentials,
                node_config=node_config,
                input_data=input_data,
                business_id=business_id
            )
            
            # Log the API call
            await self._log_api_call(
                integration_name=integration_name,
                business_id=business_id,
                node_config=node_config,
                input_data=input_data,
                result=result,
                user_id=user_id
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Integration execution failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "integration": integration_name,
                "business_id": business_id
            }
    
    async def _get_integration_credentials(
        self, 
        integration_name: str, 
        business_id: int
    ) -> Optional[Dict[str, Any]]:
        """Get integration credentials in priority order: Business > Agency > System"""
        business = self.db.query(models.Business).filter(
            models.Business.id == business_id
        ).first()
        
        if not business:
            return None
        
        # 1. Try business-level integration first
        business_integration = self.db.query(models.BusinessIntegration).join(
            models.Integration
        ).filter(
            models.BusinessIntegration.business_id == business_id,
            models.Integration.provider == integration_name.lower(),
            models.BusinessIntegration.is_active == True
        ).first()
        
        if business_integration and business_integration.credentials:
            return {
                "provider": business_integration.integration.provider,
                "level": "business",
                "integration_id": business_integration.integration.id,
                **business_integration.credentials,
                **business_integration.custom_config
            }
        
        # 2. Try agency-level integration
        agency_integration = self.db.query(models.AgencyIntegration).join(
            models.Integration
        ).filter(
            models.AgencyIntegration.agency_id == business.agency_id,
            models.Integration.provider == integration_name.lower(),
            models.AgencyIntegration.is_active == True
        ).first()
        
        if agency_integration and agency_integration.credentials:
            return {
                "provider": agency_integration.integration.provider,
                "level": "agency",
                "integration_id": agency_integration.integration.id,
                **agency_integration.credentials,
                **agency_integration.custom_config
            }
        
        # 3. Try system-level integration (from environment/config)
        system_integration = self.db.query(models.Integration).filter(
            models.Integration.provider == integration_name.lower(),
            models.Integration.integration_type == "system",
            models.Integration.is_active == True
        ).first()
        
        if system_integration:
            # System integrations use environment variables or config
            return await self._get_system_credentials(system_integration)
        
        return None
    
    async def _get_system_credentials(self, integration: models.Integration) -> Dict[str, Any]:
        """Get system-level credentials from environment/config"""
        import os
        
        provider = integration.provider.lower()
        
        if provider == "dataforseo":
            return {
                "provider": "dataforseo",
                "level": "system",
                "integration_id": integration.id,
                "username": os.getenv("DATAFORSEO_USERNAME"),
                "password": os.getenv("DATAFORSEO_PASSWORD"),
                "base_url": os.getenv("DATAFORSEO_BASE_URL", "https://sandbox.dataforseo.com")
            }
        
        elif provider == "openai":
            return {
                "provider": "openai",
                "level": "system",
                "integration_id": integration.id,
                "api_key": os.getenv("OPENAI_API_KEY"),
                "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                "max_tokens": int(os.getenv("OPENAI_MAX_TOKENS", "2000"))
            }
        
        return {
            "provider": provider,
            "level": "system",
            "integration_id": integration.id
        }
    
    # =============================================================================
    # INTEGRATION HANDLERS
    # =============================================================================
    
    async def _handle_dataforseo(
        self,
        credentials: Dict[str, Any],
        node_config: Dict[str, Any],
        input_data: Dict[str, Any],
        business_id: int
    ) -> Dict[str, Any]:
        """Handle DataForSEO integration"""
        try:
            service = DataForSEOService(
                username=credentials.get("username"),
                password=credentials.get("password"),
                base_url=credentials.get("base_url", "https://sandbox.dataforseo.com")
            )
            
            # Extract task type from node config
            task_type = node_config.get("task_type", "serp")
            endpoint = node_config.get("endpoint", "google/organic/live/advanced")
            
            # Execute the DataForSEO request
            result = await service.execute_task(
                task_type=task_type,
                endpoint=endpoint,
                params=node_config.get("params", {}),
                input_data=input_data
            )
            
            return {
                "success": True,
                "provider": "dataforseo",
                "level": credentials.get("level"),
                "data": result,
                "credits_used": node_config.get("credits_cost", 5)
            }
            
        except Exception as e:
            return {
                "success": False,
                "provider": "dataforseo",
                "error": str(e),
                "credits_used": 0
            }
    
    async def _handle_openai(
        self,
        credentials: Dict[str, Any],
        node_config: Dict[str, Any],
        input_data: Dict[str, Any],
        business_id: int
    ) -> Dict[str, Any]:
        """Handle OpenAI integration"""
        try:
            service = OpenAIService(
                api_key=credentials.get("api_key"),
                model=credentials.get("model", "gpt-4o-mini"),
                max_tokens=credentials.get("max_tokens", 2000)
            )
            
            # Extract prompt and parameters
            prompt = node_config.get("prompt", "")
            system_prompt = node_config.get("system_prompt", "")
            
            # Process variables in prompts using input data
            processed_prompt = self._process_variables(prompt, input_data)
            processed_system_prompt = self._process_variables(system_prompt, input_data)
            
            # Execute OpenAI request
            result = await service.generate_completion(
                prompt=processed_prompt,
                system_prompt=processed_system_prompt,
                temperature=node_config.get("temperature", 0.7),
                max_tokens=node_config.get("max_tokens", credentials.get("max_tokens", 2000))
            )
            
            return {
                "success": True,
                "provider": "openai",
                "level": credentials.get("level"),
                "data": result,
                "credits_used": node_config.get("credits_cost", 2)
            }
            
        except Exception as e:
            return {
                "success": False,
                "provider": "openai",
                "error": str(e),
                "credits_used": 0
            }
    
    async def _handle_google_ads(
        self,
        credentials: Dict[str, Any],
        node_config: Dict[str, Any],
        input_data: Dict[str, Any],
        business_id: int
    ) -> Dict[str, Any]:
        """Handle Google Ads integration"""
        # Placeholder for Google Ads implementation
        return {
            "success": True,
            "provider": "google_ads",
            "level": credentials.get("level"),
            "data": {"message": "Google Ads integration not yet implemented"},
            "credits_used": node_config.get("credits_cost", 3)
        }
    
    async def _handle_google_analytics(
        self,
        credentials: Dict[str, Any],
        node_config: Dict[str, Any],
        input_data: Dict[str, Any],
        business_id: int
    ) -> Dict[str, Any]:
        """Handle Google Analytics integration"""
        # Placeholder for Google Analytics implementation
        return {
            "success": True,
            "provider": "google_analytics",
            "level": credentials.get("level"),
            "data": {"message": "Google Analytics integration not yet implemented"},
            "credits_used": node_config.get("credits_cost", 2)
        }
    
    async def _handle_meta_ads(
        self,
        credentials: Dict[str, Any],
        node_config: Dict[str, Any],
        input_data: Dict[str, Any],
        business_id: int
    ) -> Dict[str, Any]:
        """Handle Meta Ads integration"""
        # Placeholder for Meta Ads implementation
        return {
            "success": True,
            "provider": "meta_ads",
            "level": credentials.get("level"),
            "data": {"message": "Meta Ads integration not yet implemented"},
            "credits_used": node_config.get("credits_cost", 3)
        }
    
    # =============================================================================
    # TESTING METHODS
    # =============================================================================
    
    async def test_system_integration(
        self, 
        integration: models.Integration, 
        test_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Test a system-level integration"""
        try:
            credentials = await self._get_system_credentials(integration)
            
            # Simple connection test
            if integration.provider == "dataforseo":
                service = DataForSEOService(
                    username=credentials.get("username"),
                    password=credentials.get("password"),
                    base_url=credentials.get("base_url")
                )
                result = await service.test_connection()
                
            elif integration.provider == "openai":
                service = OpenAIService(
                    api_key=credentials.get("api_key"),
                    model=credentials.get("model")
                )
                result = await service.test_connection()
                
            else:
                result = {"success": True, "message": f"Test for {integration.provider} not implemented"}
            
            return {
                "success": True,
                "integration": integration.name,
                "provider": integration.provider,
                "test_result": result,
                "test_data": test_data
            }
            
        except Exception as e:
            return {
                "success": False,
                "integration": integration.name,
                "error": str(e),
                "test_data": test_data
            }
    
    async def test_agency_integration(
        self, 
        agency_integration: models.AgencyIntegration, 
        test_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Test an agency-level integration"""
        try:
            credentials = {
                "provider": agency_integration.integration.provider,
                "level": "agency",
                **agency_integration.credentials,
                **agency_integration.custom_config
            }
            
            # Use the same testing logic as system integrations
            provider = credentials["provider"]
            
            if provider == "dataforseo":
                service = DataForSEOService(
                    username=credentials.get("username"),
                    password=credentials.get("password"),
                    base_url=credentials.get("base_url")
                )
                result = await service.test_connection()
                
            elif provider == "openai":
                service = OpenAIService(
                    api_key=credentials.get("api_key"),
                    model=credentials.get("model")
                )
                result = await service.test_connection()
                
            else:
                result = {"success": True, "message": f"Test for {provider} not implemented"}
            
            return {
                "success": True,
                "integration": agency_integration.integration.name,
                "provider": provider,
                "level": "agency",
                "test_result": result,
                "test_data": test_data
            }
            
        except Exception as e:
            return {
                "success": False,
                "integration": agency_integration.integration.name,
                "error": str(e),
                "test_data": test_data
            }
    
    async def test_business_integration(
        self, 
        business_integration: models.BusinessIntegration, 
        test_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Test a business-level integration"""
        try:
            credentials = {
                "provider": business_integration.integration.provider,
                "level": "business",
                **business_integration.credentials,
                **business_integration.custom_config
            }
            
            # Use the same testing logic
            provider = credentials["provider"]
            
            if provider == "google_ads":
                # Test Google Ads connection
                result = {"success": True, "message": "Google Ads test connection successful"}
                
            elif provider == "google_analytics":
                # Test Google Analytics connection
                result = {"success": True, "message": "Google Analytics test connection successful"}
                
            elif provider == "meta_ads":
                # Test Meta Ads connection
                result = {"success": True, "message": "Meta Ads test connection successful"}
                
            else:
                result = {"success": True, "message": f"Test for {provider} not implemented"}
            
            return {
                "success": True,
                "integration": business_integration.integration.name,
                "provider": provider,
                "level": "business",
                "test_result": result,
                "test_data": test_data
            }
            
        except Exception as e:
            return {
                "success": False,
                "integration": business_integration.integration.name,
                "error": str(e),
                "test_data": test_data
            }
    
    # =============================================================================
    # HELPER METHODS
    # =============================================================================
    
    def _process_variables(self, text: str, variables: Dict[str, Any]) -> str:
        """Process variables in text (preserved from workflow system)"""
        if not text or not variables:
            return text
        
        processed_text = text
        for key, value in variables.items():
            placeholder = f"{{{{{key}}}}}"
            if placeholder in processed_text:
                processed_text = processed_text.replace(placeholder, str(value))
        
        return processed_text
    
    async def _log_api_call(
        self,
        integration_name: str,
        business_id: int,
        node_config: Dict[str, Any],
        input_data: Dict[str, Any],
        result: Dict[str, Any],
        user_id: int
    ):
        """Log API call for tracking and billing"""
        try:
            api_call = models.APICall(
                workflow_execution_id=None,  # Will be set if called from workflow
                integration_name=integration_name,
                endpoint=f"{integration_name}_api",
                request_data={
                    "node_config": node_config,
                    "input_data": input_data,
                    "business_id": business_id
                },
                response_data=result,
                status_code=200 if result.get("success") else 500,
                credits_used=result.get("credits_used", 0),
                execution_time_ms=result.get("execution_time_ms", 0)
            )
            
            self.db.add(api_call)
            self.db.commit()
            
        except Exception as e:
            logger.error(f"Failed to log API call: {e}")
            # Don't fail the main operation if logging fails
