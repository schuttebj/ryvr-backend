"""
Data Processing API Router
Endpoints for filtering, transforming, and processing workflow data
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import datetime
import logging

from database import get_db
from auth import get_current_active_user
import models, schemas
from services.data_filter_service import data_filter_service

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/filter", response_model=Dict[str, Any])
async def filter_data(
    filter_request: schemas.DataFilterRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Filter data array using specified criteria"""
    try:
        # Validate input data
        if not isinstance(filter_request.source_data, list):
            raise HTTPException(
                status_code=400, 
                detail="Source data must be an array"
            )
        
        # Apply filtering
        result = data_filter_service.filter_data(
            source_data=filter_request.source_data,
            filter_config=filter_request.filter_config
        )
        
        # Log the operation
        logger.info(f"Data filter operation by user {current_user.id}: "
                   f"{len(filter_request.source_data)} -> {result['total_filtered']} items")
        
        return {
            "success": True,
            "data": result,
            "message": f"Filtered {result['original_count']} items to {result['total_filtered']} results"
        }
        
    except ValueError as e:
        logger.error(f"Data filter validation error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Data filter error: {e}")
        raise HTTPException(status_code=500, detail="Failed to filter data")


@router.post("/transform", response_model=Dict[str, Any])
async def transform_data(
    transform_request: schemas.DataTransformRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Transform data using specified operations"""
    try:
        # Basic data transformation operations
        source_data = transform_request.source_data
        operations = transform_request.operations
        
        result_data = source_data
        
        for operation in operations:
            operation_type = operation.get('type')
            
            if operation_type == 'select_fields':
                # Select only specific fields from each item
                fields = operation.get('fields', [])
                result_data = [
                    {field: item.get(field) for field in fields if field in item}
                    for item in result_data
                ]
            
            elif operation_type == 'rename_field':
                # Rename a field in all items
                old_name = operation.get('old_name')
                new_name = operation.get('new_name')
                if old_name and new_name:
                    for item in result_data:
                        if old_name in item:
                            item[new_name] = item.pop(old_name)
            
            elif operation_type == 'add_field':
                # Add a computed field to all items
                field_name = operation.get('field_name')
                field_value = operation.get('field_value')
                if field_name:
                    for item in result_data:
                        item[field_name] = field_value
        
        return {
            "success": True,
            "data": {
                "transformed_items": result_data,
                "original_count": len(source_data),
                "final_count": len(result_data),
                "operations_applied": len(operations)
            },
            "message": f"Applied {len(operations)} transformation operations"
        }
        
    except Exception as e:
        logger.error(f"Data transform error: {e}")
        raise HTTPException(status_code=500, detail="Failed to transform data")


@router.post("/validate", response_model=Dict[str, Any])
async def validate_data(
    validation_request: schemas.DataValidationRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Validate data against specified schema or rules"""
    try:
        source_data = validation_request.source_data
        validation_rules = validation_request.validation_rules
        
        errors = []
        valid_items = []
        invalid_items = []
        
        for i, item in enumerate(source_data):
            item_errors = []
            
            # Check required fields
            required_fields = validation_rules.get('required_fields', [])
            for field in required_fields:
                if field not in item or item[field] is None or item[field] == '':
                    item_errors.append(f"Missing required field: {field}")
            
            # Check field types
            field_types = validation_rules.get('field_types', {})
            for field, expected_type in field_types.items():
                if field in item and item[field] is not None:
                    actual_type = type(item[field]).__name__
                    if expected_type == 'string' and not isinstance(item[field], str):
                        item_errors.append(f"Field '{field}' should be string, got {actual_type}")
                    elif expected_type == 'number' and not isinstance(item[field], (int, float)):
                        item_errors.append(f"Field '{field}' should be number, got {actual_type}")
            
            if item_errors:
                invalid_items.append({"index": i, "item": item, "errors": item_errors})
                errors.extend([f"Item {i}: {error}" for error in item_errors])
            else:
                valid_items.append(item)
        
        return {
            "success": True,
            "data": {
                "valid_items": valid_items,
                "invalid_items": invalid_items,
                "total_items": len(source_data),
                "valid_count": len(valid_items),
                "invalid_count": len(invalid_items),
                "errors": errors
            },
            "message": f"Validated {len(source_data)} items: {len(valid_items)} valid, {len(invalid_items)} invalid"
        }
        
    except Exception as e:
        logger.error(f"Data validation error: {e}")
        raise HTTPException(status_code=500, detail="Failed to validate data")