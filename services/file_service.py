"""
File Management Service
Handles file upload, content extraction, summarization, and storage management
"""

import os
import uuid
import magic
import aiofiles
import logging
from typing import Dict, List, Optional, Any, BinaryIO
from datetime import datetime
from pathlib import Path
from sqlalchemy.orm import Session

# File processing imports
import PyPDF2
from docx import Document
import io

# Internal imports
import models
from config import settings
from services.openai_service import OpenAIService
from services.credit_service import CreditService

logger = logging.getLogger(__name__)

class FileService:
    """Service for handling file operations, content extraction, and AI processing"""
    
    # Supported file types and their MIME types
    SUPPORTED_TYPES = {
        'text/plain': ['txt', 'text'],
        'application/pdf': ['pdf'],
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['docx'],
        'application/msword': ['doc'],
        'text/markdown': ['md'],
        'text/rtf': ['rtf']
    }
    
    # Storage limits (can be moved to config/settings later)
    DEFAULT_STORAGE_LIMIT_GB = 5
    MAX_FILE_SIZE_MB = 100
    BASE_STORAGE_PATH = "/files"
    
    def __init__(self, db: Session):
        self.db = db
        self.credit_service = CreditService(db)
        
    # =============================================================================
    # FILE UPLOAD AND MANAGEMENT
    # =============================================================================
    
    async def upload_file(
        self,
        file_data: BinaryIO,
        original_filename: str,
        account_id: int,
        account_type: str,
        uploaded_by: int,
        business_id: Optional[int] = None,
        auto_process: bool = True
    ) -> models.File:
        """Upload and process a file"""
        
        # Validate file
        await self._validate_file_upload(file_data, original_filename, account_id, account_type)
        
        # Generate unique filename and determine storage path
        file_uuid = str(uuid.uuid4())
        file_extension = Path(original_filename).suffix.lower()
        safe_filename = self._sanitize_filename(original_filename)
        stored_filename = f"{file_uuid}_{safe_filename}"
        
        # Determine storage path based on business context
        if business_id:
            storage_dir = f"{self.BASE_STORAGE_PATH}/{account_id}/business/{business_id}"
        else:
            storage_dir = f"{self.BASE_STORAGE_PATH}/{account_id}/account"
            
        # Ensure directory exists
        os.makedirs(storage_dir, exist_ok=True)
        file_path = f"{storage_dir}/{stored_filename}"
        
        # Get file size and type
        file_data.seek(0, 2)  # Seek to end
        file_size = file_data.tell()
        file_data.seek(0)  # Reset to beginning
        
        # Detect MIME type
        file_content = file_data.read()
        file_data.seek(0)
        mime_type = magic.from_buffer(file_content, mime=True)
        file_type = self._get_file_type_from_mime(mime_type, file_extension)
        
        # Save file to disk
        async with aiofiles.open(file_path, 'wb') as f:
            await f.write(file_content)
        
        # Create database record
        db_file = models.File(
            account_id=account_id,
            account_type=account_type,
            business_id=business_id,
            uploaded_by=uploaded_by,
            file_name=stored_filename,
            original_name=original_filename,
            file_type=file_type,
            file_size=file_size,
            file_path=file_path,
            metadata={
                'mime_type': mime_type,
                'file_extension': file_extension,
                'upload_timestamp': datetime.utcnow().isoformat()
            }
        )
        
        self.db.add(db_file)
        self.db.commit()
        self.db.refresh(db_file)
        
        # Update storage usage
        await self._update_storage_usage(account_id, account_type, file_size, 1)
        
        # Process file content if auto_process is enabled
        if auto_process:
            await self._process_file_content(db_file)
        
        return db_file
    
    async def _validate_file_upload(
        self, 
        file_data: BinaryIO, 
        filename: str, 
        account_id: int, 
        account_type: str
    ):
        """Validate file before upload"""
        
        # Check file size
        file_data.seek(0, 2)
        file_size = file_data.tell()
        file_data.seek(0)
        
        if file_size > self.MAX_FILE_SIZE_MB * 1024 * 1024:
            raise ValueError(f"File size exceeds {self.MAX_FILE_SIZE_MB}MB limit")
        
        # Check storage quota
        current_usage = await self.get_storage_usage(account_id, account_type)
        storage_limit = await self._get_storage_limit(account_id, account_type)
        
        if current_usage['total_bytes'] + file_size > storage_limit:
            raise ValueError("Storage quota exceeded")
        
        # Check file type
        file_content = file_data.read(1024)  # Read first 1KB for type detection
        file_data.seek(0)
        mime_type = magic.from_buffer(file_content, mime=True)
        
        if not self._is_supported_file_type(mime_type, filename):
            supported_extensions = []
            for extensions in self.SUPPORTED_TYPES.values():
                supported_extensions.extend(extensions)
            raise ValueError(f"Unsupported file type. Supported types: {', '.join(supported_extensions)}")
    
    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename for safe storage"""
        # Remove path components and dangerous characters
        safe_chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
        name = Path(filename).name
        sanitized = ''.join(c if c in safe_chars else '_' for c in name)
        return sanitized[:100]  # Limit length
    
    def _get_file_type_from_mime(self, mime_type: str, extension: str) -> str:
        """Get file type from MIME type or extension"""
        for mime, extensions in self.SUPPORTED_TYPES.items():
            if mime_type == mime or extension.lstrip('.') in extensions:
                return extension.lstrip('.')
        return 'unknown'
    
    def _is_supported_file_type(self, mime_type: str, filename: str) -> bool:
        """Check if file type is supported"""
        extension = Path(filename).suffix.lower().lstrip('.')
        
        for mime, extensions in self.SUPPORTED_TYPES.items():
            if mime_type == mime or extension in extensions:
                return True
        return False
    
    # =============================================================================
    # CONTENT EXTRACTION
    # =============================================================================
    
    async def _process_file_content(self, file_record: models.File):
        """Extract content and generate summary for a file"""
        try:
            file_record.processing_status = 'processing'
            self.db.commit()
            
            # Extract text content
            content = await self.extract_file_content(file_record.file_path, file_record.file_type)
            file_record.content_text = content
            
            # Generate summary if content is substantial
            if content and len(content.strip()) > 100:
                summary_result = await self.generate_file_summary(content, file_record.business_id or file_record.account_id)
                file_record.summary = summary_result['summary']
                file_record.summary_credits_used = summary_result['credits_used']
            
            file_record.processing_status = 'completed'
            
        except Exception as e:
            logger.error(f"Error processing file {file_record.id}: {e}")
            file_record.processing_status = 'failed'
            file_record.metadata = {
                **file_record.metadata,
                'processing_error': str(e)
            }
        
        self.db.commit()
    
    async def extract_file_content(self, file_path: str, file_type: str) -> str:
        """Extract text content from various file formats"""
        try:
            if file_type.lower() in ['txt', 'text', 'md']:
                return await self._extract_text_content(file_path)
            elif file_type.lower() == 'pdf':
                return await self._extract_pdf_content(file_path)
            elif file_type.lower() in ['docx']:
                return await self._extract_docx_content(file_path)
            elif file_type.lower() == 'rtf':
                return await self._extract_rtf_content(file_path)
            else:
                logger.warning(f"Unsupported file type for content extraction: {file_type}")
                return ""
        except Exception as e:
            logger.error(f"Error extracting content from {file_path}: {e}")
            return ""
    
    async def _extract_text_content(self, file_path: str) -> str:
        """Extract content from plain text files"""
        async with aiofiles.open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            return await f.read()
    
    async def _extract_pdf_content(self, file_path: str) -> str:
        """Extract text from PDF files"""
        text_content = []
        
        with open(file_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            
            for page_num, page in enumerate(pdf_reader.pages):
                try:
                    text = page.extract_text()
                    if text.strip():
                        text_content.append(text)
                except Exception as e:
                    logger.warning(f"Error extracting text from page {page_num}: {e}")
                    continue
        
        return '\n\n'.join(text_content)
    
    async def _extract_docx_content(self, file_path: str) -> str:
        """Extract text from Word documents"""
        try:
            doc = Document(file_path)
            paragraphs = []
            
            for paragraph in doc.paragraphs:
                text = paragraph.text.strip()
                if text:
                    paragraphs.append(text)
            
            return '\n\n'.join(paragraphs)
        except Exception as e:
            logger.error(f"Error extracting DOCX content: {e}")
            return ""
    
    async def _extract_rtf_content(self, file_path: str) -> str:
        """Basic RTF content extraction (simplified)"""
        try:
            # For now, treat RTF as plain text (can be enhanced with striprtf library)
            async with aiofiles.open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = await f.read()
                # Basic RTF tag removal (very simplified)
                import re
                content = re.sub(r'\\[a-z]+\d*\s?', '', content)
                content = re.sub(r'[{}]', '', content)
                return content.strip()
        except Exception as e:
            logger.error(f"Error extracting RTF content: {e}")
            return ""
    
    # =============================================================================
    # AI SUMMARIZATION
    # =============================================================================
    
    async def generate_file_summary(self, content: str, context_id: int) -> Dict[str, Any]:
        """Generate AI summary of file content"""
        try:
            # Truncate content if too long (OpenAI token limits)
            max_content_length = 8000  # Conservative estimate for token limits
            if len(content) > max_content_length:
                content = content[:max_content_length] + "...[truncated]"
            
            # Create OpenAI service instance
            openai_service = OpenAIService()
            
            # Generate summary
            system_prompt = """You are an expert at creating concise, informative summaries of documents. 
            Create a summary that captures the key points, main topics, and essential information from the document.
            Keep the summary under 200 words but ensure it's comprehensive enough to understand the document's purpose and content."""
            
            result = await openai_service.generate_completion(
                prompt=f"Please summarize the following document:\n\n{content}",
                system_prompt=system_prompt,
                temperature=0.3,
                max_completion_tokens=300
            )
            
            if result.get('success'):
                return {
                    'summary': result['data']['content'],
                    'credits_used': result['data'].get('usage', {}).get('total_tokens', 2)
                }
            else:
                raise Exception(f"OpenAI API error: {result.get('error', 'Unknown error')}")
                
        except Exception as e:
            logger.error(f"Error generating summary: {e}")
            return {
                'summary': f"Auto-generated summary unavailable. Content preview: {content[:200]}...",
                'credits_used': 0
            }
    
    # =============================================================================
    # STORAGE MANAGEMENT
    # =============================================================================
    
    async def get_storage_usage(self, account_id: int, account_type: str) -> Dict[str, Any]:
        """Get current storage usage for an account"""
        usage = self.db.query(models.StorageUsage).filter(
            models.StorageUsage.account_id == account_id,
            models.StorageUsage.account_type == account_type
        ).first()
        
        if not usage:
            return {
                'total_bytes': 0,
                'file_count': 0,
                'account_files_bytes': 0,
                'business_files_bytes': 0
            }
        
        return {
            'total_bytes': usage.total_bytes,
            'file_count': usage.file_count,
            'account_files_bytes': usage.account_files_bytes,
            'business_files_bytes': usage.business_files_bytes
        }
    
    async def _update_storage_usage(
        self, 
        account_id: int, 
        account_type: str, 
        size_delta: int, 
        count_delta: int,
        is_business_file: bool = False
    ):
        """Update storage usage statistics"""
        usage = self.db.query(models.StorageUsage).filter(
            models.StorageUsage.account_id == account_id,
            models.StorageUsage.account_type == account_type
        ).first()
        
        if not usage:
            usage = models.StorageUsage(
                account_id=account_id,
                account_type=account_type,
                total_bytes=0,
                file_count=0,
                account_files_bytes=0,
                business_files_bytes=0
            )
            self.db.add(usage)
        
        # Update totals
        usage.total_bytes += size_delta
        usage.file_count += count_delta
        
        # Update category-specific usage
        if is_business_file:
            usage.business_files_bytes += size_delta
        else:
            usage.account_files_bytes += size_delta
        
        self.db.commit()
    
    async def _get_storage_limit(self, account_id: int, account_type: str) -> int:
        """Get storage limit for an account (in bytes)"""
        # For now, return default. Later this should check subscription tier
        return self.DEFAULT_STORAGE_LIMIT_GB * 1024 * 1024 * 1024
    
    # =============================================================================
    # FILE OPERATIONS
    # =============================================================================
    
    async def get_file(self, file_id: int, user_id: int) -> Optional[models.File]:
        """Get file with access validation"""
        file_record = self.db.query(models.File).filter(
            models.File.id == file_id,
            models.File.is_active == True
        ).first()
        
        if not file_record:
            return None
        
        # Check access permissions
        if not await self._has_file_access(file_record, user_id):
            return None
        
        return file_record
    
    async def _has_file_access(self, file_record: models.File, user_id: int) -> bool:
        """Check if user has access to file"""
        # Check if user uploaded the file
        if file_record.uploaded_by == user_id:
            return True
        
        # Check if user has access to the account/agency
        # This would integrate with your existing auth system
        # For now, simplified check
        return True  # TODO: Implement proper access control
    
    async def delete_file(self, file_id: int, user_id: int) -> bool:
        """Delete a file (soft delete)"""
        file_record = await self.get_file(file_id, user_id)
        if not file_record:
            return False
        
        # Soft delete
        file_record.is_active = False
        
        # Update storage usage
        await self._update_storage_usage(
            file_record.account_id,
            file_record.account_type,
            -file_record.file_size,
            -1,
            file_record.business_id is not None
        )
        
        self.db.commit()
        return True
    
    # =============================================================================
    # FILE SEARCH AND LISTING
    # =============================================================================
    
    async def search_files(
        self,
        account_id: int,
        account_type: str,
        user_id: int,
        business_id: Optional[int] = None,
        search_query: Optional[str] = None,
        file_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[models.File]:
        """Search and filter files"""
        
        query = self.db.query(models.File).filter(
            models.File.account_id == account_id,
            models.File.account_type == account_type,
            models.File.is_active == True
        )
        
        # Filter by business if specified
        if business_id is not None:
            query = query.filter(models.File.business_id == business_id)
        
        # Filter by file type
        if file_type:
            query = query.filter(models.File.file_type == file_type)
        
        # Search in filename, content, or summary
        if search_query:
            search_term = f"%{search_query}%"
            query = query.filter(
                (models.File.original_name.ilike(search_term)) |
                (models.File.content_text.ilike(search_term)) |
                (models.File.summary.ilike(search_term))
            )
        
        # Order by creation date (newest first)
        query = query.order_by(models.File.created_at.desc())
        
        # Apply pagination
        files = query.offset(offset).limit(limit).all()
        
        return files
