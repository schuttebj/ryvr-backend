from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime

# Base schemas
class UserBase(BaseModel):
    email: str
    username: str
    full_name: Optional[str] = None
    is_active: bool = True
    is_admin: bool = False

class UserCreate(UserBase):
    password: str

class UserUpdate(BaseModel):
    email: Optional[str] = None
    username: Optional[str] = None
    full_name: Optional[str] = None
    is_active: Optional[bool] = None
    is_admin: Optional[bool] = None

class User(UserBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

# Authentication schemas
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

class LoginRequest(BaseModel):
    username: str
    password: str

# Client schemas
class ClientBase(BaseModel):
    name: str
    description: Optional[str] = None
    contact_email: Optional[str] = None

class ClientCreate(ClientBase):
    credits_balance: int = 1000  # Default starting credits

class ClientUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    contact_email: Optional[str] = None
    credits_balance: Optional[int] = None
    is_active: Optional[bool] = None

class Client(ClientBase):
    id: int
    credits_balance: int
    credits_used: int
    is_active: bool
    owner_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

# Website schemas
class WebsiteBase(BaseModel):
    url: str
    name: str
    description: Optional[str] = None

class WebsiteCreate(WebsiteBase):
    client_id: int

class WebsiteUpdate(BaseModel):
    url: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None

class Website(WebsiteBase):
    id: int
    client_id: int
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

# Integration schemas
class IntegrationBase(BaseModel):
    name: str
    provider: str
    is_active: bool = True
    is_mock: bool = False

class IntegrationCreate(IntegrationBase):
    config: Optional[Dict[str, Any]] = None

class IntegrationUpdate(BaseModel):
    name: Optional[str] = None
    provider: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None
    is_mock: Optional[bool] = None

class Integration(IntegrationBase):
    id: int
    config: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

# Task Template schemas
class TaskTemplateBase(BaseModel):
    name: str
    description: Optional[str] = None
    category: str
    credit_cost: int = 1

class TaskTemplateCreate(TaskTemplateBase):
    integration_id: Optional[int] = None
    config_schema: Optional[Dict[str, Any]] = None

class TaskTemplate(TaskTemplateBase):
    id: int
    integration_id: Optional[int] = None
    config_schema: Optional[Dict[str, Any]] = None
    is_active: bool
    created_at: datetime
    
    class Config:
        from_attributes = True

# Workflow schemas
class WorkflowBase(BaseModel):
    name: str
    description: Optional[str] = None
    is_scheduled: bool = False

class WorkflowCreate(WorkflowBase):
    client_id: int
    workflow_data: Optional[Dict[str, Any]] = None
    schedule_config: Optional[Dict[str, Any]] = None

class WorkflowUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    workflow_data: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None
    is_scheduled: Optional[bool] = None
    schedule_config: Optional[Dict[str, Any]] = None

class Workflow(WorkflowBase):
    id: int
    client_id: int
    workflow_data: Optional[Dict[str, Any]] = None
    is_active: bool
    schedule_config: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

# Workflow Execution schemas
class WorkflowExecutionBase(BaseModel):
    workflow_id: int
    status: str = "pending"

class WorkflowExecutionCreate(WorkflowExecutionBase):
    pass

class WorkflowExecution(WorkflowExecutionBase):
    id: int
    credits_used: int
    execution_data: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    started_at: datetime
    completed_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

# Credit Transaction schemas
class CreditTransactionBase(BaseModel):
    client_id: int
    transaction_type: str
    amount: int
    description: Optional[str] = None

class CreditTransactionCreate(CreditTransactionBase):
    workflow_execution_id: Optional[int] = None

class CreditTransaction(CreditTransactionBase):
    id: int
    workflow_execution_id: Optional[int] = None
    created_at: datetime
    
    class Config:
        from_attributes = True

# API Response schemas
class APIResponse(BaseModel):
    success: bool
    message: str
    data: Optional[Any] = None

class PaginatedResponse(BaseModel):
    items: List[Any]
    total: int
    page: int
    per_page: int
    pages: int

# Dashboard analytics schemas
class DashboardStats(BaseModel):
    total_clients: int
    active_workflows: int
    total_credits_used: int
    recent_executions: int

class ClientStats(BaseModel):
    client_id: int
    credits_balance: int
    credits_used: int
    active_workflows: int
    total_executions: int
    success_rate: float 
