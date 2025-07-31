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
    device: str = Query("desktop", description="Device type (desktop/mobile)"),
    os: Optional[str] = Query(None, description="Operating system (auto-selected if not specified)"),
    depth: int = Query(10, description="Number of results to retrieve (1-700)"),
    target: Optional[str] = Query(None, description="Target domain filter (e.g., example.com)"),
    search_param: Optional[str] = Query(None, description="Additional search parameters for filtering"),
    result_type: Optional[str] = Query(None, description="Result type filter (news, shopping, images, videos)"),
    date_range: Optional[str] = Query(None, description="Date range filter"),
    organic_only: bool = Query(False, description="Filter to show only organic results with domains"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Submit SERP analysis task with enhanced filtering"""
    try:
        # Build search parameters from frontend filters
        search_params = ""
        
        # Date range filtering
        if date_range and date_range != 'any':
            date_filters = {
                'past_hour': 'qdr:h',
                'past_24h': 'qdr:d', 
                'past_week': 'qdr:w',
                'past_month': 'qdr:m',
                'past_year': 'qdr:y'
            }
            if date_range in date_filters:
                search_params += f"&tbs={date_filters[date_range]}"
        
        # Result type filtering
        if result_type and result_type != 'all':
            result_type_filters = {
                'news': '&tbm=nws',
                'shopping': '&tbm=shop',
                'images': '&tbm=isch', 
                'videos': '&tbm=vid'
            }
            if result_type in result_type_filters:
                search_params += result_type_filters[result_type]
        
        # Use provided search_param or build from filters
        final_search_param = search_param or (search_params if search_params else None)
        
        # Submit task to DataForSEO (asynchronous)
        task_submission = dataforseo_service.post_serp_task(
            keyword=keyword,
            location_code=location_code,
            language_code=language_code,
            device=device,
            os=os,
            depth=depth,
            target=target,
            search_param=final_search_param
        )
        
        # Extract task ID from submission response
        task_id = None
        if task_submission.get('tasks') and len(task_submission['tasks']) > 0:
            task_id = task_submission['tasks'][0].get('id')
        
        if not task_id:
            raise HTTPException(status_code=500, detail="Failed to get task ID from DataForSEO")
        
        logger.info(f"📋 SERP task submitted with ID: {task_id}")
        
        # Return task submission response with task ID for status checking
        return {
            "provider": "DataForSEO",
            "task_type": "serp_analysis",
            "timestamp": datetime.utcnow().isoformat(),
            "status": "submitted",
            "task_id": task_id,
            "message": "Task submitted successfully. Use task_id to check status and retrieve results.",
            "input_data": {
                "keyword": keyword,
                "location_code": location_code,
                "language_code": language_code,
                "device": device,
                "depth": depth,
                "organic_only": organic_only
            }
        }
        
        # Create workflow execution record for task submission
        workflow_execution = models.WorkflowExecution(
            workflow_id=None,  # Can be linked to a workflow later
            status="submitted",
            credits_used=0,  # Will be updated when task completes
            execution_data={
                "input_data": {
                "keyword": keyword,
                "location_code": location_code,
                "language_code": language_code,
                    "device": device,
                    "depth": depth,
                    "organic_only": organic_only
                },
                "task_id": task_id,
                "task_status": "submitted",
                "user_id": current_user.id  # Track who ran this
            }
        )
        
        db.add(workflow_execution)
        db.commit()
        
        return {
            "provider": "DataForSEO",
            "task_type": "serp_analysis",
            "timestamp": datetime.utcnow().isoformat(),
            "status": "submitted",
            "task_id": task_id,
            "message": "Task submitted successfully. Use task_id to check status and retrieve results.",
            "input_data": {
                "keyword": keyword,
                "location_code": location_code,
                "language_code": language_code,
                "device": device,
                "depth": depth,
                "organic_only": organic_only
            }
        }
        
    except Exception as e:
        logger.error(f"SERP analysis error: {e}")
        raise HTTPException(status_code=500, detail="Failed to analyze SERP")

@router.get("/serp/results/{task_id}", response_model=Dict[str, Any])
async def get_serp_results(
    task_id: str,
    organic_only: bool = Query(False, description="Filter to show only organic results with domains"),
    depth: int = Query(10, description="Number of results to retrieve (1-700)"),
    current_user: models.User = Depends(get_current_active_user)
):
    """Get SERP analysis results by task ID with optional filtering"""
    try:
        # Get raw results from DataForSEO
        raw_results = dataforseo_service.get_serp_results(task_id)
        
        # Log the raw response for debugging
        logger.info(f"🔍 DataForSEO raw response type: {type(raw_results)}")
        logger.info(f"🔍 DataForSEO raw response: {str(raw_results)[:500]}...")  # First 500 chars
        
        # Handle case where DataForSEO returns a list instead of dict
        if isinstance(raw_results, list):
            if len(raw_results) > 0 and isinstance(raw_results[0], dict):
                logger.info(f"🔄 Converting list response to dict using first element")
                raw_results = raw_results[0]
            else:
                logger.error(f"❌ Unexpected DataForSEO response format: {type(raw_results)}")
                raise HTTPException(status_code=500, detail="Invalid response format from DataForSEO")
        
        # Check if task is still processing
        if not isinstance(raw_results, dict) or raw_results.get('status_code') != 20000:
            return {
                "provider": "DataForSEO",
                "task_type": "serp_analysis",
                "timestamp": datetime.utcnow().isoformat(),
                "status": "processing",
                "task_id": task_id,
                "message": "Task is still processing. Please check again later.",
                "data": {}
            }
        
        # Process and filter results
        processed_results = raw_results
        
        # Add comprehensive logging for debugging
        logger.info(f"🔍 Raw results keys: {list(raw_results.keys()) if isinstance(raw_results, dict) else 'Not a dict'}")
        
        if 'tasks' in raw_results and raw_results['tasks']:
            logger.info(f"🔍 Tasks found: {len(raw_results['tasks'])}")
            task_data = raw_results['tasks'][0]
            logger.info(f"🔍 Task data type: {type(task_data)}")
            logger.info(f"🔍 Task data keys: {list(task_data.keys()) if isinstance(task_data, dict) else 'Not a dict'}")
            
            if 'result' in task_data:
                logger.info(f"🔍 Result type: {type(task_data['result'])}")
                if isinstance(task_data['result'], list):
                    logger.info(f"🔍 Result length: {len(task_data['result'])}")
                    if len(task_data['result']) > 0:
                        logger.info(f"🔍 First result type: {type(task_data['result'][0])}")
                        if isinstance(task_data['result'][0], dict):
                            logger.info(f"🔍 First result keys: {list(task_data['result'][0].keys())}")
        else:
            logger.info(f"🔍 No tasks found in raw_results")
            return dataforseo_service.standardize_response(processed_results, "serp_analysis")
            
        # Continue with task processing
        task_data = raw_results['tasks'][0]
        
        # Apply organic_only filter if requested
        if organic_only and 'result' in task_data and task_data['result']:
            logger.info(f"🔍 Applying organic_only filter with depth={depth}")
            
            # The result array contains the SERP items directly
            original_results = task_data['result']
            logger.info(f"📊 Original results count: {len(original_results)}")
            
            # Filter to only organic results with domains
            organic_results = [
                item for item in original_results
                if (isinstance(item, dict) and 
                    item.get('type') == 'organic' and 
                    item.get('domain') and 
                    item.get('url'))
            ]
            logger.info(f"🌱 Organic results count: {len(organic_results)}")
            
            # Limit to requested depth
            task_data['result'] = organic_results[:depth]
            logger.info(f"✂️ Final results count after depth limit: {len(task_data['result'])}")
        else:
            # Apply depth limit even if not filtering to organic only
            if 'result' in task_data and task_data['result']:
                logger.info(f"🔍 Applying depth limit={depth} (no organic filter)")
                original_count = len(task_data['result'])
                task_data['result'] = task_data['result'][:depth]
                logger.info(f"✂️ Limited results from {original_count} to {len(task_data['result'])}")
        
        # Log what we're passing to standardization
        logger.info(f"🔄 Passing to standardization: task_data result length: {len(task_data.get('result', []))}")
        if task_data.get('result') and len(task_data.get('result', [])) > 0:
            first_item = task_data['result'][0] if isinstance(task_data['result'], list) else None
            if first_item:
                logger.info(f"🔄 First result item keys: {list(first_item.keys()) if isinstance(first_item, dict) else 'Not a dict'}")
        
        # Return standardized response
        standardized_response = dataforseo_service.standardize_response(processed_results, "serp_analysis")
        logger.info(f"🔄 Standardized response data keys: {list(standardized_response.get('data', {}).keys())}")
        
        return standardized_response
        
    except Exception as e:
        logger.error(f"SERP results error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get SERP results")

@router.get("/serp/status/{task_id}", response_model=Dict[str, Any])
async def get_serp_task_status(
    task_id: str,
    current_user: models.User = Depends(get_current_active_user)
):
    """Check SERP task status by task ID"""
    try:
        # Get task status from DataForSEO
        task_status = dataforseo_service.get_serp_results(task_id)
        
        # Handle case where DataForSEO returns a list instead of dict
        if isinstance(task_status, list):
            if len(task_status) > 0 and isinstance(task_status[0], dict):
                task_status = task_status[0]
            else:
                logger.error(f"❌ Unexpected DataForSEO status response format: {type(task_status)}")
                raise HTTPException(status_code=500, detail="Invalid status response format from DataForSEO")
        
        # Determine status based on response
        if not isinstance(task_status, dict):
            logger.error(f"❌ Task status is not a dictionary: {type(task_status)}")
            raise HTTPException(status_code=500, detail="Invalid task status format")
            
        if task_status.get('status_code') == 20000:
            status = "completed"
            message = "Task completed successfully"
        elif task_status.get('status_code') == 20001:
            status = "processing"
            message = "Task is still processing"
        elif task_status.get('status_code') == 20002:
            status = "failed"
            message = "Task failed"
        else:
            status = "unknown"
            message = "Task status unknown"
        
        return {
            "provider": "DataForSEO",
            "task_type": "serp_analysis",
            "timestamp": datetime.utcnow().isoformat(),
            "status": status,
            "task_id": task_id,
            "message": message,
            "data": task_status
        }
        
    except Exception as e:
        logger.error(f"SERP task status error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get task status")

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
            status="completed",
            credits_used=task_result.get('cost', len(keywords)),
            execution_data={
                "input_data": {
                "keywords": keywords,
                "location_code": location_code,
                "language_code": language_code
            },
                "output_data": task_result,
                "user_id": current_user.id
            }
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
            status="completed",
            credits_used=task_result.get('cost', 5),
            execution_data={
                "input_data": {
                "target_site": target_site,
                "location_code": location_code,
                "language_code": language_code
            },
                "output_data": task_result,
                "user_id": current_user.id
            }
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

            status="completed",
            execution_data={
                "input_data": {
                "domain": domain,
                "location_code": location_code,
                "language_code": language_code
            },
                "output_data": task_result,
                "user_id": current_user.id
            },
            credits_used=task_result.get('cost', 3),

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

            status="completed",
            execution_data={
                "input_data": {
                "content": content[:500],  # Truncate for storage
                "keyword": keyword
            },
                "output_data": task_result,
                "user_id": current_user.id
            },
            credits_used=task_result.get('cost', 2),

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

            status="completed",
            execution_data={
                "input_data": {
                "keyword": keyword,
                "location_code": location_code,
                "language_code": language_code
            },
                "output_data": task_result,
                "user_id": current_user.id
            },
            credits_used=task_result.get('cost', 1),

        )
        
        db.add(workflow_execution)
        db.commit()
        
        return dataforseo_service.standardize_response(task_result, "serp_screenshot")
        
    except Exception as e:
        logger.error(f"SERP screenshot error: {e}")
        raise HTTPException(status_code=500, detail="Failed to get SERP screenshot") 