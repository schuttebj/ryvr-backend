"""
Flow Control Service
Handles workflow control flow nodes: Review, Options, and Conditional logic
"""

from typing import Any, Dict, List, Optional
from datetime import datetime
import logging
import json
from sqlalchemy.orm import Session

import models

logger = logging.getLogger(__name__)


class FlowControlService:
    """Handles workflow control flow nodes: Review, Options, Conditional"""
    
    def __init__(self, db: Session):
        self.db = db
    
    async def pause_for_review(
        self,
        execution_id: int,
        step_id: str,
        step_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Pause workflow execution for review approval
        
        Args:
            execution_id: Workflow execution ID
            step_id: Current step ID
            step_config: Configuration for the review node
            
        Returns:
            dict with review details
        """
        try:
            # Get execution
            execution = self.db.query(models.WorkflowExecution).filter(
                models.WorkflowExecution.id == execution_id
            ).first()
            
            if not execution:
                raise ValueError(f"Execution not found: {execution_id}")
            
            # Update execution status
            execution.flow_status = 'in_review'
            execution.current_step = step_id
            
            # Create review approval record
            reviewer_type = step_config.get('reviewerType', 'agency')
            review_approval = models.FlowReviewApproval(
                execution_id=execution_id,
                step_id=step_id,
                reviewer_type=reviewer_type,
                approved=False,  # Not yet approved
                submitted_for_review_at=datetime.utcnow()
            )
            
            self.db.add(review_approval)
            self.db.commit()
            
            logger.info(f"Workflow {execution_id} paused for {reviewer_type} review at step {step_id}")
            
            return {
                'success': True,
                'execution_id': execution_id,
                'step_id': step_id,
                'status': 'awaiting_review',
                'reviewer_type': reviewer_type,
                'editable_nodes': step_config.get('editableNodes', []),
                'editable_fields': step_config.get('editableFields', {})
            }
            
        except Exception as e:
            logger.error(f"Error pausing for review: {e}")
            self.db.rollback()
            raise
    
    async def pause_for_options(
        self,
        execution_id: int,
        step_id: str,
        step_config: Dict[str, Any],
        runtime_state: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Pause workflow execution for options selection
        
        Args:
            execution_id: Workflow execution ID
            step_id: Current step ID
            step_config: Configuration for the options node
            runtime_state: Current workflow runtime state
            
        Returns:
            dict with available options
        """
        try:
            # Get execution
            execution = self.db.query(models.WorkflowExecution).filter(
                models.WorkflowExecution.id == execution_id
            ).first()
            
            if not execution:
                raise ValueError(f"Execution not found: {execution_id}")
            
            # Extract available options from previous node output using data source path
            data_source = step_config.get('dataSource', '')
            available_options = self._extract_data_by_path(runtime_state, data_source)
            
            if not isinstance(available_options, list):
                # Try to convert to list if it's not already
                if isinstance(available_options, dict):
                    available_options = [available_options]
                else:
                    available_options = []
            
            # Update execution status
            execution.flow_status = 'input_required'
            execution.current_step = step_id
            
            # Create options selection record
            selection_mode = step_config.get('selectionMode', 'single')
            options_selection = models.FlowOptionsSelection(
                execution_id=execution_id,
                step_id=step_id,
                available_options=available_options,
                selected_options=[],  # Not yet selected
                selection_mode=selection_mode
            )
            
            self.db.add(options_selection)
            self.db.commit()
            
            logger.info(f"Workflow {execution_id} paused for options selection at step {step_id}")
            
            return {
                'success': True,
                'execution_id': execution_id,
                'step_id': step_id,
                'status': 'awaiting_selection',
                'available_options': available_options,
                'selection_mode': selection_mode,
                'option_label_field': step_config.get('optionLabelField'),
                'option_value_field': step_config.get('optionValueField')
            }
            
        except Exception as e:
            logger.error(f"Error pausing for options: {e}")
            self.db.rollback()
            raise
    
    async def process_review_approval(
        self,
        execution_id: int,
        step_id: str,
        approval_data: Dict[str, Any],
        user_id: int
    ) -> Dict[str, Any]:
        """
        Process review approval and handle edits/reruns
        
        Args:
            execution_id: Workflow execution ID
            step_id: Step ID that was reviewed
            approval_data: Approval details including edits
            user_id: User who approved/rejected
            
        Returns:
            dict with processing result
        """
        try:
            # Get review approval record
            review_approval = self.db.query(models.FlowReviewApproval).filter(
                models.FlowReviewApproval.execution_id == execution_id,
                models.FlowReviewApproval.step_id == step_id,
                models.FlowReviewApproval.reviewed_at.is_(None)
            ).first()
            
            if not review_approval:
                raise ValueError(f"Review approval not found for execution {execution_id}, step {step_id}")
            
            # Get execution
            execution = self.db.query(models.WorkflowExecution).filter(
                models.WorkflowExecution.id == execution_id
            ).first()
            
            # Update review approval
            review_approval.approved = approval_data.get('approved', False)
            review_approval.comments = approval_data.get('comments', '')
            review_approval.reviewed_by = user_id
            review_approval.reviewed_at = datetime.utcnow()
            review_approval.edited_steps = approval_data.get('edited_steps', [])
            review_approval.edited_data = approval_data.get('edited_data', {})
            review_approval.rerun_steps = approval_data.get('rerun_steps', [])
            
            # Handle reruns if edits were made
            rerun_results = []
            if review_approval.approved and review_approval.rerun_steps:
                for rerun_step_id in review_approval.rerun_steps:
                    rerun_result = await self.rerun_node(
                        execution_id,
                        rerun_step_id,
                        review_approval.edited_data.get(rerun_step_id)
                    )
                    rerun_results.append(rerun_result)
            
            # Update execution status
            if review_approval.approved:
                execution.flow_status = 'in_progress'
                logger.info(f"Review approved for execution {execution_id}, continuing workflow")
            else:
                # Handle declined - could set to error or a declined path
                execution.flow_status = 'error'
                execution.error_message = f"Review declined: {review_approval.comments}"
                logger.info(f"Review declined for execution {execution_id}")
            
            self.db.commit()
            
            return {
                'success': True,
                'execution_id': execution_id,
                'approved': review_approval.approved,
                'rerun_count': len(rerun_results),
                'rerun_results': rerun_results,
                'next_status': execution.flow_status
            }
            
        except Exception as e:
            logger.error(f"Error processing review approval: {e}")
            self.db.rollback()
            raise
    
    async def process_options_selection(
        self,
        execution_id: int,
        step_id: str,
        selected_options: List[Any],
        user_id: int
    ) -> Dict[str, Any]:
        """
        Process options selection and continue workflow
        
        Args:
            execution_id: Workflow execution ID
            step_id: Step ID where options were selected
            selected_options: Options selected by user
            user_id: User who made selection
            
        Returns:
            dict with processing result
        """
        try:
            # Get options selection record
            options_selection = self.db.query(models.FlowOptionsSelection).filter(
                models.FlowOptionsSelection.execution_id == execution_id,
                models.FlowOptionsSelection.step_id == step_id,
                models.FlowOptionsSelection.selected_at.is_(None)
            ).first()
            
            if not options_selection:
                raise ValueError(f"Options selection not found for execution {execution_id}, step {step_id}")
            
            # Get execution
            execution = self.db.query(models.WorkflowExecution).filter(
                models.WorkflowExecution.id == execution_id
            ).first()
            
            # Update options selection
            options_selection.selected_options = selected_options
            options_selection.selected_by = user_id
            options_selection.selected_at = datetime.utcnow()
            
            # Store selected options in runtime state for next nodes
            if not execution.runtime_state:
                execution.runtime_state = {}
            
            # Add selected options to runtime state with step_id as key
            execution.runtime_state[f"{step_id}_selected"] = selected_options
            
            # Update execution status back to in_progress
            execution.flow_status = 'in_progress'
            
            self.db.commit()
            
            logger.info(f"Options selected for execution {execution_id} at step {step_id}")
            
            return {
                'success': True,
                'execution_id': execution_id,
                'step_id': step_id,
                'selected_options': selected_options,
                'next_status': 'in_progress'
            }
            
        except Exception as e:
            logger.error(f"Error processing options selection: {e}")
            self.db.rollback()
            raise
    
    async def evaluate_condition(
        self,
        condition_config: Dict[str, Any],
        runtime_state: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Evaluate conditional expression
        
        Args:
            condition_config: Configuration for the conditional node
            runtime_state: Current workflow runtime state
            
        Returns:
            dict with evaluation result and path to follow
        """
        try:
            conditions = condition_config.get('conditions', [])
            
            if not conditions:
                logger.warning("No conditions defined, defaulting to true path")
                return {
                    'success': True,
                    'result': True,
                    'path': condition_config.get('truePath'),
                    'reason': 'No conditions defined'
                }
            
            # Evaluate each condition
            results = []
            for condition in conditions:
                left_value = self._extract_data_by_path(
                    runtime_state,
                    condition.get('leftOperand', '')
                )
                operator = condition.get('operator', '==')
                right_value = condition.get('rightOperand')
                
                # If right operand is a path, extract its value
                if isinstance(right_value, str) and '.' in right_value:
                    right_value = self._extract_data_by_path(runtime_state, right_value)
                
                # Evaluate condition
                condition_result = self._evaluate_single_condition(
                    left_value,
                    operator,
                    right_value
                )
                
                results.append({
                    'condition': condition,
                    'left_value': left_value,
                    'right_value': right_value,
                    'result': condition_result
                })
            
            # Combine results based on logic operators
            final_result = results[0]['result']
            for i in range(1, len(results)):
                logic_operator = conditions[i].get('logicOperator', 'AND')
                if logic_operator == 'AND':
                    final_result = final_result and results[i]['result']
                elif logic_operator == 'OR':
                    final_result = final_result or results[i]['result']
            
            # Determine which path to follow
            path = condition_config.get('truePath') if final_result else condition_config.get('falsePath')
            
            logger.info(f"Condition evaluated to {final_result}, following path: {path}")
            
            return {
                'success': True,
                'result': final_result,
                'path': path,
                'details': results
            }
            
        except Exception as e:
            logger.error(f"Error evaluating condition: {e}")
            raise
    
    async def rerun_node(
        self,
        execution_id: int,
        step_id: str,
        modified_input: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Rerun a specific node with modified input
        
        Args:
            execution_id: Workflow execution ID
            step_id: Step ID to rerun
            modified_input: Modified input data for the node
            
        Returns:
            dict with rerun result
        """
        try:
            # Get original step execution
            original_step = self.db.query(models.WorkflowStepExecution).filter(
                models.WorkflowStepExecution.execution_id == execution_id,
                models.WorkflowStepExecution.step_id == step_id
            ).order_by(models.WorkflowStepExecution.created_at.desc()).first()
            
            if not original_step:
                raise ValueError(f"Step execution not found: {step_id}")
            
            # Create new step execution for the rerun
            new_step = models.WorkflowStepExecution(
                execution_id=execution_id,
                step_id=step_id,
                step_type=original_step.step_type,
                step_name=f"{original_step.step_name} (Rerun)",
                status='pending',
                parent_execution_id=original_step.id,
                rerun_count=original_step.rerun_count + 1,
                modified_input_data=modified_input,
                input_data=modified_input if modified_input else original_step.input_data
            )
            
            self.db.add(new_step)
            self.db.commit()
            
            logger.info(f"Created rerun for step {step_id} in execution {execution_id}")
            
            # Note: Actual node execution would happen in the workflow execution service
            # This just creates the record for the rerun
            
            return {
                'success': True,
                'execution_id': execution_id,
                'step_id': step_id,
                'new_step_execution_id': new_step.id,
                'rerun_count': new_step.rerun_count
            }
            
        except Exception as e:
            logger.error(f"Error rerunning node: {e}")
            self.db.rollback()
            raise
    
    def _extract_data_by_path(self, data: Dict[str, Any], path: str) -> Any:
        """
        Extract data using dot notation path (e.g., 'results[0].items[*].url')
        
        Args:
            data: Source data dictionary
            path: Dot notation path to extract
            
        Returns:
            Extracted value or None
        """
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
                        current = current.get(key, {}) if isinstance(current, dict) else current
                    
                    if index == '*':
                        # Return all items
                        if isinstance(current, list):
                            return current
                        else:
                            return []
                    else:
                        if isinstance(current, list):
                            current = current[int(index)]
                        elif isinstance(current, dict):
                            current = current.get(index)
                else:
                    if isinstance(current, dict):
                        current = current.get(part)
                    else:
                        return None
            
            return current
            
        except (KeyError, IndexError, ValueError, TypeError, AttributeError) as e:
            logger.warning(f"Failed to extract data at path '{path}': {e}")
            return None
    
    def _evaluate_single_condition(
        self,
        left_value: Any,
        operator: str,
        right_value: Any
    ) -> bool:
        """
        Evaluate a single condition
        
        Args:
            left_value: Left operand value
            operator: Comparison operator
            right_value: Right operand value
            
        Returns:
            Boolean result of condition
        """
        try:
            if operator == '==':
                return left_value == right_value
            elif operator == '!=':
                return left_value != right_value
            elif operator == '>':
                return float(left_value) > float(right_value)
            elif operator == '<':
                return float(left_value) < float(right_value)
            elif operator == '>=':
                return float(left_value) >= float(right_value)
            elif operator == '<=':
                return float(left_value) <= float(right_value)
            elif operator == 'contains':
                return str(right_value) in str(left_value)
            elif operator == 'not_contains':
                return str(right_value) not in str(left_value)
            elif operator == 'starts_with':
                return str(left_value).startswith(str(right_value))
            elif operator == 'ends_with':
                return str(left_value).endswith(str(right_value))
            elif operator == 'is_empty':
                return not left_value or (isinstance(left_value, (list, dict, str)) and len(left_value) == 0)
            elif operator == 'is_not_empty':
                return bool(left_value) and (not isinstance(left_value, (list, dict, str)) or len(left_value) > 0)
            else:
                logger.warning(f"Unknown operator: {operator}, defaulting to False")
                return False
                
        except Exception as e:
            logger.error(f"Error evaluating condition: {e}")
            return False


# Global service instance factory
def get_flow_control_service(db: Session) -> FlowControlService:
    """Factory function to create FlowControlService instance"""
    return FlowControlService(db)

