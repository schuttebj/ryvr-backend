"""
SEO API Router
DataForSEO integration endpoints for SERP analysis, keyword research, and SEO tools
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import datetime
import logging

from database import get_db
from auth import get_current_active_user, get_current_admin_user
import models, schemas
from services.dataforseo_service import dataforseo_service

router = APIRouter()
logger = logging.getLogger(__name__)

# Account and Configuration Endpoints

@router.get("/account", response_model=Dict[str, Any])
async def get_dataforseo_account(
    current_user: models.User = Depends(get_current_active_user)
):
    """Get DataForSEO account information and credits"""
    try:
        account_info = dataforseo_service.get_account_info()
        return dataforseo_service.standardize_response(account_info, "account_info")
    except Exception as e:
        logger.error(f"DataForSEO account info error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get account information")

@router.get("/locations", response_model=List[Dict[str, Any]])
async def get_seo_locations(
    country_code: Optional[str] = Query(None, description="Filter by country code"),
    current_user: models.User = Depends(get_current_active_user)
):
    """Get available locations for SERP analysis"""
    try:
        locations = dataforseo_service.get_locations(country_code)
        return locations
    except Exception as e:
        logger.error(f"DataForSEO locations error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get locations")

@router.get("/languages", response_model=List[Dict[str, Any]])
async def get_seo_languages(
    current_user: models.User = Depends(get_current_active_user)
):
    """Get available languages for SERP analysis"""
    try:
        languages = dataforseo_service.get_languages()
        return languages
    except Exception as e:
        logger.error(f"DataForSEO languages error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get languages")

# SERP Analysis Endpoints

@router.post("/serp/analyze", response_model=Dict[str, Any])
async def analyze_serp(
    keyword: str = Query(..., description="Keyword to analyze"),
    location_code: int = Query(2840, description="Location code (default: USA)"),
    language_code: str = Query("en", description="Language code"),
    device: str = Query("desktop", description="Device type"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Submit SERP analysis task"""
    try:
        # Submit task to DataForSEO
        task_result = dataforseo_service.post_serp_task(
            keyword=keyword,
            location_code=location_code,
            language_code=language_code,
            device=device
        )
        
        # Create workflow execution record
        workflow_execution = models.WorkflowExecution(
            workflow_id=None,  # Can be linked to a workflow later
            client_id=current_user.id,
            status="pending",
            input_data={
                "keyword": keyword,
                "location_code": location_code,
                "language_code": language_code,
                "device": device
            },
            output_data={},
            credits_used=task_result.get('cost', 1),
            started_at=datetime.utcnow()
        )
        
        db.add(workflow_execution)
        db.commit()
        
        return dataforseo_service.standardize_response(task_result, "serp_analysis")
        
    except Exception as e:
        logger.error(f"SERP analysis error: {e}")
        raise HTTPException(status_code=500, detail="Failed to analyze SERP")

@router.get("/serp/results/{task_id}", response_model=Dict[str, Any])
async def get_serp_results(
    task_id: str,
    current_user: models.User = Depends(get_current_active_user)
):
    """Get SERP analysis results by task ID"""
    try:
        results = dataforseo_service.get_serp_results(task_id)
        return dataforseo_service.standardize_response(results, "serp_analysis")
    except Exception as e:
        logger.error(f"SERP results error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get SERP results")

@router.get("/serp/ready", response_model=List[Dict[str, Any]])
async def get_ready_serp_tasks(
    current_user: models.User = Depends(get_current_active_user)
):
    """Get list of completed SERP tasks"""
    try:
        ready_tasks = dataforseo_service.get_ready_serp_tasks()
        return ready_tasks
    except Exception as e:
        logger.error(f"Ready SERP tasks error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get ready tasks")

# Keyword Research Endpoints

@router.post("/keywords/search-volume", response_model=Dict[str, Any])
async def analyze_keywords_search_volume(
    keywords: List[str] = Query(..., description="List of keywords to analyze"),
    location_code: int = Query(2840, description="Location code (default: USA)"),
    language_code: str = Query("en", description="Language code"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Submit keyword search volume analysis task"""
    try:
        # Submit task to DataForSEO
        task_result = dataforseo_service.post_keywords_search_volume(
            keywords=keywords,
            location_code=location_code,
            language_code=language_code
        )
        
        # Create workflow execution record
        workflow_execution = models.WorkflowExecution(
            workflow_id=None,
            client_id=current_user.id,
            status="pending",
            input_data={
                "keywords": keywords,
                "location_code": location_code,
                "language_code": language_code
            },
            output_data={},
            credits_used=task_result.get('cost', len(keywords)),
            started_at=datetime.utcnow()
        )
        
        db.add(workflow_execution)
        db.commit()
        
        return dataforseo_service.standardize_response(task_result, "keyword_volume")
        
    except Exception as e:
        logger.error(f"Keyword search volume error: {e}")
        raise HTTPException(status_code=500, detail="Failed to analyze keyword search volume")

@router.get("/keywords/search-volume/{task_id}", response_model=Dict[str, Any])
async def get_keywords_search_volume_results(
    task_id: str,
    current_user: models.User = Depends(get_current_active_user)
):
    """Get keyword search volume results by task ID"""
    try:
        results = dataforseo_service.get_keywords_search_volume_results(task_id)
        return dataforseo_service.standardize_response(results, "keyword_volume")
    except Exception as e:
        logger.error(f"Keyword search volume results error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get keyword results")

@router.post("/keywords/for-site", response_model=Dict[str, Any])
async def get_keywords_for_site(
    target_site: str = Query(..., description="Target website domain"),
    location_code: int = Query(2840, description="Location code (default: USA)"),
    language_code: str = Query("en", description="Language code"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Get keywords that a website ranks for"""
    try:
        # Submit task to DataForSEO
        task_result = dataforseo_service.get_keywords_for_site(
            target_site=target_site,
            location_code=location_code,
            language_code=language_code
        )
        
        # Create workflow execution record
        workflow_execution = models.WorkflowExecution(
            workflow_id=None,
            client_id=current_user.id,
            status="pending",
            input_data={
                "target_site": target_site,
                "location_code": location_code,
                "language_code": language_code
            },
            output_data={},
            credits_used=task_result.get('cost', 5),
            started_at=datetime.utcnow()
        )
        
        db.add(workflow_execution)
        db.commit()
        
        return dataforseo_service.standardize_response(task_result, "keywords_for_site")
        
    except Exception as e:
        logger.error(f"Keywords for site error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get keywords for site")

# Competitor Analysis Endpoints

@router.post("/competitors/domain", response_model=Dict[str, Any])
async def analyze_competitors_domain(
    domain: str = Query(..., description="Target domain for competitor analysis"),
    location_code: int = Query(2840, description="Location code (default: USA)"),
    language_code: str = Query("en", description="Language code"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Get competitor domains for a given domain"""
    try:
        # Submit task to DataForSEO
        task_result = dataforseo_service.get_competitors_domain(
            domain=domain,
            location_code=location_code,
            language_code=language_code
        )
        
        # Create workflow execution record
        workflow_execution = models.WorkflowExecution(
            workflow_id=None,
            client_id=current_user.id,
            status="pending",
            input_data={
                "domain": domain,
                "location_code": location_code,
                "language_code": language_code
            },
            output_data={},
            credits_used=task_result.get('cost', 3),
            started_at=datetime.utcnow()
        )
        
        db.add(workflow_execution)
        db.commit()
        
        return dataforseo_service.standardize_response(task_result, "competitor_analysis")
        
    except Exception as e:
        logger.error(f"Competitor analysis error: {e}")
        raise HTTPException(status_code=500, detail="Failed to analyze competitors")

# Content Analysis Endpoints

@router.post("/content/analyze", response_model=Dict[str, Any])
async def analyze_content(
    content: str = Query(..., description="Content to analyze"),
    keyword: str = Query(..., description="Target keyword"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Analyze content for SEO optimization"""
    try:
        # Submit task to DataForSEO
        task_result = dataforseo_service.analyze_content(
            content=content,
            keyword=keyword
        )
        
        # Create workflow execution record
        workflow_execution = models.WorkflowExecution(
            workflow_id=None,
            client_id=current_user.id,
            status="pending",
            input_data={
                "content": content[:500],  # Truncate for storage
                "keyword": keyword
            },
            output_data={},
            credits_used=task_result.get('cost', 2),
            started_at=datetime.utcnow()
        )
        
        db.add(workflow_execution)
        db.commit()
        
        return dataforseo_service.standardize_response(task_result, "content_analysis")
        
    except Exception as e:
        logger.error(f"Content analysis error: {e}")
        raise HTTPException(status_code=500, detail="Failed to analyze content")

# Screenshot and Visual Analysis

@router.post("/serp/screenshot", response_model=Dict[str, Any])
async def get_serp_screenshot(
    keyword: str = Query(..., description="Keyword for SERP screenshot"),
    location_code: int = Query(2840, description="Location code (default: USA)"),
    language_code: str = Query("en", description="Language code"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Get SERP screenshot for visual analysis"""
    try:
        # Submit task to DataForSEO
        task_result = dataforseo_service.get_serp_screenshot(
            keyword=keyword,
            location_code=location_code,
            language_code=language_code
        )
        
        # Create workflow execution record
        workflow_execution = models.WorkflowExecution(
            workflow_id=None,
            client_id=current_user.id,
            status="pending",
            input_data={
                "keyword": keyword,
                "location_code": location_code,
                "language_code": language_code
            },
            output_data={},
            credits_used=task_result.get('cost', 1),
            started_at=datetime.utcnow()
        )
        
        db.add(workflow_execution)
        db.commit()
        
        return dataforseo_service.standardize_response(task_result, "serp_screenshot")
        
    except Exception as e:
        logger.error(f"SERP screenshot error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get SERP screenshot") 