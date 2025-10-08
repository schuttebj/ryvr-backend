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
            elif node_type == 'review':
                result = await self._execute_review_node(node_config, input_data)
            elif node_type == 'options':
                result = await self._execute_options_node(node_config, input_data)
            elif node_type == 'conditional':
                result = await self._execute_conditional_node(node_config, input_data)
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
            urls = []
            
            # Primary: Try urlSource (new format) - supports variables like {{node.path}}
            url_source = config.get('urlSource', '')
            if url_source:
                logger.info(f"Processing urlSource: {url_source}")
                
                # Process variables in the URL source using {{variable}} syntax
                processed_url_source = self._process_variables(url_source, input_data)
                logger.info(f"Processed urlSource result: {processed_url_source}")
                
                # Parse the processed result to extract URLs
                if processed_url_source:
                    # Check if result contains actual URLs
                    if 'http' in processed_url_source:
                        # Extract URLs using regex
                        import re
                        # First, try to extract URLs directly (handles any format)
                        url_matches = re.findall(r'https?://[^\s+,\n\r\t]+', processed_url_source)
                        if url_matches:
                            urls = url_matches
                        else:
                            # Try splitting by common delimiters including ' + ' (space-plus-space from variable system)
                            # Split on: comma, newline, tab, or ' + ' (the new variable separator)
                            urls = [
                                url.strip() 
                                for url in re.split(r'\s*[,+\n\r\t]\s*|\s+\+\s+', processed_url_source)
                                if url.strip() and 'http' in url
                            ]
                    else:
                        # The variable didn't resolve - try as a direct path
                        # Remove {{ }} if present and try direct path extraction
                        clean_path = url_source.replace('{{', '').replace('}}', '').strip()
                        if '|' in clean_path:
                            clean_path = clean_path.split('|')[0].strip()
                        
                        resolved_data = self._extract_data_by_path(input_data, clean_path)
                        logger.info(f"Resolved data from path: {type(resolved_data)}")
                        
                        if isinstance(resolved_data, list):
                            urls = [url for url in resolved_data if url and isinstance(url, str) and 'http' in url]
                        elif isinstance(resolved_data, str) and 'http' in resolved_data:
                            urls = [resolved_data]
            
            # Fallback: Try legacy inputMapping (old format) - direct path without {{}}
            if not urls:
                input_mapping = config.get('inputMapping', '')
                if input_mapping:
                    logger.info(f"Falling back to inputMapping: {input_mapping}")
                    resolved_data = self._extract_data_by_path(input_data, input_mapping)
                    
                    if isinstance(resolved_data, str):
                        urls = [resolved_data]
                    elif isinstance(resolved_data, list):
                        urls = resolved_data if resolved_data else []
                    else:
                        logger.warning(f"Input mapping resolved to unexpected type: {type(resolved_data)}")
            
            # Validate we have URLs
            if not urls:
                logger.error("No URLs found to extract content from")
                logger.error(f"Config: urlSource={config.get('urlSource')}, inputMapping={config.get('inputMapping')}")
                logger.error(f"Available input_data keys: {list(input_data.keys()) if input_data else 'None'}")
                raise ValueError("No URLs found to extract content from. Check your URL source configuration.")
            
            # Apply maxUrls limit
            max_urls = config.get('maxUrls', 10)
            urls = urls[:max_urls]
            
            logger.info(f"Extracted {len(urls)} URLs for content extraction")
            
            # Mock content extraction
            extracted_content = []
            for i, url in enumerate(urls):
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
                    'total_urls_found': len(urls),
                    'total_words': sum(item['word_count'] for item in extracted_content),
                    'extraction_type': config.get('extractionType', 'full_text')
                },
                'credits_used': len(extracted_content)
            }
            
        except Exception as e:
            logger.error(f"Content extract node execution failed: {e}")
            logger.exception("Full traceback:")
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
                    # Join array items with comma-space (matches frontend behavior)
                    # Handle array of objects by extracting useful properties
                    list_items = []
                    for item in value:
                        if isinstance(item, dict):
                            # Try common properties that make sense for lists
                            extracted = (item.get('url') or item.get('title') or item.get('name') or 
                                       item.get('domain') or item.get('keyword') or json.dumps(item))
                            list_items.append(str(extracted))
                        else:
                            list_items.append(str(item))
                    formatted_value = ', '.join(list_items)
                elif format_type == 'json':
                    formatted_value = json.dumps(value)
                elif format_type == 'count':
                    formatted_value = str(len(value)) if isinstance(value, list) else '1'
                elif format_type == 'first':
                    formatted_value = str(value[0]) if isinstance(value, list) and len(value) > 0 else str(value) if value else ''
                elif format_type == 'last':
                    formatted_value = str(value[-1]) if isinstance(value, list) and len(value) > 0 else str(value) if value else ''
                elif format_type.startswith('range:'):
                    # Handle range format like "range:0-4"
                    if isinstance(value, list):
                        range_match = re.match(r'range:(\d+)-(\d+)', format_type)
                        if range_match:
                            start = int(range_match.group(1))
                            end = int(range_match.group(2))
                            range_slice = value[start:end+1]
                            # Handle array of objects by extracting useful properties
                            range_items = []
                            for item in range_slice:
                                if isinstance(item, dict):
                                    extracted = (item.get('url') or item.get('title') or item.get('name') or 
                                               item.get('domain') or item.get('keyword') or json.dumps(item))
                                    range_items.append(str(extracted))
                                else:
                                    range_items.append(str(item))
                            formatted_value = ', '.join(range_items)
                        else:
                            formatted_value = ', '.join(str(v) for v in value)
                    else:
                        formatted_value = str(value) if value is not None else ''
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
            
            for i, part in enumerate(parts):
                if '[' in part and ']' in part:
                    # Handle array access with brackets: items[0] or items[*]
                    key, bracket_content = part.split('[', 1)
                    index = bracket_content.rstrip(']')
                    
                    # Get the array first if there's a key
                    if key:
                        current = current[key]
                    
                    if index == '*':
                        # Array wildcard - extract remaining path from each item
                        if not isinstance(current, list):
                            logger.warning(f"Expected list for wildcard access at '{part}', got {type(current)}")
                            return None
                        
                        # If there are more parts after this wildcard, recursively extract from each item
                        remaining_parts = parts[i+1:]
                        if remaining_parts:
                            remaining_path = '.'.join(remaining_parts)
                            results = []
                            for item in current:
                                # Recursively extract from each item
                                sub_result = self._extract_data_by_path(item, remaining_path)
                                if sub_result is not None:
                                    # If the sub_result is a list, extend; otherwise append
                                    if isinstance(sub_result, list):
                                        results.extend(sub_result)
                                    else:
                                        results.append(sub_result)
                            return results
                        else:
                            # No more parts, return the entire array
                            return current
                    else:
                        # Specific index access
                        current = current[int(index)]
                elif part.isdigit():
                    # Handle numeric index in dot notation: items.0 (treat as array index)
                    if isinstance(current, list):
                        current = current[int(part)]
                    elif isinstance(current, dict) and part in current:
                        # Could be a dict key that happens to be numeric
                        current = current[part]
                    else:
                        logger.warning(f"Cannot access index {part} on {type(current)}")
                        return None
                else:
                    # Simple key access
                    current = current[part]
            
            return current
            
        except (KeyError, IndexError, ValueError, TypeError) as e:
            logger.warning(f"Failed to extract data at path '{path}': {e}")
            logger.debug(f"Current data type: {type(data)}, Path: {path}")
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
    
    async def _execute_review_node(self, config: Dict[str, Any], input_data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Execute review node - pauses workflow for human review
        Note: Actual pausing is handled by FlowControlService in the workflow execution flow
        """
        try:
            # Review node returns a marker that indicates workflow should pause
            return {
                'processed': {
                    'action': 'pause_for_review',
                    'reviewer_type': config.get('reviewerType', 'agency'),
                    'editable_nodes': config.get('editableNodes', []),
                    'editable_fields': config.get('editableFields', {}),
                    'approved_path': config.get('approvedPath'),
                    'declined_path': config.get('declinedPath')
                },
                'raw': config,
                'summary': {
                    'node_type': 'review',
                    'reviewer_type': config.get('reviewerType', 'agency'),
                    'editable_count': len(config.get('editableNodes', []))
                },
                'credits_used': 0
            }
        except Exception as e:
            logger.error(f"Review node execution failed: {e}")
            raise
    
    async def _execute_options_node(self, config: Dict[str, Any], input_data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Execute options node - pauses workflow for user option selection
        Note: Actual pausing is handled by FlowControlService in the workflow execution flow
        """
        try:
            # Extract available options from input data
            data_source = config.get('dataSource', '')
            available_options = self._extract_data_by_path(input_data, data_source) if input_data else []
            
            if not isinstance(available_options, list):
                if isinstance(available_options, dict):
                    available_options = [available_options]
                else:
                    available_options = []
            
            # Options node returns a marker that indicates workflow should pause
            return {
                'processed': {
                    'action': 'pause_for_options',
                    'available_options': available_options,
                    'selection_mode': config.get('selectionMode', 'single'),
                    'option_label_field': config.get('optionLabelField'),
                    'option_value_field': config.get('optionValueField'),
                    'output_variable': config.get('outputVariable', 'selected_options')
                },
                'raw': config,
                'summary': {
                    'node_type': 'options',
                    'options_count': len(available_options),
                    'selection_mode': config.get('selectionMode', 'single')
                },
                'credits_used': 0
            }
        except Exception as e:
            logger.error(f"Options node execution failed: {e}")
            raise
    
    async def _execute_conditional_node(self, config: Dict[str, Any], input_data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Execute conditional node - evaluates conditions and determines path
        Note: Path determination is handled by FlowControlService
        """
        try:
            conditions = config.get('conditions', [])
            
            # Conditional node returns conditions for evaluation
            return {
                'processed': {
                    'action': 'evaluate_conditional',
                    'conditions': conditions,
                    'true_path': config.get('truePath'),
                    'false_path': config.get('falsePath')
                },
                'raw': config,
                'summary': {
                    'node_type': 'conditional',
                    'conditions_count': len(conditions),
                    'has_true_path': bool(config.get('truePath')),
                    'has_false_path': bool(config.get('falsePath'))
                },
                'credits_used': 0
            }
        except Exception as e:
            logger.error(f"Conditional node execution failed: {e}")
            raise


# Global service instance
workflow_execution_service = WorkflowExecutionService()