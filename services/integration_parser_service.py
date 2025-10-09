"""
Integration Parser Service
Uses OpenAI to parse API documentation and generate integration configurations
"""

import logging
import json
from typing import Dict, List, Optional, Any
from openai import OpenAI

from config import settings

logger = logging.getLogger(__name__)


class IntegrationParserService:
    """
    Service for AI-powered API documentation parsing.
    Extracts integration configuration from documentation using OpenAI's structured output.
    """
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or getattr(settings, 'openai_api_key', None)
        if not self.api_key:
            raise ValueError("OpenAI API key not configured")
        
        self.client = OpenAI(api_key=self.api_key)
    
    async def parse_documentation(
        self,
        platform_name: str,
        documentation: str,
        instructions: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Parse API documentation and extract integration configuration
        
        Args:
            platform_name: Name of the API platform (e.g., "Brevo", "SendGrid")
            documentation: API documentation text
            instructions: Optional specific instructions for parsing
            
        Returns:
            Integration configuration dict matching the schema
        """
        try:
            # Build system prompt
            system_prompt = self._build_system_prompt()
            
            # Build user prompt with documentation
            user_prompt = self._build_user_prompt(platform_name, documentation, instructions)
            
            # Get JSON schema for structured output
            response_schema = self._get_response_schema()
            
            # Call OpenAI with structured output
            response = self.client.chat.completions.create(
                model="gpt-4o-2024-08-06",  # Model that supports structured output
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "integration_config",
                        "strict": True,
                        "schema": response_schema
                    }
                },
                temperature=0.1,  # Low temperature for consistent parsing
                max_completion_tokens=16000
            )
            
            # Parse response
            content = response.choices[0].message.content
            parsed_config = json.loads(content)
            
            logger.info(f"Successfully parsed documentation for {platform_name}")
            
            return {
                "success": True,
                "config": parsed_config,
                "tokens_used": response.usage.total_tokens
            }
            
        except Exception as e:
            logger.error(f"Failed to parse documentation: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }
    
    def _build_system_prompt(self) -> str:
        """Build system prompt for the AI parser"""
        
        return """You are an expert API integration analyst. Your task is to parse API documentation and extract structured integration configuration.

Analyze the provided API documentation and extract:
1. Platform information (base URL, authentication type, display details, sandbox mode)
2. Authentication configuration (credential requirements)
3. Available API operations/endpoints
4. For each operation:
   - Endpoint path and HTTP method
   - Required and optional parameters
   - Parameter types, locations (body/query/path), and default values
   - Headers required
   - Response structure
   - Whether the operation is asynchronous (requires polling)

Focus on extracting accurate, complete information. If you're unsure about a parameter type or requirement, err on the side of making it optional with a sensible default.

For authentication types:
- "basic" - HTTP Basic Auth (username/password)
- "bearer" - Bearer token in Authorization header
- "api_key" - API key (can be in header or query param)
- "oauth2" - OAuth 2.0 flow

For parameter types:
- "string" - Text value
- "number" - Numeric value (int or float)
- "boolean" - True/False
- "array" - List of values
- "object" - Nested object
- "select" - Enumerated options
- "file" - File upload

For parameter locations:
- "body" - In request body (POST/PUT)
- "query" - In URL query string
- "path" - In URL path (e.g., /users/{id})
- "header" - In request headers

For sandbox/testing environments:
- Check if the API has a sandbox/test environment with a different base URL
- Set "has_sandbox" to true if found, false otherwise
- Extract the sandbox base URL if available (otherwise use empty string)
- Common patterns: api.sandbox.example.com, api-sandbox.example.com, sandbox.example.com, test-api.example.com

Return the extracted configuration in the specified JSON schema format."""
    
    def _build_user_prompt(
        self,
        platform_name: str,
        documentation: str,
        instructions: Optional[str] = None
    ) -> str:
        """Build user prompt with documentation"""
        
        prompt = f"""Platform: {platform_name}

{instructions if instructions else 'Extract all available API operations from the documentation below.'}

API Documentation:
---
{documentation}
---

Extract the integration configuration following the schema. Include all relevant endpoints, parameters, and authentication details."""
        
        return prompt
    
    def _get_response_schema(self) -> Dict[str, Any]:
        """Get JSON schema for OpenAI structured output with strict mode compatibility"""
        
        return {
            "type": "object",
            "properties": {
                "platform": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "base_url": {"type": "string"},
                        "auth_type": {
                            "type": "string",
                            "enum": ["basic", "bearer", "api_key", "oauth2"]
                        },
                        "color": {"type": "string"},
                        "documentation_url": {"type": "string"},
                        "has_sandbox": {"type": "boolean"},
                        "sandbox_base_url": {"type": "string"}
                    },
                    "required": ["name", "base_url", "auth_type", "color", "documentation_url", "has_sandbox", "sandbox_base_url"],
                    "additionalProperties": False
                },
                "auth_config": {
                    "type": "object",
                    "properties": {
                        "type": {
                            "type": "string",
                            "enum": ["basic", "bearer", "api_key", "oauth2"]
                        },
                        "credentials": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "type": {
                                        "type": "string",
                                        "enum": ["string", "password", "number"]
                                    },
                                    "required": {"type": "boolean"},
                                    "fixed": {"type": "boolean"},
                                    "description": {"type": "string"}
                                },
                                "required": ["name", "type", "required", "fixed", "description"],
                                "additionalProperties": False
                            }
                        }
                    },
                    "required": ["type", "credentials"],
                    "additionalProperties": False
                },
                "operations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "name": {"type": "string"},
                            "description": {"type": "string"},
                            "endpoint": {"type": "string"},
                            "method": {
                                "type": "string",
                                "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"]
                            },
                            "category": {"type": "string"},
                            "base_credits": {"type": "integer"},
                            "is_async": {"type": "boolean"},
                            "parameters": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string"},
                                        "type": {
                                            "type": "string",
                                            "enum": ["string", "number", "boolean", "array", "object", "select", "file"]
                                        },
                                        "required": {"type": "boolean"},
                                        "fixed": {"type": "boolean"},
                                        "default": {"type": "string"},  # Simplified to string for strict mode
                                        "description": {"type": "string"},
                                        "location": {
                                            "type": "string",
                                            "enum": ["body", "query", "path", "header"]
                                        },
                                        "options": {
                                            "type": "array",
                                            "items": {"type": "string"}
                                        }
                                    },
                                    "required": ["name", "type", "required", "fixed", "default", "description", "location", "options"],
                                    "additionalProperties": False
                                }
                            },
                            "headers": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string"},
                                        "value": {"type": "string"},
                                        "fixed": {"type": "boolean"}
                                    },
                                    "required": ["name", "value", "fixed"],
                                    "additionalProperties": False
                                }
                            }
                        },
                        "required": ["id", "name", "description", "endpoint", "method", "category", "base_credits", "is_async", "parameters", "headers"],
                        "additionalProperties": False
                    }
                }
            },
            "required": ["platform", "auth_config", "operations"],
            "additionalProperties": False
        }
    
    def validate_parsed_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate and enhance parsed configuration
        
        Args:
            config: Parsed configuration from AI
            
        Returns:
            Validation result with errors/warnings
        """
        errors = []
        warnings = []
        
        # Check platform config
        if "platform" not in config:
            errors.append("Missing platform configuration")
        else:
            platform = config["platform"]
            if not platform.get("base_url"):
                errors.append("Missing base_url in platform config")
            if not platform.get("base_url", "").startswith("http"):
                errors.append("base_url must start with http:// or https://")
        
        # Check auth config
        if "auth_config" not in config:
            errors.append("Missing auth_config")
        else:
            auth = config["auth_config"]
            if not auth.get("credentials"):
                warnings.append("No credentials defined in auth_config")
        
        # Check operations
        if "operations" not in config or not config["operations"]:
            errors.append("No operations defined")
        else:
            operation_ids = set()
            for idx, op in enumerate(config["operations"]):
                # Check for duplicate operation IDs
                if op["id"] in operation_ids:
                    errors.append(f"Duplicate operation ID: {op['id']}")
                operation_ids.add(op["id"])
                
                # Check endpoint format
                if not op.get("endpoint", "").startswith("/"):
                    warnings.append(f"Operation '{op['name']}' endpoint should start with /")
                
                # Check parameters
                param_names = set()
                for param in op.get("parameters", []):
                    if param["name"] in param_names:
                        errors.append(f"Duplicate parameter '{param['name']}' in operation '{op['name']}'")
                    param_names.add(param["name"])
                
                # Validate async operations
                if op.get("is_async") and not op.get("async_config"):
                    warnings.append(f"Operation '{op['name']}' marked as async but missing async_config")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings
        }

