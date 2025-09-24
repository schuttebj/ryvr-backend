"""
File Input Workflow Node
Allows workflows to use uploaded files as input data
"""

from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
import logging

from services.file_service import FileService
import models

logger = logging.getLogger(__name__)

class FileInputNode:
    """Workflow node for file input operations"""
    
    NODE_TYPE = "file_input"
    DISPLAY_NAME = "File Input"
    DESCRIPTION = "Use uploaded files as input data in workflows"
    CATEGORY = "input"
    
    @staticmethod
    def get_node_config_schema() -> Dict[str, Any]:
        """Get the configuration schema for this node type"""
        return {
            "type": "object",
            "properties": {
                "file_id": {
                    "type": "integer",
                    "title": "File ID",
                    "description": "ID of the uploaded file to use"
                },
                "output_type": {
                    "type": "string",
                    "title": "Output Type",
                    "description": "Type of output to provide",
                    "enum": ["content", "summary", "metadata", "file_url"],
                    "default": "content"
                },
                "business_context": {
                    "type": ["integer", "null"],
                    "title": "Business Context",
                    "description": "Business ID for context, or null for account-level"
                },
                "include_metadata": {
                    "type": "boolean", 
                    "title": "Include Metadata",
                    "description": "Whether to include file metadata in output",
                    "default": false
                }
            },
            "required": ["file_id", "output_type"]
        }
    
    @staticmethod
    def get_output_schema() -> Dict[str, Any]:
        """Get the output schema for this node type"""
        return {
            "type": "object",
            "properties": {
                "file_content": {
                    "type": ["string", "null"],
                    "description": "Extracted text content from the file"
                },
                "file_summary": {
                    "type": ["string", "null"],
                    "description": "AI-generated summary of the file"
                },
                "file_url": {
                    "type": ["string", "null"],
                    "description": "Download URL for the file"
                },
                "file_metadata": {
                    "type": "object",
                    "description": "File metadata including name, size, type",
                    "properties": {
                        "id": {"type": "integer"},
                        "original_name": {"type": "string"},
                        "file_type": {"type": "string"},
                        "file_size": {"type": "integer"},
                        "created_at": {"type": "string"},
                        "processing_status": {"type": "string"}
                    }
                },
                "success": {
                    "type": "boolean",
                    "description": "Whether the operation was successful"
                },
                "error_message": {
                    "type": ["string", "null"],
                    "description": "Error message if operation failed"
                }
            }
        }
    
    @staticmethod
    async def execute(
        config: Dict[str, Any],
        input_data: Dict[str, Any],
        context: Dict[str, Any],
        db: Session
    ) -> Dict[str, Any]:
        """
        Execute the file input node
        
        Args:
            config: Node configuration containing file_id and output_type
            input_data: Input data from previous nodes (not used for file input)
            context: Execution context (user_id, business_id, etc.)
            db: Database session
            
        Returns:
            Dictionary containing requested file data
        """
        
        try:
            file_service = FileService(db)
            
            # Get configuration
            file_id = config.get("file_id")
            output_type = config.get("output_type", "content")
            include_metadata = config.get("include_metadata", False)
            user_id = context.get("user_id")
            
            if not file_id:
                return {
                    "success": False,
                    "error_message": "File ID is required"
                }
            
            if not user_id:
                return {
                    "success": False,
                    "error_message": "User context is required"
                }
            
            # Get the file
            file_record = await file_service.get_file(file_id, user_id)
            if not file_record:
                return {
                    "success": False,
                    "error_message": f"File with ID {file_id} not found or access denied"
                }
            
            # Prepare output data
            output = {
                "success": True,
                "error_message": None
            }
            
            # Add requested data based on output_type
            if output_type == "content":
                output["file_content"] = file_record.content_text
                
            elif output_type == "summary":
                output["file_summary"] = file_record.summary
                
            elif output_type == "metadata":
                output["file_metadata"] = {
                    "id": file_record.id,
                    "original_name": file_record.original_name,
                    "file_type": file_record.file_type,
                    "file_size": file_record.file_size,
                    "created_at": file_record.created_at.isoformat(),
                    "processing_status": file_record.processing_status
                }
                
            elif output_type == "file_url":
                # Generate download URL (this would be implemented based on your API structure)
                output["file_url"] = f"/api/v1/files/{file_record.id}/download"
            
            # Include metadata if requested
            if include_metadata:
                output["file_metadata"] = {
                    "id": file_record.id,
                    "original_name": file_record.original_name,
                    "file_type": file_record.file_type,
                    "file_size": file_record.file_size,
                    "created_at": file_record.created_at.isoformat(),
                    "processing_status": file_record.processing_status,
                    "tags": file_record.tags
                }
            
            return output
            
        except Exception as e:
            logger.error(f"Error executing file input node: {e}")
            return {
                "success": False,
                "error_message": f"Failed to process file: {str(e)}"
            }
    
    @staticmethod
    def validate_config(config: Dict[str, Any]) -> List[str]:
        """
        Validate node configuration
        
        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []
        
        if not config.get("file_id"):
            errors.append("File ID is required")
        
        output_type = config.get("output_type")
        valid_output_types = ["content", "summary", "metadata", "file_url"]
        if output_type not in valid_output_types:
            errors.append(f"Output type must be one of: {', '.join(valid_output_types)}")
        
        return errors
    
    @staticmethod
    def get_node_template() -> Dict[str, Any]:
        """Get a template configuration for this node type"""
        return {
            "type": FileInputNode.NODE_TYPE,
            "display_name": FileInputNode.DISPLAY_NAME,
            "description": FileInputNode.DESCRIPTION,
            "category": FileInputNode.CATEGORY,
            "config": {
                "file_id": None,
                "output_type": "content",
                "include_metadata": False
            },
            "position": {"x": 0, "y": 0},
            "inputs": [],
            "outputs": ["file_data"]
        }

# Node registry entry (this would be added to your workflow system's node registry)
FILE_INPUT_NODE_DEFINITION = {
    "type": FileInputNode.NODE_TYPE,
    "class": FileInputNode,
    "display_name": FileInputNode.DISPLAY_NAME,
    "description": FileInputNode.DESCRIPTION,
    "category": FileInputNode.CATEGORY,
    "config_schema": FileInputNode.get_node_config_schema(),
    "output_schema": FileInputNode.get_output_schema(),
    "template": FileInputNode.get_node_template()
}
