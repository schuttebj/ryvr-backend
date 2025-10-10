"""
Expression Engine for Workflow V2
Handles JMESPath expressions and template string processing for the new workflow schema
"""

import jmespath
import re
import json
from typing import Any, Dict, List, Optional, Union
import logging

logger = logging.getLogger(__name__)


class ExpressionEngine:
    """
    Evaluates JMESPath expressions and template strings for workflow data binding
    
    Supports:
    - JMESPath expressions with "expr: " prefix
    - Template strings with {{ variable }} syntax
    - Validation and error handling
    - Available path discovery for autocomplete
    """
    
    def __init__(self):
        self.template_engine = TemplateEngine(self)
    
    def evaluate(self, expression: str, context: Dict[str, Any]) -> Any:
        """
        Evaluate a JMESPath expression against the given context
        
        Args:
            expression: JMESPath expression starting with "expr: "
            context: Runtime context to evaluate against
            
        Returns:
            Evaluation result
            
        Examples:
            evaluate("expr: $.inputs.site_url", context) -> "https://example.com"
            evaluate("expr: $.steps.serp_1.output.keywords[].value", context) -> [150, 250]
        """
        if not expression or not isinstance(expression, str):
            return expression
            
        if not expression.startswith("expr: "):
            return expression
            
        try:
            jmes_expr = expression[6:]  # Remove "expr: " prefix
            logger.debug(f"Evaluating JMESPath: {jmes_expr}")
            
            # Handle special $ prefix for root context access
            if jmes_expr.startswith("$."):
                jmes_expr = jmes_expr[2:]  # Remove $. prefix for standard JMESPath
            
            result = jmespath.search(jmes_expr, context)
            logger.debug(f"JMESPath result: {result}")
            
            return result
            
        except Exception as e:
            logger.error(f"JMESPath evaluation failed for '{expression}': {e}")
            raise ExpressionEvaluationError(f"Failed to evaluate expression '{expression}': {e}")
    
    def validate_expression(self, expression: str) -> Dict[str, Any]:
        """
        Validate JMESPath expression syntax
        
        Args:
            expression: Expression to validate
            
        Returns:
            Validation result with is_valid, error_message
        """
        if not expression or not isinstance(expression, str):
            return {"is_valid": True, "error_message": None}
            
        if not expression.startswith("expr: "):
            return {"is_valid": True, "error_message": "Not a JMESPath expression"}
            
        try:
            jmes_expr = expression[6:]
            if jmes_expr.startswith("$."):
                jmes_expr = jmes_expr[2:]
                
            # Try to compile the expression
            jmespath.compile(jmes_expr)
            return {"is_valid": True, "error_message": None}
            
        except Exception as e:
            return {"is_valid": False, "error_message": str(e)}
    
    def get_available_paths(self, context: Dict[str, Any], max_depth: int = 3) -> List[str]:
        """
        Get available JMESPath expressions for autocomplete
        
        Args:
            context: Runtime context to analyze
            max_depth: Maximum nesting depth to explore
            
        Returns:
            List of available path expressions
        """
        paths = []
        
        def extract_paths(obj: Any, current_path: str = "$", depth: int = 0):
            if depth > max_depth:
                return
                
            if isinstance(obj, dict):
                for key, value in obj.items():
                    new_path = f"{current_path}.{key}"
                    paths.append(new_path)
                    extract_paths(value, new_path, depth + 1)
                    
            elif isinstance(obj, list) and obj:
                # Add array access patterns
                paths.append(f"{current_path}[]")
                paths.append(f"{current_path}[0]")
                if len(obj) > 1:
                    paths.append(f"{current_path}[-1]")
                
                # Explore first item structure
                extract_paths(obj[0], f"{current_path}[]", depth + 1)
        
        extract_paths(context)
        return sorted(list(set(paths)))
    
    def resolve_bindings(self, bindings: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Resolve all bindings in a step's input configuration
        
        Args:
            bindings: Input bindings from step configuration
            context: Runtime context
            
        Returns:
            Resolved bindings with expressions evaluated
        """
        resolved = {}
        
        for key, value in bindings.items():
            try:
                resolved[key] = self._resolve_value(value, context)
            except Exception as e:
                logger.error(f"Failed to resolve binding '{key}': {e}")
                resolved[key] = None
                
        return resolved
    
    def resolve_expression(self, value: Any, context: Dict[str, Any]) -> Any:
        """
        Resolve a value that may contain expressions or templates
        This is a public wrapper around _resolve_value
        
        Args:
            value: Value to resolve (string with expressions/templates, or nested structures)
            context: Runtime context
            
        Returns:
            Resolved value with expressions evaluated
        """
        return self._resolve_value(value, context)
    
    def _resolve_value(self, value: Any, context: Dict[str, Any]) -> Any:
        """Recursively resolve a value that may contain expressions or templates"""
        if isinstance(value, str):
            if value.startswith("expr: "):
                return self.evaluate(value, context)
            elif "{{" in value and "}}" in value:
                return self.template_engine.process(value, context)
            else:
                return value
                
        elif isinstance(value, dict):
            return {k: self._resolve_value(v, context) for k, v in value.items()}
            
        elif isinstance(value, list):
            return [self._resolve_value(item, context) for item in value]
            
        else:
            return value


class TemplateEngine:
    """
    Processes template strings with {{ variable }} syntax
    
    Supports:
    - Simple variable substitution: {{ $.inputs.site_url }}
    - JMESPath expressions in templates: {{ $.steps.serp_1.output.keywords[0].value }}
    - Default values: {{ $.inputs.optional_field || 'default' }}
    """
    
    def __init__(self, expression_engine: ExpressionEngine):
        self.expression_engine = expression_engine
        self.template_pattern = re.compile(r'\{\{\s*([^}]+)\s*\}\}')
    
    def process(self, template: str, context: Dict[str, Any]) -> str:
        """
        Process template string by replacing {{ variables }} with values
        
        Args:
            template: Template string with {{ }} placeholders
            context: Runtime context for variable resolution
            
        Returns:
            Processed string with variables replaced
            
        Examples:
            process("Site: {{ $.inputs.site_url }}", context) -> "Site: https://example.com"
            process("Keywords: {{ $.steps.keywords.output.count }}", context) -> "Keywords: 25"
        """
        if not template or not isinstance(template, str):
            return str(template)
            
        def replace_variable(match):
            var_expr = match.group(1).strip()
            
            try:
                # Handle default values with || operator
                if " || " in var_expr:
                    main_expr, default_value = var_expr.split(" || ", 1)
                    main_expr = main_expr.strip()
                    default_value = default_value.strip().strip("'\"")
                    
                    # Try main expression first
                    if main_expr.startswith("$."):
                        result = self.expression_engine.evaluate(f"expr: {main_expr}", context)
                        return str(result) if result is not None else default_value
                    else:
                        return context.get(main_expr, default_value)
                
                # Regular variable resolution
                if var_expr.startswith("$."):
                    # JMESPath expression
                    result = self.expression_engine.evaluate(f"expr: {var_expr}", context)
                    return str(result) if result is not None else f"{{{{ {var_expr} }}}}"
                else:
                    # Simple context lookup
                    result = context.get(var_expr, f"{{{{ {var_expr} }}}}")
                    return str(result)
                    
            except Exception as e:
                logger.warning(f"Failed to resolve template variable '{var_expr}': {e}")
                return f"{{{{ {var_expr} }}}}"
        
        return self.template_pattern.sub(replace_variable, template)
    
    def extract_variables(self, template: str) -> List[str]:
        """
        Extract variable names from template string
        
        Args:
            template: Template string to analyze
            
        Returns:
            List of variable expressions found in template
        """
        if not template or not isinstance(template, str):
            return []
            
        matches = self.template_pattern.findall(template)
        return [match.strip() for match in matches]
    
    def validate_template(self, template: str) -> Dict[str, Any]:
        """
        Validate template syntax and variable expressions
        
        Args:
            template: Template string to validate
            
        Returns:
            Validation result with is_valid, errors, variables
        """
        if not template or not isinstance(template, str):
            return {"is_valid": True, "errors": [], "variables": []}
            
        errors = []
        variables = []
        
        try:
            matches = self.template_pattern.findall(template)
            
            for var_expr in matches:
                var_expr = var_expr.strip()
                variables.append(var_expr)
                
                # Validate JMESPath expressions
                if var_expr.startswith("$."):
                    validation = self.expression_engine.validate_expression(f"expr: {var_expr}")
                    if not validation["is_valid"]:
                        errors.append(f"Invalid expression '{var_expr}': {validation['error_message']}")
                        
        except Exception as e:
            errors.append(f"Template parsing error: {e}")
            
        return {
            "is_valid": len(errors) == 0,
            "errors": errors,
            "variables": variables
        }


class ExpressionEvaluationError(Exception):
    """Raised when expression evaluation fails"""
    pass


class ContextBuilder:
    """
    Builds runtime context for expression evaluation
    
    Manages the complete runtime state structure:
    - $.inputs - per-run inputs
    - $.globals - workflow globals  
    - $.steps.<id>.output - step outputs
    - $.runtime - RYVR-specific context (business, integrations, etc.)
    """
    
    @staticmethod
    def build_context(
        inputs: Dict[str, Any],
        globals_config: Dict[str, Any],
        step_outputs: Dict[str, Any],
        runtime_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Build complete runtime context for expression evaluation
        
        Args:
            inputs: Workflow input parameters
            globals_config: Global workflow configuration
            step_outputs: Outputs from completed steps
            runtime_context: RYVR runtime context (business, user, integrations)
            
        Returns:
            Complete context structure for expression evaluation
        """
        context = {
            "inputs": inputs or {},
            "globals": globals_config or {},
            "steps": {},
            "runtime": runtime_context or {}
        }
        
        # Build step outputs structure
        for step_id, output in (step_outputs or {}).items():
            context["steps"][step_id] = {
                "output": output
            }
            
        return context
    
    @staticmethod
    def add_step_output(context: Dict[str, Any], step_id: str, output: Any) -> Dict[str, Any]:
        """
        Add a step's output to the runtime context
        
        Args:
            context: Current runtime context
            step_id: ID of the completed step
            output: Step's output data
            
        Returns:
            Updated context with new step output
        """
        if "steps" not in context:
            context["steps"] = {}
            
        context["steps"][step_id] = {
            "output": output
        }
        
        return context


# Create singleton instances
expression_engine = ExpressionEngine()
context_builder = ContextBuilder()
