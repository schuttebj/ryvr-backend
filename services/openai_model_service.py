"""
OpenAI Model Management Service
Handles model storage, retrieval, and refresh operations
"""

from sqlalchemy.orm import Session
from sqlalchemy import and_
from typing import List, Dict, Any, Optional
import logging
from datetime import datetime, timedelta
import asyncio

from openai import OpenAI
import models
from config import settings

logger = logging.getLogger(__name__)

class OpenAIModelService:
    """Service for managing OpenAI models in the database"""
    
    def __init__(self, db: Session):
        self.db = db
    
    async def get_stored_models(self, active_only: bool = True) -> List[models.OpenAIModel]:
        """Get all stored OpenAI models from database"""
        query = self.db.query(models.OpenAIModel)
        
        if active_only:
            query = query.filter(models.OpenAIModel.is_active == True)
        
        return query.order_by(models.OpenAIModel.model_id).all()
    
    async def get_default_model(self) -> Optional[models.OpenAIModel]:
        """Get the system default OpenAI model"""
        return self.db.query(models.OpenAIModel).filter(
            and_(
                models.OpenAIModel.is_default == True,
                models.OpenAIModel.is_active == True
            )
        ).first()
    
    async def set_default_model(self, model_id: str) -> bool:
        """Set a model as the system default"""
        try:
            # Remove default from all other models
            self.db.query(models.OpenAIModel).update({models.OpenAIModel.is_default: False})
            
            # Set the specified model as default
            model = self.db.query(models.OpenAIModel).filter(
                models.OpenAIModel.model_id == model_id
            ).first()
            
            if not model:
                logger.error(f"Model {model_id} not found in database")
                return False
            
            model.is_default = True
            self.db.commit()
            
            logger.info(f"Set {model_id} as default OpenAI model")
            return True
            
        except Exception as e:
            logger.error(f"Failed to set default model: {e}")
            self.db.rollback()
            return False
    
    async def refresh_models_from_api(self, api_key: Optional[str] = None) -> Dict[str, Any]:
        """Fetch latest models from OpenAI API and update database"""
        try:
            # Use provided API key or try to get from system integration
            if not api_key:
                api_key = await self._get_system_openai_key()
            
            if not api_key:
                logger.warning("No OpenAI API key available for model refresh")
                return {
                    "success": False,
                    "error": "No OpenAI API key configured",
                    "models_updated": 0
                }
            
            # Initialize OpenAI client
            client = OpenAI(api_key=api_key)
            
            # Fetch models from API
            logger.info("Fetching models from OpenAI API...")
            models_response = client.models.list()
            
            # Filter for chat completion models
            chat_models = []
            for model in models_response.data:
                # Filter for GPT models that support chat completions
                if any(gpt_prefix in model.id.lower() for gpt_prefix in ['gpt-3.5', 'gpt-4']):
                    chat_models.append({
                        "id": model.id,
                        "created": model.created,
                        "owned_by": model.owned_by
                    })
            
            # Update database
            models_updated = 0
            models_added = 0
            
            for model in chat_models:
                existing = self.db.query(models.OpenAIModel).filter(
                    models.OpenAIModel.model_id == model["id"]
                ).first()
                
                if existing:
                    # Update existing model
                    existing.created = model["created"]
                    existing.owned_by = model["owned_by"]
                    existing.is_active = True
                    existing.last_refreshed = datetime.utcnow()
                    models_updated += 1
                else:
                    # Add new model
                    new_model = models.OpenAIModel(
                        model_id=model["id"],
                        created=model["created"],
                        owned_by=model["owned_by"],
                        is_active=True,
                        display_name=self._generate_display_name(model["id"]),
                        description=self._generate_description(model["id"]),
                        cost_per_1k_tokens=self._estimate_cost(model["id"]),
                        max_tokens=self._estimate_max_tokens(model["id"]),
                        last_refreshed=datetime.utcnow()
                    )
                    self.db.add(new_model)
                    models_added += 1
            
            # Ensure we have a default model set
            await self._ensure_default_model()
            
            self.db.commit()
            
            logger.info(f"Model refresh completed: {models_added} added, {models_updated} updated")
            
            return {
                "success": True,
                "models_added": models_added,
                "models_updated": models_updated,
                "total_models": len(chat_models),
                "refreshed_at": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to refresh models from API: {e}")
            self.db.rollback()
            return {
                "success": False,
                "error": str(e),
                "models_updated": 0
            }
    
    async def ensure_fallback_models(self) -> None:
        """Ensure fallback models exist in database if API is unavailable"""
        fallback_models = [
            {
                "id": "gpt-4o",
                "created": 0,
                "owned_by": "openai",
                "display_name": "GPT-4o",
                "description": "Most advanced GPT-4 model with multimodal capabilities",
                "cost_per_1k_tokens": 0.03,
                "max_tokens": 128000
            },
            {
                "id": "gpt-4o-mini",
                "created": 0,
                "owned_by": "openai",
                "display_name": "GPT-4o Mini",
                "description": "Faster, more affordable GPT-4 variant (Recommended)",
                "cost_per_1k_tokens": 0.0015,
                "max_tokens": 128000,
                "is_default": True
            },
            {
                "id": "gpt-4-turbo",
                "created": 0,
                "owned_by": "openai",
                "display_name": "GPT-4 Turbo",
                "description": "Fast GPT-4 model with improved performance",
                "cost_per_1k_tokens": 0.01,
                "max_tokens": 128000
            },
            {
                "id": "gpt-3.5-turbo",
                "created": 0,
                "owned_by": "openai",
                "display_name": "GPT-3.5 Turbo",
                "description": "Fast and affordable model for most tasks",
                "cost_per_1k_tokens": 0.001,
                "max_tokens": 16384
            }
        ]
        
        for model_data in fallback_models:
            existing = self.db.query(models.OpenAIModel).filter(
                models.OpenAIModel.model_id == model_data["id"]
            ).first()
            
            if not existing:
                new_model = models.OpenAIModel(
                    model_id=model_data["id"],
                    created=model_data["created"],
                    owned_by=model_data["owned_by"],
                    is_active=True,
                    is_default=model_data.get("is_default", False),
                    display_name=model_data["display_name"],
                    description=model_data["description"],
                    cost_per_1k_tokens=model_data["cost_per_1k_tokens"],
                    max_tokens=model_data["max_tokens"],
                    last_refreshed=datetime.utcnow()
                )
                self.db.add(new_model)
        
        self.db.commit()
        logger.info("Ensured fallback models are available")
    
    async def should_refresh_models(self) -> bool:
        """Check if models should be refreshed (older than 24 hours)"""
        latest_refresh = self.db.query(models.OpenAIModel.last_refreshed).filter(
            models.OpenAIModel.last_refreshed.isnot(None)
        ).order_by(models.OpenAIModel.last_refreshed.desc()).first()
        
        if not latest_refresh or not latest_refresh[0]:
            return True
        
        # Refresh if older than 24 hours
        refresh_threshold = datetime.utcnow() - timedelta(hours=24)
        return latest_refresh[0] < refresh_threshold
    
    async def get_models_for_dropdown(self) -> List[Dict[str, Any]]:
        """Get models formatted for frontend dropdown"""
        stored_models = await self.get_stored_models()
        
        return [
            {
                "id": model.model_id,
                "name": model.display_name or model.model_id,
                "description": model.description,
                "is_default": model.is_default,
                "cost_per_1k_tokens": model.cost_per_1k_tokens,
                "max_tokens": model.max_tokens
            }
            for model in stored_models
        ]
    
    async def _get_system_openai_key(self) -> Optional[str]:
        """Get OpenAI API key from system integration"""
        try:
            # Get OpenAI integration
            openai_integration = self.db.query(models.Integration).filter(
                models.Integration.provider == "openai",
                models.Integration.is_active == True
            ).first()
            
            if not openai_integration:
                return None
            
            # Get system integration
            system_integration = self.db.query(models.SystemIntegration).filter(
                models.SystemIntegration.integration_id == openai_integration.id,
                models.SystemIntegration.is_active == True
            ).first()
            
            if not system_integration or not system_integration.credentials:
                return None
            
            return system_integration.credentials.get("api_key")
            
        except Exception as e:
            logger.error(f"Failed to get system OpenAI API key: {e}")
            return None
    
    async def _ensure_default_model(self) -> None:
        """Ensure at least one model is set as default"""
        current_default = await self.get_default_model()
        
        if not current_default:
            # Set gpt-4o-mini as default if available, otherwise first available model
            preferred_default = self.db.query(models.OpenAIModel).filter(
                and_(
                    models.OpenAIModel.model_id == "gpt-4o-mini",
                    models.OpenAIModel.is_active == True
                )
            ).first()
            
            if preferred_default:
                preferred_default.is_default = True
            else:
                # Use first available model
                first_model = self.db.query(models.OpenAIModel).filter(
                    models.OpenAIModel.is_active == True
                ).first()
                if first_model:
                    first_model.is_default = True
            
            self.db.commit()
    
    def _generate_display_name(self, model_id: str) -> str:
        """Generate user-friendly display name for model"""
        display_names = {
            "gpt-4o": "GPT-4o",
            "gpt-4o-mini": "GPT-4o Mini",
            "gpt-4-turbo": "GPT-4 Turbo",
            "gpt-4-turbo-preview": "GPT-4 Turbo Preview",
            "gpt-3.5-turbo": "GPT-3.5 Turbo",
            "gpt-3.5-turbo-16k": "GPT-3.5 Turbo 16K"
        }
        return display_names.get(model_id, model_id.replace("-", " ").title())
    
    def _generate_description(self, model_id: str) -> str:
        """Generate description for model"""
        descriptions = {
            "gpt-4o": "Most advanced GPT-4 model with multimodal capabilities",
            "gpt-4o-mini": "Faster, more affordable GPT-4 variant (Recommended)",
            "gpt-4-turbo": "Fast GPT-4 model with improved performance",
            "gpt-3.5-turbo": "Fast and affordable model for most tasks"
        }
        return descriptions.get(model_id, f"OpenAI model: {model_id}")
    
    def _estimate_cost(self, model_id: str) -> float:
        """Estimate cost per 1K tokens for model"""
        costs = {
            "gpt-4o": 0.03,
            "gpt-4o-mini": 0.0015,
            "gpt-4-turbo": 0.01,
            "gpt-3.5-turbo": 0.001
        }
        return costs.get(model_id, 0.01)  # Default estimate
    
    def _estimate_max_tokens(self, model_id: str) -> int:
        """Estimate maximum context window for model"""
        max_tokens = {
            "gpt-4o": 128000,
            "gpt-4o-mini": 128000,
            "gpt-4-turbo": 128000,
            "gpt-3.5-turbo": 16384,
            "gpt-3.5-turbo-16k": 16384
        }
        return max_tokens.get(model_id, 8192)  # Default estimate
