"""
File Management Router
Handles file upload, processing, storage, and management operations
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
import os
import logging
from datetime import datetime

from database import get_db
from auth import get_current_active_user, verify_business_access
import models, schemas
from services.file_service import FileService

router = APIRouter(prefix="/api/v1/files", tags=["files"])
logger = logging.getLogger(__name__)

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_file_service(db: Session = Depends(get_db)) -> FileService:
    """Dependency to get FileService instance"""
    return FileService(db)

def get_account_info(current_user: models.User) -> tuple[int, str]:
    """Get account ID and type from current user"""
    if current_user.role == 'agency':
        # For agencies, check if user owns an agency
        # This would need to be enhanced based on your agency ownership logic
        return current_user.id, 'agency'  # Simplified for now
    else:
        return current_user.id, 'user'

# =============================================================================
# ACCOUNT-LEVEL FILE ENDPOINTS
# =============================================================================

@router.post("/upload", response_model=schemas.FileUploadResponse)
async def upload_account_file(
    file: UploadFile = File(...),
    auto_process: bool = Form(True),
    auto_embed: bool = Form(False),  # NEW: Optional auto-embedding
    tags: Optional[str] = Form(None),  # JSON string of tags
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
    file_service: FileService = Depends(get_file_service)
):
    """
    Upload file to account level
    
    - auto_process: Extract text and generate AI summary (default: True)
    - auto_embed: Generate vector embeddings for semantic search (default: False)
    """
    try:
        account_id, account_type = get_account_info(current_user)
        
        # Parse tags if provided
        file_tags = []
        if tags:
            import json
            try:
                file_tags = json.loads(tags)
            except json.JSONDecodeError:
                pass
        
        # Upload file
        uploaded_file = await file_service.upload_file(
            file_data=file.file,
            original_filename=file.filename,
            account_id=account_id,
            account_type=account_type,
            uploaded_by=current_user.id,
            business_id=None,
            auto_process=auto_process
        )
        
        # Update tags if provided
        if file_tags:
            uploaded_file.tags = file_tags
            db.commit()
        
        # Optional: Generate embeddings automatically
        if auto_embed and uploaded_file.content_text:
            try:
                from services.embedding_service import EmbeddingService
                embedding_service = EmbeddingService(db)
                
                # Generate embeddings in background (don't block response)
                import asyncio
                asyncio.create_task(
                    embedding_service.generate_file_embeddings(
                        file_id=uploaded_file.id,
                        business_id=None,
                        account_id=account_id,
                        account_type=account_type,
                        force_regenerate=False
                    )
                )
            except Exception as e:
                logger.warning(f"Auto-embedding failed for file {uploaded_file.id}: {str(e)}")
                # Don't fail the upload if embedding fails
        
        return schemas.FileUploadResponse(
            id=uploaded_file.id,
            file_name=uploaded_file.file_name,
            original_name=uploaded_file.original_name,
            file_size=uploaded_file.file_size,
            file_type=uploaded_file.file_type,
            processing_status=uploaded_file.processing_status,
            created_at=uploaded_file.created_at
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"File upload error: {e}")
        raise HTTPException(status_code=500, detail="File upload failed")

@router.get("/", response_model=schemas.FileListResponse)
async def list_account_files(
    search_query: Optional[str] = Query(None, description="Search in filename, content, or summary"),
    file_type: Optional[str] = Query(None, description="Filter by file type"),
    limit: int = Query(50, le=100, description="Number of files to return"),
    offset: int = Query(0, ge=0, description="Number of files to skip"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
    file_service: FileService = Depends(get_file_service)
):
    """List account-level files"""
    try:
        account_id, account_type = get_account_info(current_user)
        
        files = await file_service.search_files(
            account_id=account_id,
            account_type=account_type,
            user_id=current_user.id,
            business_id=None,  # Account-level files only
            search_query=search_query,
            file_type=file_type,
            limit=limit,
            offset=offset
        )
        
        # Get total count for pagination
        total_query = db.query(models.File).filter(
            models.File.account_id == account_id,
            models.File.account_type == account_type,
            models.File.business_id.is_(None),
            models.File.is_active == True
        )
        
        if file_type:
            total_query = total_query.filter(models.File.file_type == file_type)
        
        if search_query:
            search_term = f"%{search_query}%"
            total_query = total_query.filter(
                (models.File.original_name.ilike(search_term)) |
                (models.File.content_text.ilike(search_term)) |
                (models.File.summary.ilike(search_term))
            )
        
        total_count = total_query.count()
        
        return schemas.FileListResponse(
            files=files,
            total_count=total_count,
            offset=offset,
            limit=limit
        )
        
    except Exception as e:
        logger.error(f"Error listing files: {e}")
        raise HTTPException(status_code=500, detail="Failed to list files")

# =============================================================================
# BUSINESS-LEVEL FILE ENDPOINTS
# =============================================================================

@router.post("/businesses/{business_id}/upload", response_model=schemas.FileUploadResponse)
async def upload_business_file(
    business_id: int,
    file: UploadFile = File(...),
    auto_process: bool = Form(True),
    tags: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
    file_service: FileService = Depends(get_file_service)
):
    """Upload file to specific business"""
    try:
        # Verify business access
        if not verify_business_access(db, current_user, business_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access to this business denied"
            )
        
        account_id, account_type = get_account_info(current_user)
        
        # Parse tags if provided
        file_tags = []
        if tags:
            import json
            try:
                file_tags = json.loads(tags)
            except json.JSONDecodeError:
                pass
        
        # Upload file
        uploaded_file = await file_service.upload_file(
            file_data=file.file,
            original_filename=file.filename,
            account_id=account_id,
            account_type=account_type,
            uploaded_by=current_user.id,
            business_id=business_id,
            auto_process=auto_process
        )
        
        # Update tags if provided
        if file_tags:
            uploaded_file.tags = file_tags
            db.commit()
        
        return schemas.FileUploadResponse(
            id=uploaded_file.id,
            file_name=uploaded_file.file_name,
            original_name=uploaded_file.original_name,
            file_size=uploaded_file.file_size,
            file_type=uploaded_file.file_type,
            processing_status=uploaded_file.processing_status,
            created_at=uploaded_file.created_at
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Business file upload error: {e}")
        raise HTTPException(status_code=500, detail="File upload failed")

@router.get("/businesses/{business_id}/", response_model=schemas.FileListResponse)
async def list_business_files(
    business_id: int,
    search_query: Optional[str] = Query(None),
    file_type: Optional[str] = Query(None),
    limit: int = Query(50, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
    file_service: FileService = Depends(get_file_service)
):
    """List files for specific business"""
    try:
        # Verify business access
        if not verify_business_access(db, current_user, business_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access to this business denied"
            )
        
        account_id, account_type = get_account_info(current_user)
        
        files = await file_service.search_files(
            account_id=account_id,
            account_type=account_type,
            user_id=current_user.id,
            business_id=business_id,
            search_query=search_query,
            file_type=file_type,
            limit=limit,
            offset=offset
        )
        
        # Get total count
        total_query = db.query(models.File).filter(
            models.File.account_id == account_id,
            models.File.account_type == account_type,
            models.File.business_id == business_id,
            models.File.is_active == True
        )
        
        if file_type:
            total_query = total_query.filter(models.File.file_type == file_type)
        
        if search_query:
            search_term = f"%{search_query}%"
            total_query = total_query.filter(
                (models.File.original_name.ilike(search_term)) |
                (models.File.content_text.ilike(search_term)) |
                (models.File.summary.ilike(search_term))
            )
        
        total_count = total_query.count()
        
        return schemas.FileListResponse(
            files=files,
            total_count=total_count,
            offset=offset,
            limit=limit
        )
        
    except Exception as e:
        logger.error(f"Error listing business files: {e}")
        raise HTTPException(status_code=500, detail="Failed to list files")

# =============================================================================
# INDIVIDUAL FILE OPERATIONS
# =============================================================================

@router.get("/{file_id}", response_model=schemas.File)
async def get_file_details(
    file_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
    file_service: FileService = Depends(get_file_service)
):
    """Get file details and metadata"""
    file_record = await file_service.get_file(file_id, current_user.id)
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")
    
    return file_record

@router.get("/{file_id}/download")
async def download_file(
    file_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
    file_service: FileService = Depends(get_file_service)
):
    """Download file content"""
    file_record = await file_service.get_file(file_id, current_user.id)
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")
    
    if not os.path.exists(file_record.file_path):
        raise HTTPException(status_code=404, detail="File content not found")
    
    return FileResponse(
        path=file_record.file_path,
        filename=file_record.original_name,
        media_type='application/octet-stream'
    )

@router.get("/{file_id}/content")
async def get_file_content(
    file_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
    file_service: FileService = Depends(get_file_service)
):
    """Get extracted text content of file"""
    file_record = await file_service.get_file(file_id, current_user.id)
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")
    
    return {
        "file_id": file_record.id,
        "original_name": file_record.original_name,
        "content_text": file_record.content_text,
        "summary": file_record.summary,
        "processing_status": file_record.processing_status
    }

@router.put("/{file_id}", response_model=schemas.File)
async def update_file(
    file_id: int,
    file_update: schemas.FileUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
    file_service: FileService = Depends(get_file_service)
):
    """Update file metadata (name, tags)"""
    file_record = await file_service.get_file(file_id, current_user.id)
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")
    
    # Update allowed fields
    for field, value in file_update.dict(exclude_unset=True).items():
        setattr(file_record, field, value)
    
    file_record.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(file_record)
    
    return file_record

@router.delete("/{file_id}")
async def delete_file(
    file_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
    file_service: FileService = Depends(get_file_service)
):
    """Delete file"""
    success = await file_service.delete_file(file_id, current_user.id)
    if not success:
        raise HTTPException(status_code=404, detail="File not found")
    
    return {"message": "File deleted successfully"}

@router.post("/{file_id}/summarize")
async def generate_file_summary(
    file_id: int,
    request: schemas.FileSummaryRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
    file_service: FileService = Depends(get_file_service)
):
    """Generate or regenerate AI summary for file"""
    file_record = await file_service.get_file(file_id, current_user.id)
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")
    
    if not file_record.content_text:
        raise HTTPException(status_code=400, detail="File content not available for summarization")
    
    # Check if summary already exists and force_regenerate is False
    if file_record.summary and not request.force_regenerate:
        return {
            "file_id": file_record.id,
            "summary": file_record.summary,
            "credits_used": file_record.summary_credits_used,
            "regenerated": False
        }
    
    try:
        # Generate new summary
        summary_result = await file_service.generate_file_summary(
            file_record.content_text, 
            file_record.business_id,
            file_record.account_id,
            file_record.account_type
        )
        
        # Update file record
        file_record.summary = summary_result['summary']
        file_record.summary_credits_used = summary_result['credits_used']
        db.commit()
        
        return {
            "file_id": file_record.id,
            "summary": summary_result['summary'],
            "credits_used": summary_result['credits_used'],
            "regenerated": True
        }
        
    except Exception as e:
        logger.error(f"Error generating summary: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate summary")

# =============================================================================
# FILE MANAGEMENT OPERATIONS
# =============================================================================

@router.post("/{file_id}/move")
async def move_file(
    file_id: int,
    move_request: schemas.FileMoveRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
    file_service: FileService = Depends(get_file_service)
):
    """Move file between account and business contexts"""
    file_record = await file_service.get_file(file_id, current_user.id)
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")
    
    # Verify access to target business if moving to business
    if move_request.target_business_id:
        if not verify_business_access(db, current_user, move_request.target_business_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access to target business denied"
            )
    
    # Update file business context
    old_business_id = file_record.business_id
    file_record.business_id = move_request.target_business_id
    
    # Update file path
    account_id, account_type = get_account_info(current_user)
    old_path = file_record.file_path
    
    if move_request.target_business_id:
        new_dir = f"{file_service.BASE_STORAGE_PATH}/{account_id}/business/{move_request.target_business_id}"
    else:
        new_dir = f"{file_service.BASE_STORAGE_PATH}/{account_id}/account"
    
    os.makedirs(new_dir, exist_ok=True)
    new_path = f"{new_dir}/{file_record.file_name}"
    
    # Move physical file
    try:
        import shutil
        shutil.move(old_path, new_path)
        file_record.file_path = new_path
        db.commit()
        
        return {"message": "File moved successfully", "new_business_id": move_request.target_business_id}
        
    except Exception as e:
        logger.error(f"Error moving file: {e}")
        # Rollback database changes
        file_record.business_id = old_business_id
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to move file")

# =============================================================================
# STORAGE MANAGEMENT
# =============================================================================

@router.get("/storage/usage", response_model=schemas.StorageUsageResponse)
async def get_storage_usage(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
    file_service: FileService = Depends(get_file_service)
):
    """Get current storage usage for account"""
    try:
        account_id, account_type = get_account_info(current_user)
        
        usage = await file_service.get_storage_usage(account_id, account_type)
        limit_bytes = await file_service._get_storage_limit(account_id, account_type)
        
        total_gb = usage['total_bytes'] / (1024 ** 3)
        limit_gb = limit_bytes / (1024 ** 3)
        usage_percentage = (usage['total_bytes'] / limit_bytes) * 100 if limit_bytes > 0 else 0
        
        return schemas.StorageUsageResponse(
            total_bytes=usage['total_bytes'],
            file_count=usage['file_count'],
            account_files_bytes=usage['account_files_bytes'],
            business_files_bytes=usage['business_files_bytes'],
            total_gb=round(total_gb, 2),
            limit_gb=round(limit_gb, 2),
            usage_percentage=round(usage_percentage, 1)
        )
        
    except Exception as e:
        logger.error(f"Error getting storage usage: {e}")
        raise HTTPException(status_code=500, detail="Failed to get storage usage")

# =============================================================================
# SEARCH AND FILTER
# =============================================================================

@router.post("/search", response_model=schemas.FileListResponse)
async def search_all_files(
    search_request: schemas.FileSearchRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user),
    file_service: FileService = Depends(get_file_service)
):
    """Search across all accessible files (account + business files)"""
    try:
        account_id, account_type = get_account_info(current_user)
        
        # Verify business access if business_id is specified
        if search_request.business_id:
            if not verify_business_access(db, current_user, search_request.business_id):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access to specified business denied"
                )
        
        files = await file_service.search_files(
            account_id=account_id,
            account_type=account_type,
            user_id=current_user.id,
            business_id=search_request.business_id,
            search_query=search_request.search_query,
            file_type=search_request.file_type,
            limit=search_request.limit,
            offset=search_request.offset
        )
        
        # Get total count for pagination
        total_query = db.query(models.File).filter(
            models.File.account_id == account_id,
            models.File.account_type == account_type,
            models.File.is_active == True
        )
        
        if search_request.business_id:
            total_query = total_query.filter(models.File.business_id == search_request.business_id)
        
        if search_request.file_type:
            total_query = total_query.filter(models.File.file_type == search_request.file_type)
        
        if search_request.search_query:
            search_term = f"%{search_request.search_query}%"
            total_query = total_query.filter(
                (models.File.original_name.ilike(search_term)) |
                (models.File.content_text.ilike(search_term)) |
                (models.File.summary.ilike(search_term))
            )
        
        total_count = total_query.count()
        
        return schemas.FileListResponse(
            files=files,
            total_count=total_count,
            offset=search_request.offset,
            limit=search_request.limit
        )
        
    except Exception as e:
        logger.error(f"Error searching files: {e}")
        raise HTTPException(status_code=500, detail="Search failed")
