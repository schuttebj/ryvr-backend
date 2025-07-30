"""
Data Filter Service
Provides filtering and processing capabilities for workflow data
"""

from typing import Any, Dict, List, Optional, Union
import logging

logger = logging.getLogger(__name__)


class DataFilterService:
    """Service for filtering and processing data arrays"""
    
    @staticmethod
    def filter_data(source_data: List[Dict[str, Any]], filter_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Filter data array based on configuration
        
        Args:
            source_data: Array of data items to filter
            filter_config: Configuration containing filter rules
            
        Returns:
            Dict containing filtered results and metadata
        """
        try:
            if not isinstance(source_data, list):
                raise ValueError("Source data must be an array")
            
            filter_property = filter_config.get('filterProperty', '')
            filter_operation = filter_config.get('filterOperation', 'contains')
            filter_value = filter_config.get('filterValue', '')
            case_sensitive = filter_config.get('caseSensitive', False)
            max_results = filter_config.get('maxResults', 0)
            
            # Apply filtering logic
            filtered_items = []
            
            for item in source_data:
                if DataFilterService._item_matches_filter(
                    item, filter_property, filter_operation, filter_value, case_sensitive
                ):
                    filtered_items.append(item)
                    
                    # Apply max results limit during filtering for efficiency
                    if max_results > 0 and len(filtered_items) >= max_results:
                        break
            
            result = {
                'filtered_items': filtered_items,
                'total_filtered': len(filtered_items),
                'original_count': len(source_data),
                'filter_applied': {
                    'property': filter_property,
                    'operation': filter_operation,
                    'value': filter_value,
                    'case_sensitive': case_sensitive
                },
                'truncated': max_results > 0 and len(source_data) > max_results
            }
            
            logger.info(f"Data filter applied: {len(source_data)} -> {len(filtered_items)} items")
            return result
            
        except Exception as e:
            logger.error(f"Data filtering failed: {e}")
            raise ValueError(f"Data filtering failed: {str(e)}")
    
    @staticmethod
    def _item_matches_filter(item: Dict[str, Any], property_path: str, 
                           operation: str, filter_value: str, case_sensitive: bool) -> bool:
        """
        Check if an item matches the filter criteria
        
        Args:
            item: Data item to check
            property_path: Dot-notation path to property (e.g., 'domain', 'meta.title')
            operation: Filter operation (contains, equals, starts_with, etc.)
            filter_value: Value to compare against
            case_sensitive: Whether comparison should be case sensitive
            
        Returns:
            True if item matches filter, False otherwise
        """
        try:
            # Get the property value using dot notation
            item_value = DataFilterService._get_nested_property(item, property_path)
            
            # Handle different filter operations
            if operation == 'contains':
                return DataFilterService._string_contains(item_value, filter_value, case_sensitive)
            
            elif operation == 'not_contains':
                return not DataFilterService._string_contains(item_value, filter_value, case_sensitive)
            
            elif operation == 'equals':
                return DataFilterService._string_equals(item_value, filter_value, case_sensitive)
            
            elif operation == 'not_equals':
                return not DataFilterService._string_equals(item_value, filter_value, case_sensitive)
            
            elif operation == 'starts_with':
                return DataFilterService._string_starts_with(item_value, filter_value, case_sensitive)
            
            elif operation == 'ends_with':
                return DataFilterService._string_ends_with(item_value, filter_value, case_sensitive)
            
            elif operation == 'greater_than':
                try:
                    return float(item_value) > float(filter_value)
                except (ValueError, TypeError):
                    return False
            
            elif operation == 'less_than':
                try:
                    return float(item_value) < float(filter_value)
                except (ValueError, TypeError):
                    return False
            
            elif operation == 'exists':
                return item_value is not None
            
            elif operation == 'not_exists':
                return item_value is None
            
            else:
                logger.warning(f"Unknown filter operation: {operation}")
                return True
                
        except Exception as e:
            logger.warning(f"Error checking filter match: {e}")
            return False
    
    @staticmethod
    def _get_nested_property(obj: Dict[str, Any], property_path: str) -> Any:
        """
        Get nested property value using dot notation
        
        Args:
            obj: Object to get property from
            property_path: Dot-separated path (e.g., 'meta.title')
            
        Returns:
            Property value or None if not found
        """
        if not property_path:
            return obj
        
        try:
            current = obj
            for part in property_path.split('.'):
                if isinstance(current, dict) and part in current:
                    current = current[part]
                else:
                    return None
            return current
        except (KeyError, TypeError, AttributeError):
            return None
    
    @staticmethod
    def _string_contains(item_value: Any, filter_value: str, case_sensitive: bool) -> bool:
        """Check if item value contains filter value"""
        item_str = str(item_value or '')
        filter_str = filter_value if case_sensitive else filter_value.lower()
        item_str = item_str if case_sensitive else item_str.lower()
        return filter_str in item_str
    
    @staticmethod
    def _string_equals(item_value: Any, filter_value: str, case_sensitive: bool) -> bool:
        """Check if item value equals filter value"""
        item_str = str(item_value or '')
        filter_str = filter_value if case_sensitive else filter_value.lower()
        item_str = item_str if case_sensitive else item_str.lower()
        return item_str == filter_str
    
    @staticmethod
    def _string_starts_with(item_value: Any, filter_value: str, case_sensitive: bool) -> bool:
        """Check if item value starts with filter value"""
        item_str = str(item_value or '')
        filter_str = filter_value if case_sensitive else filter_value.lower()
        item_str = item_str if case_sensitive else item_str.lower()
        return item_str.startswith(filter_str)
    
    @staticmethod
    def _string_ends_with(item_value: Any, filter_value: str, case_sensitive: bool) -> bool:
        """Check if item value ends with filter value"""
        item_str = str(item_value or '')
        filter_str = filter_value if case_sensitive else filter_value.lower()
        item_str = item_str if case_sensitive else item_str.lower()
        return item_str.endswith(filter_str)


# Global service instance
data_filter_service = DataFilterService()