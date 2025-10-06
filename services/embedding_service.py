"""
Embedding Service
Handles vector embeddings generation and semantic search for files and documents
"""

import logging
import tiktoken
from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import text, bindparam
from openai import AsyncOpenAI
import models
from config import settings
from services.credit_service import CreditService

logger = logging.getLogger(__name__)


class EmbeddingService:
    """
    Service for generating and managing vector embeddings for semantic search
    Supports both file-level and chunk-level embeddings with business isolation
    
    VERSION: 2.3.0 - Add aggressive debug logging (2025-10-06)
    """
    
    # Embedding configuration
    EMBEDDING_MODEL = "text-embedding-3-small"  # $0.02 per 1M tokens (cheaper, fast)
    EMBEDDING_DIMENSIONS = 1536
    
    # Chunking configuration for large documents
    CHUNK_SIZE = 1000  # tokens per chunk
    CHUNK_OVERLAP = 200  # token overlap between chunks
    
    # Default search parameters (user can override)
    DEFAULT_TOP_K = 5
    DEFAULT_SIMILARITY_THRESHOLD = 0.7
    DEFAULT_MAX_CONTEXT_TOKENS = 4000
    
    def __init__(self, db: Session):
        self.db = db
        self.credit_service = CreditService(db)
        self.encoding = tiktoken.get_encoding("cl100k_base")  # For token counting
    
    # =========================================================================
    # EMBEDDING GENERATION
    # =========================================================================
    
    async def generate_file_embeddings(
        self, 
        file_id: int,
        business_id: Optional[int],
        account_id: int,
        account_type: str,
        force_regenerate: bool = False
    ) -> Dict[str, Any]:
        """
        Generate embeddings for a file
        Automatically chunks large documents
        
        Args:
            file_id: ID of file to embed
            business_id: Business context for API key and credits
            account_id: Account ID for API key lookup
            account_type: 'user' or 'agency'
            force_regenerate: Regenerate even if embeddings exist
            
        Returns:
            Dict with generation results and credits used
        """
        # Get file
        file = self.db.query(models.File).filter(models.File.id == file_id).first()
        if not file:
            raise ValueError(f"File not found: {file_id}")
        
        # Check if already embedded
        if not force_regenerate and file.embedding_status == 'completed':
            logger.info(f"File {file_id} already has embeddings, skipping")
            chunk_count = self.db.query(models.DocumentChunk).filter(
                models.DocumentChunk.file_id == file_id
            ).count()
            return {
                'success': True,
                'file_id': file_id,
                'file_name': file.original_name,
                'message': 'Embeddings already exist',
                'skipped': True,
                'summary_embedded': file.summary_embedding is not None,
                'content_embedded': file.content_embedding is not None,
                'chunks_created': chunk_count,
                'chunks_embedded': chunk_count,
                'total_tokens_used': 0,
                'credits_used': 0,
                'embedding_model': file.embedding_model
            }
        
        # Update status
        file.embedding_status = 'processing'
        self.db.commit()
        
        try:
            # Get OpenAI API key
            api_key = self._get_openai_api_key(business_id, account_id, account_type)
            if not api_key:
                file.embedding_status = 'failed'
                self.db.commit()
                raise ValueError("OpenAI API key not configured")
            
            client = AsyncOpenAI(api_key=api_key)
            
            results = {
                'success': True,
                'file_id': file_id,
                'file_name': file.original_name,
                'skipped': False,
                'summary_embedded': False,
                'content_embedded': False,
                'chunks_created': 0,
                'chunks_embedded': 0,
                'total_tokens_used': 0,
                'credits_used': 0,
                'embedding_model': self.EMBEDDING_MODEL
            }
            
            # 1. Generate embedding for summary (fast search)
            if file.summary and file.summary.strip() and "Auto-generated summary unavailable" not in file.summary:
                logger.info(f"Generating summary embedding for file {file_id}")
                summary_response = await client.embeddings.create(
                    model=self.EMBEDDING_MODEL,
                    input=file.summary
                )
                file.summary_embedding = summary_response.data[0].embedding
                results['summary_embedded'] = True
                results['total_tokens_used'] += summary_response.usage.total_tokens
            elif file.content_text and file.content_text.strip():
                # Fallback: If summary is unavailable, use first 1000 chars of content
                logger.warning(f"Summary unavailable for file {file_id}, using content preview for summary embedding")
                content_preview = file.content_text[:1000]
                summary_response = await client.embeddings.create(
                    model=self.EMBEDDING_MODEL,
                    input=content_preview
                )
                file.summary_embedding = summary_response.data[0].embedding
                results['summary_embedded'] = True
                results['total_tokens_used'] += summary_response.usage.total_tokens
            
            # 2. Process content - ALWAYS create chunks for semantic search
            if file.content_text and file.content_text.strip():
                content_tokens = len(self.encoding.encode(file.content_text))
                
                # Always create chunks (even for small docs) for better search accuracy
                logger.info(f"Chunking and embedding file {file_id} ({content_tokens} tokens)")
                chunks = self._chunk_text(file.content_text)
                
                # Delete existing chunks if regenerating
                if force_regenerate:
                    self.db.query(models.DocumentChunk).filter(
                        models.DocumentChunk.file_id == file_id
                    ).delete()
                
                # If document is very small and results in only 1 chunk, also store full content embedding
                if len(chunks) == 1:
                    logger.info(f"Single chunk detected, also storing content_embedding")
                    content_response = await client.embeddings.create(
                        model=self.EMBEDDING_MODEL,
                        input=file.content_text
                    )
                    file.content_embedding = content_response.data[0].embedding
                    results['content_embedded'] = True
                    results['total_tokens_used'] += content_response.usage.total_tokens
                
                # Create and embed all chunks
                for i, chunk_text in enumerate(chunks):
                    chunk_response = await client.embeddings.create(
                        model=self.EMBEDDING_MODEL,
                        input=chunk_text
                    )
                    
                    chunk = models.DocumentChunk(
                        file_id=file.id,
                        business_id=business_id,
                        chunk_index=i,
                        chunk_text=chunk_text,
                        chunk_embedding=chunk_response.data[0].embedding,
                        chunk_metadata={
                            'total_chunks': len(chunks),
                            'token_count': len(self.encoding.encode(chunk_text))
                        }
                    )
                    self.db.add(chunk)
                    results['total_tokens_used'] += chunk_response.usage.total_tokens
                
                results['chunks_created'] = len(chunks)
                results['chunks_embedded'] = len(chunks)
            
            # Update file metadata
            file.embedding_model = self.EMBEDDING_MODEL
            file.embedding_credits_used = results['total_tokens_used']
            file.embedding_status = 'completed'
            
            self.db.commit()
            
            # Track credits
            results['credits_used'] = results['total_tokens_used']
            if business_id and account_id:
                # Get credit pool for the user/account
                credit_pool = self.db.query(models.CreditPool).filter_by(owner_id=account_id).first()
                if credit_pool:
                    self.credit_service.deduct_credits(
                        pool_id=credit_pool.id,
                        amount=results['credits_used'],
                        description=f"Vector embeddings for: {file.original_name}",
                        business_id=business_id
                    )
            
            logger.info(f"Successfully generated embeddings for file {file_id}: {results}")
            return results
            
        except Exception as e:
            logger.error(f"Failed to generate embeddings for file {file_id}: {str(e)}")
            file.embedding_status = 'failed'
            self.db.commit()
            raise
    
    # =========================================================================
    # SEMANTIC SEARCH
    # =========================================================================
    
    async def search_files(
        self,
        query: str,
        business_id: Optional[int],
        account_id: int,
        account_type: str,
        top_k: int = DEFAULT_TOP_K,
        similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
        file_types: Optional[List[str]] = None,
        search_content: bool = False,
        business_ids: Optional[List[int]] = None
    ) -> List[Dict[str, Any]]:
        """
        Semantic search across files for a business
        
        VERSION CHECK: This is EmbeddingService v2.0.0 with fixed SQL parameter binding
        
        Args:
            query: Search query text
            business_id: Business to search within
            account_id: Account ID for API key
            account_type: Account type
            top_k: Number of results to return
            similarity_threshold: Minimum similarity score (0-1)
            file_types: Optional filter by file types (e.g., ['pdf', 'docx'])
            search_content: If True, search full content; if False, search summaries (faster)
            
        Returns:
            List of matching files with similarity scores
        """
        # CRITICAL DEBUG: This MUST appear in logs if new code is running
        print("=" * 80)
        print("🚨 EMBEDDING SERVICE VERSION 2.3.0 - SEARCH_FILES METHOD CALLED")
        print("=" * 80)
        logger.info("🔍 EmbeddingService.search_files() - VERSION 2.2.0 (Vector embedded directly in SQL)")
        
        # DEBUG: Check how many files have embeddings
        embedding_column = 'content_embedding' if search_content else 'summary_embedding'
        total_files = self.db.query(models.File).filter(
            models.File.business_id == business_id,
            models.File.is_active == True
        ).count()
        files_with_embeddings = self.db.query(models.File).filter(
            models.File.business_id == business_id,
            models.File.is_active == True,
            getattr(models.File, embedding_column).isnot(None)
        ).count()
        print("=" * 80)
        print(f"📊 Business {business_id} has {files_with_embeddings}/{total_files} files with {embedding_column}")
        print("=" * 80)
        logger.info(f"📊 Business {business_id} has {files_with_embeddings}/{total_files} files with {embedding_column}")
        
        # Generate query embedding
        api_key = self._get_openai_api_key(business_id, account_id, account_type)
        if not api_key:
            raise ValueError("OpenAI API key not configured")
        
        client = AsyncOpenAI(api_key=api_key)
        query_response = await client.embeddings.create(
            model=self.EMBEDDING_MODEL,
            input=query
        )
        query_embedding = query_response.data[0].embedding
        
        # Build search query
        embedding_column = 'content_embedding' if search_content else 'summary_embedding'
        
        # Convert embedding list to PostgreSQL array literal format
        # We embed this directly in SQL (not as a parameter) because vector type needs special handling
        import json
        embedding_array_str = json.dumps(query_embedding)
        
        # Build SQL query parts - embed vector directly, use :param for other values
        select_clause = f"SELECT f.id, f.original_name, f.file_type, f.file_size, f.summary, f.created_at, 1 - (f.{embedding_column} <=> '{embedding_array_str}'::vector) as similarity"
        from_clause = "FROM files f"
        where_parts = [
            f"f.{embedding_column} IS NOT NULL",
            "f.is_active = true",
            f"1 - (f.{embedding_column} <=> '{embedding_array_str}'::vector) >= :threshold"
        ]
        
        # Initialize parameters (no query_embedding - it's embedded directly)
        params = {
            'threshold': similarity_threshold,
            'limit': top_k
        }
        
        # Add business filter - single or multiple businesses
        if business_ids:
            # Cross-business search
            placeholders = ','.join([f":business_id_{i}" for i in range(len(business_ids))])
            where_parts.append(f"f.business_id IN ({placeholders})")
            for i, bid in enumerate(business_ids):
                params[f'business_id_{i}'] = bid
        elif business_id:
            # Single business search
            where_parts.append("f.business_id = :business_id")
            params['business_id'] = business_id
        
        # Add file type filter if specified
        if file_types:
            placeholders = ','.join([f":file_type_{i}" for i in range(len(file_types))])
            where_parts.append(f"f.file_type IN ({placeholders})")
            for i, ft in enumerate(file_types):
                params[f'file_type_{i}'] = ft
        
        # Build complete query
        where_clause = "WHERE " + " AND ".join(where_parts)
        order_clause = f"ORDER BY f.{embedding_column} <=> '{embedding_array_str}'::vector"
        limit_clause = "LIMIT :limit"
        
        sql_query = f"{select_clause} {from_clause} {where_clause} {order_clause} {limit_clause}"
        
        # CRITICAL DEBUG: Show actual SQL being generated
        print("=" * 80)
        print("🔍 SQL QUERY GENERATED:")
        print(sql_query)
        print("🔍 PARAMETERS:")
        print(params)
        print("=" * 80)
        
        # Log the query for debugging
        logger.info(f"🔍 Executing semantic search query")
        logger.info(f"📊 SQL Query: {sql_query}")
        logger.info(f"📊 Parameters: {list(params.keys())}")
        
        # Execute using text() with :param style binding
        from sqlalchemy import text
        result = self.db.execute(text(sql_query), params)
        rows = result.fetchall()
        
        # Format results
        results = [
            {
                'file_id': row[0],
                'filename': row[1],
                'file_type': row[2],
                'file_size': row[3],
                'summary': row[4],
                'created_at': row[5].isoformat() if row[5] else None,
                'similarity': float(row[6])
            }
            for row in rows
        ]
        
        logger.info(f"🔍 Search query '{query}' returned {len(results)} results for business {business_id}")
        if results:
            logger.info(f"📄 Top result: {results[0]['filename']} (similarity: {results[0]['similarity']:.3f})")
        else:
            logger.warning(f"⚠️ No results found. Query: '{query}', Business: {business_id}, Threshold: {similarity_threshold}")
        return results
    
    async def search_chunks(
        self,
        query: str,
        business_id: int,
        account_id: int,
        account_type: str,
        top_k: int = 10,
        similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
        file_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Semantic search across document chunks
        Useful for finding specific passages in large documents
        
        Args:
            query: Search query
            business_id: Business context
            account_id: Account ID for API key
            account_type: Account type
            top_k: Number of chunks to return
            similarity_threshold: Minimum similarity
            file_id: Optional - search only within specific file
            
        Returns:
            List of matching chunks with context
        """
        # Generate query embedding
        api_key = self._get_openai_api_key(business_id, account_id, account_type)
        client = AsyncOpenAI(api_key=api_key)
        
        query_response = await client.embeddings.create(
            model=self.EMBEDDING_MODEL,
            input=query
        )
        query_embedding = query_response.data[0].embedding
        
        # Convert embedding to PostgreSQL array literal format
        # We embed this directly in SQL (not as a parameter) because vector type needs special handling
        import json
        embedding_array_str = json.dumps(query_embedding)
        
        # Build query parts - embed vector directly, use :param for other values
        select_clause = f"SELECT c.id, c.file_id, c.chunk_text, c.chunk_index, c.chunk_metadata, f.original_name, 1 - (c.chunk_embedding <=> '{embedding_array_str}'::vector) as similarity"
        from_clause = "FROM document_chunks c JOIN files f ON f.id = c.file_id"
        where_parts = [
            "c.business_id = :business_id",
            "c.chunk_embedding IS NOT NULL",
            f"1 - (c.chunk_embedding <=> '{embedding_array_str}'::vector) >= :threshold"
        ]
        
        params = {
            'business_id': business_id,
            'threshold': similarity_threshold,
            'limit': top_k
        }
        
        if file_id:
            where_parts.append("c.file_id = :file_id")
            params['file_id'] = file_id
        
        # Build complete query
        where_clause = "WHERE " + " AND ".join(where_parts)
        order_clause = f"ORDER BY c.chunk_embedding <=> '{embedding_array_str}'::vector"
        limit_clause = "LIMIT :limit"
        
        sql_query = f"{select_clause} {from_clause} {where_clause} {order_clause} {limit_clause}"
        
        # Execute using text() with :param style binding
        from sqlalchemy import text
        result = self.db.execute(text(sql_query), params)
        rows = result.fetchall()
        
        results = [
            {
                'chunk_id': row[0],
                'file_id': row[1],
                'chunk_text': row[2],
                'chunk_index': row[3],
                'chunk_metadata': row[4],
                'filename': row[5],
                'similarity': float(row[6])
            }
            for row in rows
        ]
        
        return results
    
    # =========================================================================
    # CONTEXT RETRIEVAL FOR WORKFLOWS
    # =========================================================================
    
    async def get_context_for_workflow(
        self,
        query: str,
        business_id: Optional[int],
        account_id: int,
        account_type: str,
        max_tokens: int = DEFAULT_MAX_CONTEXT_TOKENS,
        top_k: int = 10,
        similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
        include_sources: bool = True,
        business_ids: Optional[List[int]] = None
    ) -> Dict[str, Any]:
        """
        Get relevant document context for workflow node injection
        Automatically aggregates and formats content within token budget
        
        Args:
            query: Context query (e.g., "information about pricing strategy")
            business_id: Business context
            account_id: Account ID
            account_type: Account type
            max_tokens: Maximum tokens for context
            top_k: Number of documents to consider
            similarity_threshold: Minimum relevance
            include_sources: Include source file references
            
        Returns:
            Dict with formatted context and metadata
        """
        # STRATEGY: Always search chunks for detailed content matching
        # Chunks provide more accurate context than summaries
        logger.info(f"🔍 Searching chunks with top_k={top_k * 2}, threshold={similarity_threshold}")
        chunk_results = await self.search_chunks(
            query=query,
            business_id=business_id,
            account_id=account_id,
            account_type=account_type,
            top_k=top_k * 2,  # Get more chunks for better coverage
            similarity_threshold=similarity_threshold
        )
        
        context_parts = []
        current_tokens = 0
        sources = []
        sources_set = set()  # Track unique sources
        
        # Use chunks if available
        if chunk_results:
            logger.info(f"✅ Found {len(chunk_results)} chunk results")
            
            for chunk in chunk_results:
                chunk_tokens = len(self.encoding.encode(chunk['chunk_text']))
                
                if current_tokens + chunk_tokens > max_tokens:
                    logger.info(f"⚠️ Reached token limit: {current_tokens}/{max_tokens}")
                    break
                
                # Add chunk text with file context
                chunk_context = f"[From: {chunk['filename']}]\n{chunk['chunk_text']}"
                context_parts.append(chunk_context)
                current_tokens += chunk_tokens
                
                # Track unique source files
                if include_sources and chunk['filename'] not in sources_set:
                    sources_set.add(chunk['filename'])
                    sources.append({
                        'file_id': chunk['file_id'],
                        'filename': chunk['filename'],
                        'similarity': chunk['similarity']
                    })
            
            context = "\n\n---\n\n".join(context_parts)
            logger.info(f"📝 Built context from {len(context_parts)} chunks, {current_tokens} tokens, {len(sources)} unique files")
        else:
            logger.warning(f"⚠️ No chunk results found, returning empty context")
            context = ""
        
        return {
            'context': context,
            'token_count': current_tokens,
            'sources': sources if include_sources else [],
            'query': query,
            'results_used': len(context_parts)
        }
    
    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
    def _chunk_text(self, text: str) -> List[str]:
        """
        Split text into overlapping chunks based on token count
        
        Args:
            text: Text to chunk
            
        Returns:
            List of text chunks
        """
        tokens = self.encoding.encode(text)
        chunks = []
        
        start = 0
        while start < len(tokens):
            end = start + self.CHUNK_SIZE
            chunk_tokens = tokens[start:end]
            chunk_text = self.encoding.decode(chunk_tokens)
            chunks.append(chunk_text)
            
            # Move forward with overlap
            start += (self.CHUNK_SIZE - self.CHUNK_OVERLAP)
        
        return chunks if chunks else [text]
    
    def _get_openai_api_key(
        self, 
        business_id: Optional[int],
        account_id: int,
        account_type: str
    ) -> Optional[str]:
        """
        Get OpenAI API key from integrations with priority:
        1. Business-level integration
        2. Agency-level integration  
        3. System-level integration (admin configured)
        4. Global settings fallback
        """
        try:
            # Try business integration first
            if business_id:
                business_integration = self.db.query(models.BusinessIntegration).filter(
                    models.BusinessIntegration.business_id == business_id,
                    models.BusinessIntegration.is_active == True
                ).join(models.Integration).filter(
                    models.Integration.name == "OpenAI",
                    models.Integration.is_active == True
                ).first()
                
                if business_integration and business_integration.credentials:
                    api_key = business_integration.credentials.get('api_key')
                    if api_key:
                        logger.info(f"✅ Using business-level OpenAI API key for business {business_id}")
                        return api_key
            
            # Try agency integration
            if account_type == 'agency':
                agency_integration = self.db.query(models.AgencyIntegration).filter(
                    models.AgencyIntegration.agency_id == account_id,
                    models.AgencyIntegration.is_active == True
                ).join(models.Integration).filter(
                    models.Integration.name == "OpenAI",
                    models.Integration.is_active == True
                ).first()
                
                if agency_integration and agency_integration.credentials:
                    api_key = agency_integration.credentials.get('api_key')
                    if api_key:
                        logger.info(f"✅ Using agency-level OpenAI API key for agency {account_id}")
                        return api_key
            
            # Try system-level integration (admin configured)
            logger.info("🔍 Checking for system-level OpenAI integration...")
            system_integration = self.db.query(models.SystemIntegration).join(
                models.Integration
            ).filter(
                models.Integration.provider == "openai",
                models.SystemIntegration.is_active == True,
                models.Integration.is_active == True
            ).first()
            
            if system_integration and system_integration.credentials:
                credentials = system_integration.credentials
                if isinstance(credentials, str):
                    import json
                    credentials = json.loads(credentials)
                api_key = credentials.get("api_key")
                if api_key:
                    logger.info("✅ Using system-level OpenAI API key")
                    return api_key
            
            # Fallback to global settings
            logger.warning("⚠️ No integration found, falling back to environment variable")
            return settings.OPENAI_API_KEY if hasattr(settings, 'OPENAI_API_KEY') else None
            
        except Exception as e:
            logger.error(f"❌ Error getting OpenAI API key: {str(e)}")
            return settings.OPENAI_API_KEY if hasattr(settings, 'OPENAI_API_KEY') else None

