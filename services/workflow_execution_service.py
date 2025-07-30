"""
Workflow Execution Service
Handles execution of individual nodes and complete workflows with data persistence
"""

from typing import Any, Dict, List, Optional
from datetime import datetime
import logging
import json
import uuid
import time

from services.dataforseo_service import dataforseo_service
from services.openai_service import openai_service
from services.data_filter_service import data_filter_service

logger = logging.getLogger(__name__)


class WorkflowExecutionService:
    """Service for executing workflow nodes and managing data flow"""
    
    def __init__(self):
        # In-memory storage for node execution results (in production, use Redis or database)
        self.node_execution_results: Dict[str, Dict[str, Any]] = {}
    
    async def execute_node(self, node_id: str, node_type: str, node_config: Dict[str, Any], 
                          input_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Execute a single workflow node
        
        Args:
            node_id: Unique identifier for the node
            node_type: Type of node (seo_serp_analyze, data_filter, etc.)
            node_config: Configuration for the node
            input_data: Data from previous nodes
            
        Returns:
            Standardized execution result
        """
        start_time = time.time()
        execution_id = str(uuid.uuid4())
        
        try:
            logger.info(f"Executing node {node_id} of type {node_type}")
            
            # Route to appropriate execution handler
            if node_type == 'seo_serp_analyze':
                result = await self._execute_serp_node(node_config, input_data)
            elif node_type == 'data_filter':
                result = await self._execute_filter_node(node_config, input_data)
            elif node_type == 'ai_openai_task':
                result = await self._execute_ai_node(node_config, input_data)
            elif node_type == 'content_extract':
                result = await self._execute_content_extract_node(node_config, input_data)
            else:
                raise ValueError(f"Unsupported node type: {node_type}")
            
            execution_time_ms = int((time.time() - start_time) * 1000)
            
            # Create standardized response
            execution_result = {
                'success': True,
                'node_id': node_id,
                'execution_id': execution_id,
                'node_type': node_type,
                'executed_at': datetime.utcnow().isoformat(),
                'execution_time_ms': execution_time_ms,
                'data': {
                    'processed': result.get('processed', result),
                    'raw': result.get('raw', {}),
                    'summary': result.get('summary', {}),
                },
                'credits_used': result.get('credits_used', 1),
                'status': 'success'
            }
            
            # Store result for future variable access
            self.node_execution_results[node_id] = execution_result
            
            logger.info(f"Node {node_id} executed successfully in {execution_time_ms}ms")
            return execution_result
            
        except Exception as e:
            execution_time_ms = int((time.time() - start_time) * 1000)
            error_result = {
                'success': False,
                'node_id': node_id,
                'execution_id': execution_id,
                'node_type': node_type,
                'executed_at': datetime.utcnow().isoformat(),
                'execution_time_ms': execution_time_ms,
                'error': str(e),
                'status': 'failed'
            }
            
            logger.error(f"Node {node_id} execution failed: {e}")
            return error_result
    
    async def _execute_serp_node(self, config: Dict[str, Any], input_data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Execute SERP analysis node"""
        try:
            # Process variables in keyword if input_data is available
            keyword = self._process_variables(config.get('keyword', ''), input_data)
            
            # Submit SERP task with all enhanced parameters
            task_result = dataforseo_service.post_serp_task(
                keyword=keyword,
                location_code=config.get('locationCode', 2840),
                language_code=config.get('languageCode', 'en'),
                device=config.get('device', 'desktop'),
                os=config.get('os'),
                depth=config.get('maxResults', 10),
                target=config.get('target'),
                search_param=config.get('searchParam')
            )
            
            # Process real SERP results or use mock data
            if 'tasks' in task_result and task_result['tasks']:
                # Real API response - process and filter results
                raw_results = task_result['tasks'][0].get('result', [])
                processed_items = []
                
                for result_group in raw_results:
                    items = result_group.get('items', [])
                    
                    for item in items:
                        # Filter based on organicOnly setting
                        if config.get('organicOnly', False):
                            # Only include organic results with domains
                            if (item.get('type') == 'organic' and 
                                item.get('domain') and 
                                item.get('url')):
                                processed_items.append(item)
                        else:
                            # Include all items but prioritize those with domains
                            processed_items.append(item)
                    
                    # Respect depth/maxResults limit
                    max_results = config.get('maxResults', 10)
                    if len(processed_items) >= max_results:
                        processed_items = processed_items[:max_results]
                        break
                
                mock_serp_data = {
                    'results': [{
                        'keyword': keyword,
                        'location_code': config.get('locationCode', 2840),
                        'language_code': config.get('languageCode', 'en'),
                        'total_count': len(processed_items),
                        'items': processed_items
                    }]
                }
            else:
                # Fallback to mock data for testing
                max_results = config.get('maxResults', 10)
                mock_serp_data = {
                    'results': [{
                        'keyword': keyword,
                        'location_code': config.get('locationCode', 2840),
                        'language_code': config.get('languageCode', 'en'),
                        'total_count': max_results,
                        'items': [
                            {
                                'type': 'organic',
                                'title': f'Example Result {i+1} for {keyword}',
                                'url': f'https://example{i+1}.com',
                                'domain': f'example{i+1}.com',
                                'description': f'This is a sample description for result {i+1}',
                                'position': i+1,
                                'rank_absolute': i+1
                            }
                            for i in range(max_results)
                        ]
                    }]
                }
            
            return {
                'processed': mock_serp_data,
                'raw': task_result,
                'summary': {
                    'keyword': keyword,
                    'total_results': len(mock_serp_data['results'][0]['items']),
                    'top_domain': mock_serp_data['results'][0]['items'][0]['domain'] if mock_serp_data['results'][0]['items'] else None
                },
                'credits_used': 1
            }
            
        except Exception as e:
            logger.error(f"SERP node execution failed: {e}")
            raise
    
    async def _execute_filter_node(self, config: Dict[str, Any], input_data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Execute data filter node"""
        try:
            if not input_data:
                raise ValueError("Data filter node requires input data")
            
            # Extract source data using data source path
            data_source = config.get('dataSource', '')
            source_data = self._extract_data_by_path(input_data, data_source)
            
            if not isinstance(source_data, list):
                raise ValueError("Data source must point to an array")
            
            # Apply filtering
            filter_config = {
                'filterProperty': config.get('filterProperty', ''),
                'filterOperation': config.get('filterOperation', 'contains'),
                'filterValue': config.get('filterValue', ''),
                'caseSensitive': config.get('caseSensitive', False),
                'maxResults': config.get('maxResults', 0)
            }
            
            result = data_filter_service.filter_data(source_data, filter_config)
            
            return {
                'processed': result,
                'raw': {'original_data': source_data, 'filter_config': filter_config},
                'summary': {
                    'original_count': result['original_count'],
                    'filtered_count': result['total_filtered'],
                    'filter_operation': f"{filter_config['filterProperty']} {filter_config['filterOperation']} '{filter_config['filterValue']}'"
                },
                'credits_used': 0
            }
            
        except Exception as e:
            logger.error(f"Filter node execution failed: {e}")
            raise
    
    async def _execute_ai_node(self, config: Dict[str, Any], input_data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Execute AI analysis node"""
        try:
            # Process variables in user prompt
            user_prompt = self._process_variables(config.get('userPrompt', ''), input_data)
            
            # Call OpenAI service (this would be implemented based on your OpenAI service)
            # For now, return mock response
            mock_ai_response = {
                'analysis': f'AI analysis of the provided data: {user_prompt[:100]}...',
                'summary': 'This is a mock AI analysis response',
                'confidence': 0.85
            }
            
            return {
                'processed': mock_ai_response,
                'raw': {'prompt': user_prompt, 'model': config.get('modelOverride', 'gpt-4')},
                'summary': {
                    'prompt_length': len(user_prompt),
                    'response_length': len(mock_ai_response['analysis']),
                    'confidence': mock_ai_response['confidence']
                },
                'credits_used': 2
            }
            
        except Exception as e:
            logger.error(f"AI node execution failed: {e}")
            raise
    
    async def _execute_content_extract_node(self, config: Dict[str, Any], input_data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Execute content extraction node"""
        try:
            # Extract URLs from input mapping
            input_mapping = config.get('inputMapping', '')
            urls = self._extract_data_by_path(input_data, input_mapping)
            
            if isinstance(urls, str):
                urls = [urls]
            elif not isinstance(urls, list):
                raise ValueError("Input mapping must point to URL string or array of URLs")
            
            # Mock content extraction
            extracted_content = []
            for i, url in enumerate(urls[:10]):  # Limit to 10 URLs
                extracted_content.append({
                    'url': url,
                    'title': f'Extracted Title {i+1}',
                    'content': f'This is mock extracted content from {url}',
                    'word_count': 250,
                    'extraction_type': config.get('extractionType', 'full_text'),
                    'extracted_at': datetime.utcnow().isoformat()
                })
            
            return {
                'processed': extracted_content,
                'raw': {'urls': urls, 'config': config},
                'summary': {
                    'urls_processed': len(extracted_content),
                    'total_words': sum(item['word_count'] for item in extracted_content),
                    'extraction_type': config.get('extractionType', 'full_text')
                },
                'credits_used': len(extracted_content)
            }
            
        except Exception as e:
            logger.error(f"Content extract node execution failed: {e}")
            raise
    
    def _process_variables(self, text: str, input_data: Optional[Dict[str, Any]]) -> str:
        """Process variables in text using {{path|format}} syntax"""
        if not input_data or not text:
            return text
        
        import re
        
        # Find all variable references
        pattern = r'\{\{([^}]+)\}\}'
        matches = re.findall(pattern, text)
        
        for match in matches:
            try:
                # Parse variable (e.g., "serp_results.results[0].items[*].url|list")
                parts = match.split('|')
                path = parts[0].strip()
                format_type = parts[1].strip() if len(parts) > 1 else 'value'
                
                # Extract data using path
                value = self._extract_data_by_path(input_data, path)
                
                # Apply formatting
                if format_type == 'list' and isinstance(value, list):
                    formatted_value = ', '.join(str(v) for v in value)
                elif format_type == 'json':
                    formatted_value = json.dumps(value)
                else:
                    formatted_value = str(value) if value is not None else ''
                
                # Replace in text
                text = text.replace('{{' + match + '}}', formatted_value)
                
            except Exception as e:
                logger.warning(f"Failed to process variable {match}: {e}")
                # Leave the variable placeholder if processing fails
        
        return text
    
    def _extract_data_by_path(self, data: Dict[str, Any], path: str) -> Any:
        """Extract data using dot notation path (e.g., 'results[0].items[*].url')"""
        if not path:
            return data
        
        try:
            current = data
            parts = path.split('.')
            
            for part in parts:
                if '[' in part and ']' in part:
                    # Handle array access
                    key, bracket_content = part.split('[', 1)
                    index = bracket_content.rstrip(']')
                    
                    if key:
                        current = current[key]
                    
                    if index == '*':
                        # Return all items or extract from all items
                        continue
                    else:
                        current = current[int(index)]
                else:
                    current = current[part]
            
            return current
            
        except (KeyError, IndexError, ValueError, TypeError) as e:
            logger.warning(f"Failed to extract data at path '{path}': {e}")
            return None
    
    def get_node_execution_result(self, node_id: str) -> Optional[Dict[str, Any]]:
        """Get stored execution result for a node"""
        return self.node_execution_results.get(node_id)
    
    def get_all_node_results(self) -> Dict[str, Dict[str, Any]]:
        """Get all stored node execution results"""
        return self.node_execution_results.copy()
    
    def clear_node_results(self):
        """Clear all stored node execution results"""
        self.node_execution_results.clear()
        logger.info("Cleared all node execution results")


# Global service instance
workflow_execution_service = WorkflowExecutionService()