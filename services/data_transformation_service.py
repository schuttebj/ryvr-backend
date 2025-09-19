"""
Data Transformation Service for Workflow V2
Handles extract, aggregate, format, and compute transformations for workflow steps

Specifically designed to handle the use case:
Input: [prop1{id:1,value:150}, prop2{id:2,value:250}]
Output: "150, 250" (comma-separated values) or sum/avg calculations
"""

import statistics
import operator
import re
import json
from typing import Any, Dict, List, Union, Optional, Callable
from functools import reduce
import logging

from .expression_engine import expression_engine

logger = logging.getLogger(__name__)


class DataTransformationService:
    """
    Applies comprehensive data transformations according to workflow step configurations
    
    Supports:
    - Extract: Pull specific properties from arrays/objects using JMESPath
    - Aggregate: Sum, average, count, min, max operations
    - Format: Join arrays, split strings, case conversion
    - Compute: Mathematical expressions and custom calculations
    """
    
    def __init__(self):
        self.aggregators = {
            'sum': self._aggregate_sum,
            'avg': self._aggregate_avg,
            'mean': self._aggregate_avg,  # Alias for avg
            'count': self._aggregate_count,
            'min': self._aggregate_min,
            'max': self._aggregate_max,
            'first': self._aggregate_first,
            'last': self._aggregate_last,
            'unique': self._aggregate_unique,
            'concat': self._aggregate_concat
        }
        
        self.formatters = {
            'join': self._format_join,
            'split': self._format_split,
            'upper': self._format_upper,
            'lower': self._format_lower,
            'title': self._format_title,
            'trim': self._format_trim,
            'replace': self._format_replace,
            'slice': self._format_slice
        }
    
    def apply_transformations(self, data: Any, transform_config: Dict[str, Any], 
                            runtime_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Apply all transformations according to the configuration
        
        Args:
            data: Source data to transform
            transform_config: Transformation configuration
            runtime_context: Runtime context for expression evaluation
            
        Returns:
            Dictionary with transformation results
            
        Example:
            Input data: [{"id": 1, "value": 150}, {"id": 2, "value": 250}]
            Config: {
                "extract": [{"as": "values", "expr": "expr: @[].value"}],
                "aggregate": [{"as": "values_sum", "function": "sum", "source": "values"}],
                "format": [{"as": "values_csv", "function": "join", "source": "values", "separator": ", "}]
            }
            Result: {"values": [150, 250], "values_sum": 400, "values_csv": "150, 250"}
        """
        result = {"_source": data}
        context = runtime_context or {}
        
        try:
            # Step 1: Extract transformations
            if "extract" in transform_config:
                extract_results = self._apply_extractions(data, transform_config["extract"], context)
                result.update(extract_results)
                logger.debug(f"Extract results: {extract_results}")
            
            # Step 2: Aggregate transformations (uses extract results)
            if "aggregate" in transform_config:
                aggregate_results = self._apply_aggregations(result, transform_config["aggregate"])
                result.update(aggregate_results)
                logger.debug(f"Aggregate results: {aggregate_results}")
            
            # Step 3: Format transformations (uses previous results)
            if "format" in transform_config:
                format_results = self._apply_formatting(result, transform_config["format"])
                result.update(format_results)
                logger.debug(f"Format results: {format_results}")
            
            # Step 4: Compute transformations (mathematical expressions)
            if "compute" in transform_config:
                compute_results = self._apply_computations(result, transform_config["compute"], context)
                result.update(compute_results)
                logger.debug(f"Compute results: {compute_results}")
            
            # Remove internal source data unless specifically requested
            if not transform_config.get("keep_source", False):
                result.pop("_source", None)
                
            return result
            
        except Exception as e:
            logger.error(f"Transformation failed: {e}")
            raise TransformationError(f"Data transformation failed: {e}")
    
    def _apply_extractions(self, data: Any, extractions: List[Dict[str, Any]], 
                          context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle extract operations
        
        Examples:
            {"as": "values", "expr": "expr: @[].value"} -> Extract all 'value' properties
            {"as": "filtered", "expr": "expr: @[?value > 100]"} -> Filter and extract
        """
        result = {}
        
        for extraction in extractions:
            alias = extraction["as"]
            expr = extraction["expr"]
            
            try:
                if expr.startswith("expr: "):
                    # Use JMESPath expression engine
                    # Create context with current data as root (@)
                    eval_context = {"@": data, **context}
                    extracted = expression_engine.evaluate(expr, eval_context)
                    result[alias] = extracted
                else:
                    # Simple path extraction
                    result[alias] = self._simple_path_extract(data, expr)
                    
                logger.debug(f"Extracted '{alias}': {result[alias]}")
                
            except Exception as e:
                logger.error(f"Extraction failed for '{alias}': {e}")
                result[alias] = None
        
        return result
    
    def _apply_aggregations(self, data: Dict[str, Any], aggregations: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Handle aggregate functions: sum, avg, count, min, max, etc.
        
        Examples:
            {"as": "total", "function": "sum", "source": "values"} -> Sum all values
            {"as": "average", "function": "avg", "source": "values"} -> Average values
        """
        result = {}
        
        for agg in aggregations:
            alias = agg["as"]
            function = agg["function"]
            source = agg["source"]
            
            try:
                if source not in data:
                    logger.warning(f"Source '{source}' not found for aggregation '{alias}'")
                    result[alias] = None
                    continue
                    
                source_data = data[source]
                
                if function in self.aggregators:
                    result[alias] = self.aggregators[function](source_data)
                else:
                    logger.error(f"Unknown aggregation function: {function}")
                    result[alias] = None
                    
                logger.debug(f"Aggregated '{alias}' ({function}): {result[alias]}")
                
            except Exception as e:
                logger.error(f"Aggregation failed for '{alias}': {e}")
                result[alias] = None
        
        return result
    
    def _apply_formatting(self, data: Dict[str, Any], formats: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Handle format functions: join, split, case conversion, etc.
        
        Examples:
            {"as": "csv", "function": "join", "source": "values", "separator": ", "} -> "150, 250"
            {"as": "upper_text", "function": "upper", "source": "text"} -> "HELLO WORLD"
        """
        result = {}
        
        for fmt in formats:
            alias = fmt["as"]
            function = fmt["function"]
            source = fmt["source"]
            
            try:
                if source not in data:
                    logger.warning(f"Source '{source}' not found for formatting '{alias}'")
                    result[alias] = None
                    continue
                    
                source_data = data[source]
                
                if function in self.formatters:
                    # Pass additional parameters to formatter
                    kwargs = {k: v for k, v in fmt.items() if k not in ["as", "function", "source"]}
                    result[alias] = self.formatters[function](source_data, **kwargs)
                else:
                    logger.error(f"Unknown format function: {function}")
                    result[alias] = None
                    
                logger.debug(f"Formatted '{alias}' ({function}): {result[alias]}")
                
            except Exception as e:
                logger.error(f"Formatting failed for '{alias}': {e}")
                result[alias] = None
        
        return result
    
    def _apply_computations(self, data: Dict[str, Any], computations: List[Dict[str, Any]], 
                           context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle compute transformations (mathematical expressions)
        
        Examples:
            {"as": "range", "expr": "expr: max(values) - min(values)"} -> Calculate range
            {"as": "percentage", "expr": "expr: (current / total) * 100"} -> Calculate percentage
        """
        result = {}
        
        for comp in computations:
            alias = comp["as"]
            expr = comp["expr"]
            
            try:
                if expr.startswith("expr: "):
                    # Create evaluation context with current data
                    eval_context = {**data, **context}
                    computed = expression_engine.evaluate(expr, eval_context)
                    result[alias] = computed
                else:
                    # Simple mathematical evaluation
                    result[alias] = self._simple_math_eval(expr, data)
                    
                logger.debug(f"Computed '{alias}': {result[alias]}")
                
            except Exception as e:
                logger.error(f"Computation failed for '{alias}': {e}")
                result[alias] = None
        
        return result
    
    # Aggregation functions
    def _aggregate_sum(self, data: Any) -> Union[int, float]:
        """Sum numeric values"""
        if not isinstance(data, list):
            return data if isinstance(data, (int, float)) else 0
        return sum(x for x in data if isinstance(x, (int, float)))
    
    def _aggregate_avg(self, data: Any) -> Union[int, float]:
        """Calculate average of numeric values"""
        if not isinstance(data, list):
            return data if isinstance(data, (int, float)) else 0
        numeric_data = [x for x in data if isinstance(x, (int, float))]
        return statistics.mean(numeric_data) if numeric_data else 0
    
    def _aggregate_count(self, data: Any) -> int:
        """Count items"""
        if isinstance(data, list):
            return len(data)
        elif data is not None:
            return 1
        return 0
    
    def _aggregate_min(self, data: Any) -> Any:
        """Find minimum value"""
        if isinstance(data, list) and data:
            return min(data)
        return data
    
    def _aggregate_max(self, data: Any) -> Any:
        """Find maximum value"""
        if isinstance(data, list) and data:
            return max(data)
        return data
    
    def _aggregate_first(self, data: Any) -> Any:
        """Get first item"""
        if isinstance(data, list) and data:
            return data[0]
        return data
    
    def _aggregate_last(self, data: Any) -> Any:
        """Get last item"""
        if isinstance(data, list) and data:
            return data[-1]
        return data
    
    def _aggregate_unique(self, data: Any) -> List[Any]:
        """Get unique values"""
        if isinstance(data, list):
            seen = set()
            result = []
            for item in data:
                if item not in seen:
                    seen.add(item)
                    result.append(item)
            return result
        return [data] if data is not None else []
    
    def _aggregate_concat(self, data: Any) -> str:
        """Concatenate values as strings"""
        if isinstance(data, list):
            return "".join(str(x) for x in data)
        return str(data) if data is not None else ""
    
    # Format functions
    def _format_join(self, data: Any, separator: str = ",", **kwargs) -> str:
        """
        Join array elements with separator
        
        This is the key function for your use case:
        [150, 250] with separator=", " becomes "150, 250"
        """
        if isinstance(data, list):
            return separator.join(str(x) for x in data)
        return str(data) if data is not None else ""
    
    def _format_split(self, data: Any, separator: str = ",", **kwargs) -> List[str]:
        """Split string by separator"""
        if isinstance(data, str):
            return data.split(separator)
        return [str(data)] if data is not None else []
    
    def _format_upper(self, data: Any, **kwargs) -> str:
        """Convert to uppercase"""
        return str(data).upper() if data is not None else ""
    
    def _format_lower(self, data: Any, **kwargs) -> str:
        """Convert to lowercase"""
        return str(data).lower() if data is not None else ""
    
    def _format_title(self, data: Any, **kwargs) -> str:
        """Convert to title case"""
        return str(data).title() if data is not None else ""
    
    def _format_trim(self, data: Any, **kwargs) -> str:
        """Trim whitespace"""
        return str(data).strip() if data is not None else ""
    
    def _format_replace(self, data: Any, old: str, new: str, **kwargs) -> str:
        """Replace substring"""
        return str(data).replace(old, new) if data is not None else ""
    
    def _format_slice(self, data: Any, start: int = 0, end: Optional[int] = None, **kwargs) -> Any:
        """Slice array or string"""
        if isinstance(data, (list, str)):
            return data[start:end]
        return data
    
    # Helper methods
    def _simple_path_extract(self, data: Any, path: str) -> Any:
        """Simple dot-notation path extraction for basic cases"""
        try:
            parts = path.split('.')
            current = data
            for part in parts:
                if isinstance(current, dict):
                    current = current.get(part)
                elif isinstance(current, list) and part.isdigit():
                    current = current[int(part)]
                else:
                    return None
            return current
        except:
            return None
    
    def _simple_math_eval(self, expr: str, data: Dict[str, Any]) -> Any:
        """Simple mathematical expression evaluation (basic operations only)"""
        try:
            # Replace variable names with values
            for key, value in data.items():
                if isinstance(value, (int, float)):
                    expr = expr.replace(key, str(value))
            
            # Only allow basic math operations for security
            allowed_chars = set('0123456789+-*/.() ')
            if all(c in allowed_chars for c in expr):
                return eval(expr)
            else:
                logger.warning(f"Unsafe mathematical expression: {expr}")
                return None
        except:
            return None


class TransformationError(Exception):
    """Raised when data transformation fails"""
    pass


# Example usage and test cases
def test_transformation_service():
    """Test the transformation service with the specific use case"""
    service = DataTransformationService()
    
    # Test case: Extract values from array and format as CSV
    data = [
        {"id": 1, "value": 150},
        {"id": 2, "value": 250}
    ]
    
    transform_config = {
        "extract": [
            {"as": "values", "expr": "expr: @[].value"},
            {"as": "ids", "expr": "expr: @[].id"}
        ],
        "aggregate": [
            {"as": "values_sum", "function": "sum", "source": "values"},
            {"as": "values_avg", "function": "avg", "source": "values"},
            {"as": "values_count", "function": "count", "source": "values"}
        ],
        "format": [
            {"as": "values_csv", "function": "join", "source": "values", "separator": ", "},
            {"as": "ids_pipe", "function": "join", "source": "ids", "separator": " | "}
        ],
        "compute": [
            {"as": "value_range", "expr": "expr: max(values) - min(values)"}
        ]
    }
    
    result = service.apply_transformations(data, transform_config)
    
    print("Test Results:")
    print(f"Original data: {data}")
    print(f"Extracted values: {result.get('values')}")  # [150, 250]
    print(f"Values sum: {result.get('values_sum')}")     # 400
    print(f"Values avg: {result.get('values_avg')}")     # 200
    print(f"Values CSV: {result.get('values_csv')}")     # "150, 250"
    print(f"Value range: {result.get('value_range')}")   # 100
    
    return result


# Create singleton instance
data_transformation_service = DataTransformationService()

if __name__ == "__main__":
    test_transformation_service()
