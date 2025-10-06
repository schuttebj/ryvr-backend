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
from auth import get_current_active_user
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
    # Simplified to always use user account
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

@router.get("/files/{business_id}")
async def list_files_with_embeddings(
    business_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """
    List all files with their embedding status for a business
    
    Shows which files have been embedded and which haven't
    Useful for debugging and monitoring embedding coverage
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
        
        # Get all files with embedding info
        files = db.query(models.File).filter(
            models.File.business_id == business_id,
            models.File.is_active == True
        ).order_by(models.File.created_at.desc()).all()
        
        # Get chunk counts for each file
        file_list = []
        for file in files:
            chunk_count = db.query(models.DocumentChunk).filter(
                models.DocumentChunk.file_id == file.id
            ).count()
            
            # Check if chunks have embeddings
            chunks_with_embeddings = db.query(models.DocumentChunk).filter(
                models.DocumentChunk.file_id == file.id,
                models.DocumentChunk.chunk_embedding.isnot(None)
            ).count()
            
            # Determine if file is successfully embedded
            has_summary_embedding = file.summary_embedding is not None
            has_content_embedding = file.content_embedding is not None
            has_chunk_embeddings = chunks_with_embeddings > 0
            is_embedded = has_summary_embedding or has_content_embedding or has_chunk_embeddings
            
            # Create descriptive status
            if file.embedding_status == 'completed' and is_embedded:
                embedding_summary = f"Successfully embedded ({chunks_with_embeddings} chunks)"
            elif file.embedding_status == 'failed':
                embedding_summary = "Embedding failed"
            elif file.embedding_status == 'processing':
                embedding_summary = "Processing embeddings..."
            elif is_embedded:
                embedding_summary = "Embedded (partial)"
            else:
                embedding_summary = "Not yet embedded"
            
            file_list.append({
                'id': file.id,  # Add 'id' field for frontend compatibility
                'file_id': file.id,  # Keep for backwards compatibility
                'filename': file.original_name,
                'original_name': file.original_name,
                'file_name': file.file_name,
                'file_type': file.file_type,
                'file_size': file.file_size,
                'file_path': file.file_path,
                'content_text': None,  # Don't include full content for performance
                'summary': file.summary,
                'summary_credits_used': file.summary_credits_used or 0,
                'processing_status': file.processing_status,
                'tags': file.tags or [],
                'file_metadata': file.file_metadata or {},
                'is_active': file.is_active,
                'created_at': file.created_at.isoformat() if file.created_at else None,
                'updated_at': file.updated_at.isoformat() if file.updated_at else None,
                'account_id': file.account_id,
                'account_type': file.account_type,
                'business_id': file.business_id,
                'uploaded_by': file.uploaded_by,
                # Embedding-specific fields
                'embedding_status': file.embedding_status or 'pending',
                'is_embedded': is_embedded,
                'embedding_summary': embedding_summary,
                'has_summary_embedding': has_summary_embedding,
                'has_content_embedding': has_content_embedding,
                'chunk_count': chunk_count,
                'chunks_with_embeddings': chunks_with_embeddings,
                'embedding_coverage': round((chunks_with_embeddings / chunk_count * 100) if chunk_count > 0 else 0, 1),
                'embedding_credits_used': file.embedding_credits_used or 0,
                'embedding_model': file.embedding_model
            })
        
        # Calculate summary statistics
        embedded_count = sum(1 for f in file_list if f['is_embedded'])
        not_embedded_count = len(file_list) - embedded_count
        total_chunks = sum(f['chunk_count'] for f in file_list)
        total_embedded_chunks = sum(f['chunks_with_embeddings'] for f in file_list)
        
        return {
            'success': True,
            'business_id': business_id,
            'total_files': len(file_list),
            'embedded_files': embedded_count,
            'not_embedded_files': not_embedded_count,
            'embedding_percentage': round((embedded_count / len(file_list) * 100) if len(file_list) > 0 else 0, 1),
            'total_chunks': total_chunks,
            'total_embedded_chunks': total_embedded_chunks,
            'files': file_list
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing files with embeddings: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to list files")


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


# =============================================================================
# RAG CHAT ENDPOINT
# =============================================================================

@router.post("/chat", response_model=schemas.ChatResponse)
async def chat_with_documents(
    request: schemas.ChatRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
    embedding_service: EmbeddingService = Depends(get_embedding_service)
):
    """
    RAG (Retrieval Augmented Generation) Chat - Single Business
    
    Ask questions and get AI answers based on documents from a specific business
    """
    # Ensure business_id is provided for single business chat
    if not request.business_id:
        raise HTTPException(
            status_code=400, 
            detail="business_id is required for single business chat. Use /chat-all for cross-business chat."
        )
    
    return await _chat_implementation(request, db, current_user, embedding_service, cross_business=False)

@router.post("/chat-all", response_model=schemas.ChatResponse)
async def chat_with_all_documents(
    request: schemas.ChatRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
    embedding_service: EmbeddingService = Depends(get_embedding_service)
):
    """
    RAG (Retrieval Augmented Generation) Chat - Cross-Business
    
    Ask questions and get AI answers based on documents from all accessible businesses
    """
    return await _chat_implementation(request, db, current_user, embedding_service, cross_business=True)

async def _chat_implementation(
    request: schemas.ChatRequest,
    db: Session,
    current_user: models.User,
    embedding_service: EmbeddingService,
    cross_business: bool = False
):
    """
    RAG (Retrieval Augmented Generation) Chat Implementation
    
    Ask questions and get AI answers based on your uploaded documents
    
    - Searches your business documents for relevant context
    - Generates AI response using GPT-4/GPT-3.5-turbo
    - Returns answer with source citations
    - Tracks credit usage
    
    Perfect for:
    - Asking questions about your documents
    - Getting summaries across multiple files
    - Finding specific information quickly
    """
    try:
        # Validate access based on chat type
        if cross_business:
            # Cross-business chat - check if user has this feature
            if current_user.role != 'admin':
                subscription = current_user.subscription
                if not subscription or not subscription.tier.cross_business_chat:
                    raise HTTPException(
                        status_code=403,
                        detail="Cross-business chat not available in your subscription tier"
                    )
        else:
            # Single business chat - validate business access
            if not request.business_id:
                raise HTTPException(status_code=400, detail="business_id is required")
                
            business = db.query(models.Business).filter_by(id=request.business_id).first()
            if not business:
                raise HTTPException(status_code=404, detail="Business not found")
            
            # Check ownership or membership
            is_owner = business.owner_id == current_user.id
            is_member = db.query(models.BusinessUser).filter_by(
                business_id=request.business_id, user_id=current_user.id
            ).first() is not None
            
            if not (is_owner or is_member) and current_user.role != 'admin':
                raise HTTPException(status_code=403, detail="Access denied to this business")
        
        account_id, account_type = get_account_info(current_user)
        
        # Step 1: Get relevant context from documents
        logger.info(f"🔍 Searching documents for query: {request.message}")
        
        # TEMPORARY: Force lower threshold for better recall (0.7 is too strict)
        effective_threshold = min(request.similarity_threshold, 0.4)  # Use 0.4 max (40% similarity)
        logger.info(f"📊 Search parameters: top_k={request.top_k}, similarity_threshold={request.similarity_threshold} -> {effective_threshold}, business_id={request.business_id}")
        
        if cross_business:
            # For cross-business chat, search across all user's businesses
            user_businesses = []
            if current_user.role == 'admin':
                # Admins can access all businesses
                user_businesses = db.query(models.Business).all()
            else:
                # Get user's owned and member businesses
                owned_businesses = db.query(models.Business).filter_by(owner_id=current_user.id).all()
                member_businesses = db.query(models.Business).join(models.BusinessUser).filter(
                    models.BusinessUser.user_id == current_user.id
                ).all()
                
                # Combine and deduplicate
                business_ids = set()
                for business in owned_businesses + member_businesses:
                    if business.id not in business_ids:
                        user_businesses.append(business)
                        business_ids.add(business.id)
            
            # Search across all businesses (we'll need to modify the service for this)
            context_result = await embedding_service.get_context_for_workflow(
                query=request.message,
                business_id=None,  # None indicates cross-business search
                account_id=account_id,
                account_type=account_type,
                max_tokens=request.max_context_tokens,
                top_k=request.top_k,
                similarity_threshold=effective_threshold,  # Use lowered threshold
                include_sources=True,
                business_ids=[b.id for b in user_businesses]  # Pass list of accessible business IDs
            )
        else:
            # Single business search
            context_result = await embedding_service.get_context_for_workflow(
                query=request.message,
                business_id=request.business_id,
                account_id=account_id,
                account_type=account_type,
                max_tokens=request.max_context_tokens,
                top_k=request.top_k,
                similarity_threshold=effective_threshold,  # Use lowered threshold
                include_sources=True
            )
        
        context_found = bool(context_result.get('context', '').strip())
        
        # Debug logging
        logger.info(f"✅ Search complete: context_found={context_found}, sources={len(context_result.get('sources', []))}")
        if not context_found:
            logger.warning(f"⚠️ No relevant documents found for query: {request.message}")
            logger.warning(f"📋 Context result: {context_result}")
        
        # Step 2: Generate AI response with context
        from services.openai_service import OpenAIService
        
        # Get OpenAI API key
        api_key = embedding_service._get_openai_api_key(
            request.business_id, 
            account_id, 
            account_type
        )
        
        if not api_key:
            raise HTTPException(
                status_code=400, 
                detail="OpenAI API key not configured. Please set up OpenAI integration."
            )
        
        openai_service = OpenAIService(api_key=api_key)
        
        # Build system prompt
        system_prompt = """You are a helpful AI assistant that answers questions based on the user's uploaded documents.

Your job is to:
1. Answer questions accurately using ONLY the provided context from documents
2. If the context doesn't contain the answer, say "I don't have enough information in your documents to answer that."
3. Cite which documents you're referencing when possible
4. Be concise but thorough
5. If asked about multiple documents, synthesize information across them

Always base your answers on the provided context. Don't make up information."""

        # Build user prompt with context
        if context_found:
            user_prompt = f"""Context from uploaded documents:
---
{context_result['context']}
---

User Question: {request.message}

Please answer the question based on the context above. If the context doesn't contain relevant information, say so."""
        else:
            user_prompt = f"""No relevant documents were found for this question.

User Question: {request.message}

Please let the user know that you don't have any relevant documents to answer their question, and suggest they upload documents related to their question."""
        
        # Generate response
        logger.info(f"Generating AI response using model: {request.model}")
        ai_result = await openai_service.generate_completion(
            prompt=user_prompt,
            system_prompt=system_prompt,
            model=request.model,
            temperature=request.temperature,
            max_completion_tokens=1000
        )
        
        if not ai_result.get('success'):
            raise HTTPException(
                status_code=500,
                detail=f"AI generation failed: {ai_result.get('error', 'Unknown error')}"
            )
        
        # Calculate total credits used
        # Embedding search credits are tracked separately
        # AI generation credits from token usage
        tokens_used = ai_result.get('usage', {}).get('total_tokens', 0)
        credits_used = tokens_used  # 1 token = 1 credit (adjust as needed)
        
        # Track credits
        # Deduct credits for API usage (skip for admin users)
        if current_user.role != 'admin':
            from services.credit_service import CreditService
            credit_service = CreditService(db)
            
            # Get credit pool for the user
            credit_pool = db.query(models.CreditPool).filter(
                models.CreditPool.owner_id == account_id
            ).first()
            
            if credit_pool:
                credit_service.deduct_credits(
                    pool_id=credit_pool.id,
                    amount=credits_used,
                    description=f"RAG Chat: '{request.message[:50]}...'",
                    business_id=request.business_id,
                    created_by=current_user.id,
                    allow_overage=True
                )
            else:
                logger.warning(f"No credit pool found for user {current_user.id}, skipping credit deduction")
        
        # Format sources for response
        sources = [
            schemas.ContextSource(**source)
            for source in context_result.get('sources', [])
        ]
        
        return schemas.ChatResponse(
            success=True,
            message=request.message,
            response=ai_result['content'],
            sources=sources,
            context_found=context_found,
            tokens_used=tokens_used,
            credits_used=credits_used
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in RAG chat: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Chat failed: {str(e)}")

