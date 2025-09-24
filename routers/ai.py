"""
AI API Router
OpenAI integration endpoints for content generation, analysis, and automation
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import datetime
import logging

from database import get_db
from auth import get_current_active_user, get_current_admin_user
import models, schemas
from services.openai_service import openai_service

router = APIRouter()
logger = logging.getLogger(__name__)

# Content Generation Endpoints

@router.post("/content/generate", response_model=Dict[str, Any])
async def generate_content(
    prompt: str = Body(..., description="Content generation prompt"),
    model: str = Body("gpt-4o-mini", description="OpenAI model to use"),
    max_completion_tokens: int = Body(32768, description="Maximum tokens to generate"),
    temperature: float = Body(1.0, description="Creativity level (0.0-2.0)"),
    top_p: float = Body(1.0, description="Nucleus sampling parameter"),
    frequency_penalty: float = Body(0.0, description="Frequency penalty"),
    presence_penalty: float = Body(0.0, description="Presence penalty"),
    stop: Optional[List[str]] = Body(None, description="Stop sequences"),
    system_message: Optional[str] = Body(None, description="System context message"),
    response_format: Optional[Dict[str, str]] = Body({"type": "text"}, description="Response format"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Generate content using OpenAI's chat completion API"""
    try:
        # Generate content
        result = openai_service.generate_content(
            prompt=prompt,
            model=model,
            max_completion_tokens=max_completion_tokens,
            temperature=temperature,
            top_p=top_p,
            frequency_penalty=frequency_penalty,
            presence_penalty=presence_penalty,
            stop=stop,
            system_message=system_message,
            response_format=response_format
        )
        
        # Create workflow execution record
        workflow_execution = models.WorkflowExecution(
            workflow_id=None,
            client_id=current_user.id,
            status="completed",
            input_data={
                "prompt": prompt[:500],  # Truncate for storage
                "model": model,
                "max_completion_tokens": max_completion_tokens,
                "temperature": temperature
            },
            output_data={"content": result["content"][:500]},  # Truncate for storage
            credits_used=result["usage"]["total_tokens"],
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow()
        )
        
        db.add(workflow_execution)
        db.commit()
        
        return openai_service.standardize_response(result, "content_generation")
        
    except Exception as e:
        logger.error(f"Content generation error: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate content")

@router.post("/content/seo", response_model=Dict[str, Any])
async def generate_seo_content(
    keyword: str = Body(..., description="Target keyword"),
    content_type: str = Body("blog_post", description="Type of content to generate"),
    tone: str = Body("professional", description="Content tone"),
    length: int = Body(800, description="Approximate word count"),
    target_audience: str = Body("general", description="Target audience"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Generate SEO-optimized content"""
    try:
        # Generate SEO content
        result = openai_service.generate_seo_content(
            keyword=keyword,
            content_type=content_type,
            tone=tone,
            length=length,
            target_audience=target_audience
        )
        
        # Create workflow execution record
        workflow_execution = models.WorkflowExecution(
            workflow_id=None,
            client_id=current_user.id,
            status="completed",
            input_data={
                "keyword": keyword,
                "content_type": content_type,
                "tone": tone,
                "length": length,
                "target_audience": target_audience
            },
            output_data={"content": result["content"][:500]},
            credits_used=result["usage"]["total_tokens"],
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow()
        )
        
        db.add(workflow_execution)
        db.commit()
        
        return openai_service.standardize_response(result, "seo_content_generation")
        
    except Exception as e:
        logger.error(f"SEO content generation error: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate SEO content")

# Content Analysis Endpoints

@router.post("/content/analyze", response_model=Dict[str, Any])
async def analyze_content(
    content: str = Body(..., description="Content to analyze"),
    keyword: str = Body(..., description="Target keyword"),
    analysis_type: str = Body("seo", description="Type of analysis"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Analyze content for SEO, readability, and quality"""
    try:
        # Analyze content
        result = openai_service.analyze_content(
            content=content,
            keyword=keyword,
            analysis_type=analysis_type
        )
        
        # Create workflow execution record
        workflow_execution = models.WorkflowExecution(
            workflow_id=None,
            client_id=current_user.id,
            status="completed",
            input_data={
                "content": content[:500],
                "keyword": keyword,
                "analysis_type": analysis_type
            },
            output_data={"analysis": result["content"][:500]},
            credits_used=result["usage"]["total_tokens"],
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow()
        )
        
        db.add(workflow_execution)
        db.commit()
        
        return openai_service.standardize_response(result, "content_analysis")
        
    except Exception as e:
        logger.error(f"Content analysis error: {e}")
        raise HTTPException(status_code=500, detail="Failed to analyze content")

# Keyword Research Endpoints

@router.post("/keywords/generate", response_model=Dict[str, Any])
async def generate_keywords(
    topic: str = Body(..., description="Topic for keyword generation"),
    industry: str = Body("general", description="Industry context"),
    keyword_type: str = Body("long_tail", description="Type of keywords"),
    count: int = Body(20, description="Number of keywords to generate"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Generate keyword suggestions for a given topic"""
    try:
        # Generate keywords
        result = openai_service.generate_keywords(
            topic=topic,
            industry=industry,
            keyword_type=keyword_type,
            count=count
        )
        
        # Create workflow execution record
        workflow_execution = models.WorkflowExecution(
            workflow_id=None,
            client_id=current_user.id,
            status="completed",
            input_data={
                "topic": topic,
                "industry": industry,
                "keyword_type": keyword_type,
                "count": count
            },
            output_data={"keywords": result["content"][:500]},
            credits_used=result["usage"]["total_tokens"],
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow()
        )
        
        db.add(workflow_execution)
        db.commit()
        
        return openai_service.standardize_response(result, "keyword_generation")
        
    except Exception as e:
        logger.error(f"Keyword generation error: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate keywords")

# Ad Copy Generation Endpoints

@router.post("/ads/generate", response_model=Dict[str, Any])
async def generate_ad_copy(
    product: str = Body(..., description="Product or service description"),
    platform: str = Body("google_ads", description="Advertising platform"),
    campaign_type: str = Body("search", description="Campaign type"),
    target_audience: str = Body("general", description="Target audience"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Generate ad copy for various platforms"""
    try:
        # Generate ad copy
        result = openai_service.generate_ad_copy(
            product=product,
            platform=platform,
            campaign_type=campaign_type,
            target_audience=target_audience
        )
        
        # Create workflow execution record
        workflow_execution = models.WorkflowExecution(
            workflow_id=None,
            client_id=current_user.id,
            status="completed",
            input_data={
                "product": product,
                "platform": platform,
                "campaign_type": campaign_type,
                "target_audience": target_audience
            },
            output_data={"ad_copy": result["content"][:500]},
            credits_used=result["usage"]["total_tokens"],
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow()
        )
        
        db.add(workflow_execution)
        db.commit()
        
        return openai_service.standardize_response(result, "ad_copy_generation")
        
    except Exception as e:
        logger.error(f"Ad copy generation error: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate ad copy")

# Email Marketing Endpoints

@router.post("/email/sequence", response_model=Dict[str, Any])
async def generate_email_sequence(
    topic: str = Body(..., description="Email sequence topic"),
    sequence_type: str = Body("welcome", description="Type of email sequence"),
    email_count: int = Body(5, description="Number of emails in sequence"),
    tone: str = Body("professional", description="Email tone"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Generate email sequence for marketing campaigns"""
    try:
        # Generate email sequence
        result = openai_service.generate_email_sequence(
            topic=topic,
            sequence_type=sequence_type,
            email_count=email_count,
            tone=tone
        )
        
        # Create workflow execution record
        workflow_execution = models.WorkflowExecution(
            workflow_id=None,
            client_id=current_user.id,
            status="completed",
            input_data={
                "topic": topic,
                "sequence_type": sequence_type,
                "email_count": email_count,
                "tone": tone
            },
            output_data={"email_sequence": result["content"][:500]},
            credits_used=result["usage"]["total_tokens"],
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow()
        )
        
        db.add(workflow_execution)
        db.commit()
        
        return openai_service.standardize_response(result, "email_sequence_generation")
        
    except Exception as e:
        logger.error(f"Email sequence generation error: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate email sequence")

# Batch Processing Endpoints

@router.post("/batch/generate", response_model=List[Dict[str, Any]])
async def batch_generate_content(
    prompts: List[str] = Body(..., description="List of prompts to process"),
    model: str = Body("gpt-4o-mini", description="OpenAI model to use"),
    max_completion_tokens: int = Body(16384, description="Maximum tokens per generation"),
    temperature: float = Body(1.0, description="Creativity level"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Generate content for multiple prompts"""
    try:
        # Batch generate content
        results = openai_service.batch_generate(
            prompts=prompts,
            model=model,
            max_completion_tokens=max_completion_tokens,
            temperature=temperature
        )
        
        # Create workflow execution record
        total_tokens = sum(r.get("usage", {}).get("total_tokens", 0) for r in results)
        
        workflow_execution = models.WorkflowExecution(
            workflow_id=None,
            client_id=current_user.id,
            status="completed",
            input_data={
                "prompts": [p[:100] for p in prompts],  # Truncate for storage
                "model": model,
                "prompt_count": len(prompts)
            },
            output_data={"results_count": len(results)},
            credits_used=total_tokens,
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow()
        )
        
        db.add(workflow_execution)
        db.commit()
        
        return [openai_service.standardize_response(result, "batch_content_generation") for result in results]
        
    except Exception as e:
        logger.error(f"Batch generation error: {e}")
        raise HTTPException(status_code=500, detail="Failed to batch generate content")

# Model Management Endpoints

@router.post("/models/fetch-from-integration", response_model=List[Dict[str, Any]])
async def fetch_models_from_integration(
    integration_id: str = Body(..., description="Integration ID to use for API key"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Fetch available OpenAI models using a specific integration's API key"""
    try:
        # Get the integration from localStorage/database
        # For now, we'll expect the API key to be passed from frontend
        # since integrations are stored in localStorage
        raise HTTPException(status_code=400, detail="Please provide API key directly")
        
    except Exception as e:
        logger.error(f"Failed to fetch models from integration: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch models from integration")

@router.post("/models/fetch-with-key", response_model=List[Dict[str, Any]])
async def fetch_models_with_api_key(
    api_key: str = Body(..., description="OpenAI API key"),
    current_user: models.User = Depends(get_current_active_user)
):
    """Fetch available OpenAI models using provided API key"""
    try:
        # Create temporary OpenAI service with provided API key
        temp_openai_service = OpenAIService(api_key=api_key)
        models = temp_openai_service.get_available_models()
        return models
    except Exception as e:
        logger.error(f"Failed to fetch models with provided API key: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch models with API key")

@router.get("/models/available", response_model=List[Dict[str, Any]])
async def get_available_models(
    current_user: models.User = Depends(get_current_active_user)
):
    """Get list of available OpenAI models (fallback - returns static models)"""
    try:
        # Return static fallback models since we want integration-specific fetching
        logger.info("Returning static fallback models - use /models/fetch-with-key for live models")
        return [
            {"id": "gpt-4o", "created": 0, "owned_by": "openai"},
            {"id": "gpt-4o-mini", "created": 0, "owned_by": "openai"},
            {"id": "gpt-4-turbo", "created": 0, "owned_by": "openai"},
            {"id": "gpt-3.5-turbo", "created": 0, "owned_by": "openai"}
        ]
    except Exception as e:
        logger.error(f"Failed to fetch models: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch available models")

@router.get("/models/recommended", response_model=Dict[str, Any])
async def get_recommended_model(
    task_type: str = Query("general", description="Task type: general, complex, fast, creative"),
    current_user: models.User = Depends(get_current_active_user)
):
    """Get recommended model for a specific task type"""
    try:
        recommended_model = openai_service.get_recommended_model(task_type)
        return {
            "success": True,
            "recommended_model": recommended_model,
            "task_type": task_type
        }
    except Exception as e:
        logger.error(f"Failed to get recommended model: {e}")
        raise HTTPException(status_code=500, detail="Failed to get recommended model") 