"""
Embeddings Router
API endpoints for vector embeddings and semantic search
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
import logging

import models
import schemas
from database import get_db
from auth import get_current_active_user, get_current_business
from services.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/embeddings", tags=["embeddings"])


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_embedding_service(db: Session = Depends(get_db)) -> EmbeddingService:
    """Dependency to get embedding service"""
    return EmbeddingService(db)


def get_account_info(current_user: models.User) -> tuple[int, str]:
    """Get account ID and type from current user"""
    if current_user.role == 'agency':
        # Get agency ID
        agency_user = db.query(models.AgencyUser).filter(
            models.AgencyUser.user_id == current_user.id
        ).first()
        return agency_user.agency_id if agency_user else current_user.id, 'agency'
    else:
        return current_user.id, 'user'


# =============================================================================
# EMBEDDING GENERATION ENDPOINTS
# =============================================================================

@router.post("/files/{file_id}/generate", response_model=schemas.EmbeddingGenerateResponse)
async def generate_file_embeddings(
    file_id: int,
    request: schemas.EmbeddingGenerateRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
    embedding_service: EmbeddingService = Depends(get_embedding_service)
):
    """
    Generate vector embeddings for a file
    
    - Automatically chunks large documents
    - Uses OpenAI text-embedding-3-small model
    - Tracks credits used
    - Skips if embeddings already exist (unless force_regenerate=True)
    """
    try:
        # Get file and validate access
        file = db.query(models.File).filter(models.File.id == file_id).first()
        if not file:
            raise HTTPException(status_code=404, detail="File not found")
        
        # Validate user has access to this file
        account_id, account_type = get_account_info(current_user)
        
        if file.account_id != account_id or file.account_type != account_type:
            # Check if user has access through business
            if file.business_id:
                business_user = db.query(models.BusinessUser).filter(
                    models.BusinessUser.business_id == file.business_id,
                    models.BusinessUser.user_id == current_user.id,
                    models.BusinessUser.is_active == True
                ).first()
                
                if not business_user:
                    raise HTTPException(status_code=403, detail="Access denied to this file")
            else:
                raise HTTPException(status_code=403, detail="Access denied to this file")
        
        # Generate embeddings
        result = await embedding_service.generate_file_embeddings(
            file_id=file_id,
            business_id=file.business_id,
            account_id=account_id,
            account_type=account_type,
            force_regenerate=request.force_regenerate
        )
        
        return schemas.EmbeddingGenerateResponse(**result)
        
    except ValueError as e:
        logger.error(f"Validation error generating embeddings: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error generating embeddings for file {file_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to generate embeddings")


@router.post("/batch/generate")
async def batch_generate_embeddings(
    business_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
    embedding_service: EmbeddingService = Depends(get_embedding_service)
):
    """
    Generate embeddings for all files in a business that don't have them yet
    Useful for initial setup or bulk processing
    """
    try:
        # Validate business access
        business_user = db.query(models.BusinessUser).filter(
            models.BusinessUser.business_id == business_id,
            models.BusinessUser.user_id == current_user.id,
            models.BusinessUser.is_active == True
        ).first()
        
        if not business_user and current_user.role != 'admin':
            raise HTTPException(status_code=403, detail="Access denied to this business")
        
        # Get files without embeddings
        files = db.query(models.File).filter(
            models.File.business_id == business_id,
            models.File.is_active == True,
            models.File.embedding_status.in_(['pending', 'failed'])
        ).all()
        
        account_id, account_type = get_account_info(current_user)
        
        results = {
            'success': True,
            'total_files': len(files),
            'processed': 0,
            'failed': 0,
            'skipped': 0,
            'total_credits': 0
        }
        
        for file in files:
            try:
                result = await embedding_service.generate_file_embeddings(
                    file_id=file.id,
                    business_id=business_id,
                    account_id=account_id,
                    account_type=account_type,
                    force_regenerate=False
                )
                
                if result['success']:
                    results['processed'] += 1
                    results['total_credits'] += result.get('credits_used', 0)
                else:
                    results['skipped'] += 1
                    
            except Exception as e:
                logger.error(f"Failed to process file {file.id}: {str(e)}")
                results['failed'] += 1
        
        return results
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in batch embedding generation: {str(e)}")
        raise HTTPException(status_code=500, detail="Batch processing failed")


# =============================================================================
# SEMANTIC SEARCH ENDPOINTS
# =============================================================================

@router.post("/search", response_model=schemas.SemanticSearchResponse)
async def semantic_search(
    request: schemas.SemanticSearchRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
    embedding_service: EmbeddingService = Depends(get_embedding_service)
):
    """
    Semantic search across files using vector similarity
    
    - Searches within specified business context
    - Adjustable similarity threshold (0.0-1.0)
    - Optional file type filtering
    - Can search summaries (fast) or full content (thorough)
    
    Returns files ranked by semantic similarity to query
    """
    try:
        # Validate business access
        business_user = db.query(models.BusinessUser).filter(
            models.BusinessUser.business_id == request.business_id,
            models.BusinessUser.user_id == current_user.id,
            models.BusinessUser.is_active == True
        ).first()
        
        if not business_user and current_user.role != 'admin':
            raise HTTPException(status_code=403, detail="Access denied to this business")
        
        account_id, account_type = get_account_info(current_user)
        
        # Perform search
        results = await embedding_service.search_files(
            query=request.query,
            business_id=request.business_id,
            account_id=account_id,
            account_type=account_type,
            top_k=request.top_k,
            similarity_threshold=request.similarity_threshold,
            file_types=request.file_types,
            search_content=request.search_content
        )
        
        # Convert to response format
        search_results = [
            schemas.SemanticSearchResult(**result)
            for result in results
        ]
        
        return schemas.SemanticSearchResponse(
            success=True,
            query=request.query,
            results=search_results,
            count=len(search_results)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in semantic search: {str(e)}")
        raise HTTPException(status_code=500, detail="Search failed")


# =============================================================================
# WORKFLOW CONTEXT ENDPOINTS
# =============================================================================

@router.post("/context", response_model=schemas.WorkflowContextResponse)
async def get_workflow_context(
    request: schemas.WorkflowContextRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
    embedding_service: EmbeddingService = Depends(get_embedding_service)
):
    """
    Get relevant document context for workflow injection
    
    - Searches business knowledge base
    - Automatically formats and aggregates content
    - Respects token limits
    - Includes source file references
    
    Use this to inject relevant context into AI workflow nodes
    """
    try:
        # Validate business access
        business_user = db.query(models.BusinessUser).filter(
            models.BusinessUser.business_id == request.business_id,
            models.BusinessUser.user_id == current_user.id,
            models.BusinessUser.is_active == True
        ).first()
        
        if not business_user and current_user.role != 'admin':
            raise HTTPException(status_code=403, detail="Access denied to this business")
        
        account_id, account_type = get_account_info(current_user)
        
        # Get context
        result = await embedding_service.get_context_for_workflow(
            query=request.query,
            business_id=request.business_id,
            account_id=account_id,
            account_type=account_type,
            max_tokens=request.max_tokens,
            top_k=request.top_k,
            similarity_threshold=request.similarity_threshold,
            include_sources=request.include_sources
        )
        
        # Convert sources to response format
        sources = [
            schemas.ContextSource(**source)
            for source in result.get('sources', [])
        ]
        
        return schemas.WorkflowContextResponse(
            success=True,
            context=result['context'],
            token_count=result['token_count'],
            sources=sources,
            query=result['query'],
            results_used=result['results_used']
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting workflow context: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get context")


# =============================================================================
# UTILITY ENDPOINTS
# =============================================================================

@router.get("/stats/{business_id}")
async def get_embedding_stats(
    business_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """
    Get embedding statistics for a business
    
    - Total files
    - Files with embeddings
    - Total chunks
    - Credits used
    """
    try:
        # Validate access
        business_user = db.query(models.BusinessUser).filter(
            models.BusinessUser.business_id == business_id,
            models.BusinessUser.user_id == current_user.id,
            models.BusinessUser.is_active == True
        ).first()
        
        if not business_user and current_user.role != 'admin':
            raise HTTPException(status_code=403, detail="Access denied to this business")
        
        # Get statistics
        total_files = db.query(models.File).filter(
            models.File.business_id == business_id,
            models.File.is_active == True
        ).count()
        
        files_with_summary_embeddings = db.query(models.File).filter(
            models.File.business_id == business_id,
            models.File.is_active == True,
            models.File.summary_embedding.isnot(None)
        ).count()
        
        files_with_content_embeddings = db.query(models.File).filter(
            models.File.business_id == business_id,
            models.File.is_active == True,
            models.File.content_embedding.isnot(None)
        ).count()
        
        total_chunks = db.query(models.DocumentChunk).filter(
            models.DocumentChunk.business_id == business_id
        ).count()
        
        total_credits = db.query(
            models.File.embedding_credits_used
        ).filter(
            models.File.business_id == business_id,
            models.File.is_active == True
        ).all()
        
        credits_sum = sum([f[0] or 0 for f in total_credits])
        
        return {
            'success': True,
            'business_id': business_id,
            'total_files': total_files,
            'files_with_summary_embeddings': files_with_summary_embeddings,
            'files_with_content_embeddings': files_with_content_embeddings,
            'total_chunks': total_chunks,
            'total_credits_used': credits_sum,
            'coverage_percentage': round(
                (files_with_summary_embeddings / total_files * 100) if total_files > 0 else 0,
                2
            )
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting embedding stats: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get statistics")

