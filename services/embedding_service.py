"""
Embedding Service
Handles vector embeddings generation and semantic search for files and documents
"""

import logging
import tiktoken
from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import text
from openai import AsyncOpenAI
import models
from config import settings
from services.credit_service import CreditService

logger = logging.getLogger(__name__)


class EmbeddingService:
    """
    Service for generating and managing vector embeddings for semantic search
    Supports both file-level and chunk-level embeddings with business isolation
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
            if file.summary and file.summary.strip():
                logger.info(f"Generating summary embedding for file {file_id}")
                summary_response = await client.embeddings.create(
                    model=self.EMBEDDING_MODEL,
                    input=file.summary
                )
                file.summary_embedding = summary_response.data[0].embedding
                results['summary_embedded'] = True
                results['total_tokens_used'] += summary_response.usage.total_tokens
            
            # 2. Process content
            if file.content_text and file.content_text.strip():
                content_tokens = len(self.encoding.encode(file.content_text))
                
                if content_tokens <= self.CHUNK_SIZE:
                    # Small document - single embedding
                    logger.info(f"Generating content embedding for file {file_id} ({content_tokens} tokens)")
                    content_response = await client.embeddings.create(
                        model=self.EMBEDDING_MODEL,
                        input=file.content_text
                    )
                    file.content_embedding = content_response.data[0].embedding
                    results['content_embedded'] = True
                    results['total_tokens_used'] += content_response.usage.total_tokens
                else:
                    # Large document - create chunks
                    logger.info(f"Chunking and embedding file {file_id} ({content_tokens} tokens)")
                    chunks = self._chunk_text(file.content_text)
                    
                    # Delete existing chunks if regenerating
                    if force_regenerate:
                        self.db.query(models.DocumentChunk).filter(
                            models.DocumentChunk.file_id == file_id
                        ).delete()
                    
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
        
        # Convert embedding list to PostgreSQL array format
        import json
        embedding_str = json.dumps(query_embedding)
        
        sql_query = f"""
        SELECT 
            f.id,
            f.original_name,
            f.file_type,
            f.file_size,
            f.summary,
            f.created_at,
            1 - (f.{embedding_column} <=> :query_embedding::vector) as similarity
        FROM files f
        WHERE 
            f.{embedding_column} IS NOT NULL
            AND f.is_active = true
            AND 1 - (f.{embedding_column} <=> :query_embedding::vector) >= :threshold
        """
        
        # Add business filter - single or multiple businesses
        params = {
            'query_embedding': embedding_str,
            'threshold': similarity_threshold,
            'limit': top_k
        }
        
        if business_ids:
            # Cross-business search
            placeholders = ','.join([f":business_id_{i}" for i in range(len(business_ids))])
            sql_query += f" AND f.business_id IN ({placeholders})"
            for i, bid in enumerate(business_ids):
                params[f'business_id_{i}'] = bid
        elif business_id:
            # Single business search
            sql_query += " AND f.business_id = :business_id"
            params['business_id'] = business_id
        
        # Add file type filter if specified
        if file_types:
            placeholders = ','.join([f":file_type_{i}" for i in range(len(file_types))])
            sql_query += f" AND f.file_type IN ({placeholders})"
            for i, ft in enumerate(file_types):
                params[f'file_type_{i}'] = ft
        
        sql_query += f"""
        ORDER BY f.{embedding_column} <=> :query_embedding::vector
        LIMIT :limit
        """
        
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
        
        logger.info(f"Search query '{query}' returned {len(results)} results for business {business_id}")
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
        
        # Convert embedding to PostgreSQL array format
        import json
        embedding_str = json.dumps(query_embedding)
        
        # Build query
        sql_query = """
        SELECT 
            c.id,
            c.file_id,
            c.chunk_text,
            c.chunk_index,
            c.chunk_metadata,
            f.original_name,
            1 - (c.chunk_embedding <=> :query_embedding::vector) as similarity
        FROM document_chunks c
        JOIN files f ON f.id = c.file_id
        WHERE 
            c.business_id = :business_id
            AND c.chunk_embedding IS NOT NULL
            AND 1 - (c.chunk_embedding <=> :query_embedding::vector) >= :threshold
        """
        
        if file_id:
            sql_query += " AND c.file_id = :file_id"
        
        sql_query += """
        ORDER BY c.chunk_embedding <=> :query_embedding::vector
        LIMIT :limit
        """
        
        params = {
            'query_embedding': embedding_str,
            'business_id': business_id,
            'threshold': similarity_threshold,
            'limit': top_k
        }
        
        if file_id:
            params['file_id'] = file_id
        
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
        # Search files first (faster)
        file_results = await self.search_files(
            query=query,
            business_id=business_id,
            account_id=account_id,
            account_type=account_type,
            top_k=top_k,
            similarity_threshold=similarity_threshold,
            search_content=False,  # Use summaries for speed
            business_ids=business_ids  # Pass business_ids for cross-business search
        )
        
        # If no file results, try chunks
        if not file_results:
            chunk_results = await self.search_chunks(
                query=query,
                business_id=business_id,
                account_id=account_id,
                account_type=account_type,
                top_k=top_k,
                similarity_threshold=similarity_threshold
            )
            
            # Format chunk results
            context_parts = []
            current_tokens = 0
            sources = []
            
            for chunk in chunk_results:
                chunk_tokens = len(self.encoding.encode(chunk['chunk_text']))
                
                if current_tokens + chunk_tokens > max_tokens:
                    break
                
                context_parts.append(chunk['chunk_text'])
                current_tokens += chunk_tokens
                
                if include_sources and chunk['filename'] not in sources:
                    sources.append(chunk['filename'])
            
            context = "\n\n---\n\n".join(context_parts)
            
        else:
            # Use file summaries
            context_parts = []
            current_tokens = 0
            sources = []
            
            for file_result in file_results:
                if not file_result['summary']:
                    continue
                
                summary_tokens = len(self.encoding.encode(file_result['summary']))
                
                if current_tokens + summary_tokens > max_tokens:
                    break
                
                file_context = f"[{file_result['filename']}]\n{file_result['summary']}"
                context_parts.append(file_context)
                current_tokens += summary_tokens
                
                if include_sources:
                    sources.append({
                        'file_id': file_result['file_id'],
                        'filename': file_result['filename'],
                        'similarity': file_result['similarity']
                    })
            
            context = "\n\n---\n\n".join(context_parts)
        
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

