from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, JSON
from sqlalchemy.sql import func
from database import Base

class Integration(Base):
    """System-wide integrations (not per client)"""
    __tablename__ = "simple_integrations"
    
    id = Column(String, primary_key=True)  # UUID or custom ID
    name = Column(String, nullable=False)
    type = Column(String, nullable=False)  # 'openai', 'dataforseo', 'custom'
    status = Column(String, default="disconnected")  # 'connected', 'disconnected', 'error'
    config = Column(JSON, nullable=True)  # Stores API keys, settings, etc.
    last_tested = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class SimpleWorkflow(Base):
    """Simplified workflows for proof of concept"""
    __tablename__ = "simple_workflows"
    
    id = Column(String, primary_key=True)  # UUID or custom ID
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    nodes = Column(JSON, nullable=True)  # Workflow nodes array
    edges = Column(JSON, nullable=True)  # Workflow connections array
    is_active = Column(Boolean, default=False)
    tags = Column(JSON, nullable=True)  # Array of tag strings
    execution_count = Column(Integer, default=0)
    last_executed = Column(DateTime(timezone=True), nullable=True)
    success_rate = Column(Integer, default=0)  # Percentage
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class WorkflowExecution(Base):
    """Track workflow executions"""
    __tablename__ = "simple_workflow_executions"
    
    id = Column(String, primary_key=True)
    workflow_id = Column(String, nullable=False)  # References simple_workflows.id
    status = Column(String, default="pending")  # 'pending', 'running', 'completed', 'failed'
    results = Column(JSON, nullable=True)  # Execution results
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True) 