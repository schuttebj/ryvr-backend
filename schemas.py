from pydantic import BaseModel, EmailStr, validator
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime
from decimal import Decimal

# =============================================================================
# CORE USER SCHEMAS
# =============================================================================

class UserBase(BaseModel):
    email: EmailStr
    username: str
    role: Literal['admin', 'user']  # Simplified roles
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    avatar_url: Optional[str] = None
    is_active: bool = True
    is_master_account: bool = True
    master_account_id: Optional[int] = None
    seat_name: Optional[str] = None

class UserCreate(UserBase):
    password: str

class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    avatar_url: Optional[str] = None
    is_active: Optional[bool] = None
    email_verified: Optional[bool] = None

class User(UserBase):
    id: int
    email_verified: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

# =============================================================================
# AUTHENTICATION SCHEMAS
# =============================================================================

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None
    role: Optional[str] = None
    agency_id: Optional[int] = None
    business_id: Optional[int] = None

class LoginRequest(BaseModel):
    username: str
    password: str

class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    user: User
    agency_id: Optional[int] = None
    business_id: Optional[int] = None

# =============================================================================
# AGENCY SCHEMAS
# =============================================================================

class AgencyBase(BaseModel):
    name: str
    slug: str
    website: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    branding_config: Optional[Dict[str, Any]] = {}
    settings: Optional[Dict[str, Any]] = {}

class AgencyCreate(AgencyBase):
    pass

class AgencyUpdate(BaseModel):
    name: Optional[str] = None
    website: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    branding_config: Optional[Dict[str, Any]] = None
    settings: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None

class Agency(AgencyBase):
    id: int
    onboarding_data: Dict[str, Any]
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

class AgencyUserBase(BaseModel):
    role: Literal['owner', 'manager', 'viewer']
    permissions: Optional[Dict[str, Any]] = {}

class AgencyUserCreate(AgencyUserBase):
    user_id: int
    agency_id: int

class AgencyUser(AgencyUserBase):
    id: int
    agency_id: int
    user_id: int
    invited_by: Optional[int] = None
    invited_at: Optional[datetime] = None
    joined_at: Optional[datetime] = None
    is_active: bool
    created_at: datetime
    
    class Config:
        from_attributes = True

# =============================================================================
# BUSINESS SCHEMAS
# =============================================================================

class BusinessBase(BaseModel):
    name: str
    slug: Optional[str] = None
    industry: Optional[str] = None
    website: Optional[str] = None
    description: Optional[str] = None
    contact_email: Optional[EmailStr] = None
    contact_phone: Optional[str] = None
    contact_address: Optional[str] = None
    settings: Optional[Dict[str, Any]] = {}
    branding_config: Optional[Dict[str, Any]] = {}

class BusinessCreate(BusinessBase):
    agency_id: int

class BusinessUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    industry: Optional[str] = None
    website: Optional[str] = None
    description: Optional[str] = None
    contact_email: Optional[EmailStr] = None
    contact_phone: Optional[str] = None
    contact_address: Optional[str] = None
    settings: Optional[Dict[str, Any]] = None
    branding_config: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None

class Business(BusinessBase):
    id: int
    agency_id: int
    onboarding_data: Dict[str, Any]
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

# =============================================================================
# LEGACY CLIENT SCHEMAS (for backward compatibility)
# =============================================================================

class ClientBase(BusinessBase):
    """Legacy Client schema - maps to Business for backward compatibility"""
    pass

class ClientCreate(BusinessCreate):
    """Legacy Client creation schema - maps to Business for backward compatibility"""
    pass

class ClientUpdate(BusinessUpdate):
    """Legacy Client update schema - maps to Business for backward compatibility"""
    pass

class Client(Business):
    """Legacy Client schema - maps to Business for backward compatibility"""
    pass

class BusinessProfileGenerationRequest(BaseModel):
    ai_model: str = "gpt-4"
    include_assumptions: bool = True

class BusinessUserBase(BaseModel):
    role: Literal['owner', 'manager', 'viewer']
    permissions: Optional[Dict[str, Any]] = {}

class BusinessUserCreate(BusinessUserBase):
    user_id: int
    business_id: int

class BusinessUser(BusinessUserBase):
    id: int
    business_id: int
    user_id: int
    is_active: bool
    created_at: datetime
    
    class Config:
        from_attributes = True

# =============================================================================
# ONBOARDING SCHEMAS
# =============================================================================

class OnboardingQuestionBase(BaseModel):
    section: str
    question_key: str
    question_text: str
    question_type: Literal['text', 'textarea', 'select', 'multiselect', 'file']
    options: Optional[List[str]] = []
    is_required: bool = False
    placeholder: Optional[str] = None
    help_text: Optional[str] = None
    sort_order: int = 0

class OnboardingQuestionCreate(OnboardingQuestionBase):
    template_id: int

class OnboardingQuestion(OnboardingQuestionBase):
    id: int
    template_id: int
    is_active: bool
    created_at: datetime
    
    class Config:
        from_attributes = True

class OnboardingTemplateBase(BaseModel):
    name: str
    description: Optional[str] = None
    target_type: Literal['agency', 'business']
    is_default: bool = False

class OnboardingTemplateCreate(OnboardingTemplateBase):
    questions: Optional[List[OnboardingQuestionCreate]] = []

class OnboardingTemplate(OnboardingTemplateBase):
    id: int
    is_active: bool
    created_by: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    questions: Optional[List[OnboardingQuestion]] = []
    
    class Config:
        from_attributes = True

class OnboardingResponseBase(BaseModel):
    question_id: int
    response_value: Optional[str] = None
    response_data: Optional[Dict[str, Any]] = {}

class OnboardingResponseCreate(OnboardingResponseBase):
    template_id: int
    respondent_id: int
    respondent_type: Literal['agency', 'business']

class OnboardingResponse(OnboardingResponseBase):
    id: int
    template_id: int
    respondent_id: int
    respondent_type: str
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

# =============================================================================
# CLIENT ACCESS SCHEMAS
# =============================================================================

class ClientAccessBase(BaseModel):
    business_id: int
    client_email: EmailStr
    access_type: Literal['viewer', 'approver'] = 'viewer'
    permissions: List[str] = []
    is_active: bool = True
    expires_at: Optional[datetime] = None

class ClientAccessCreate(ClientAccessBase):
    pass

class ClientAccessUpdate(BaseModel):
    access_type: Optional[Literal['viewer', 'approver']] = None
    permissions: Optional[List[str]] = None
    is_active: Optional[bool] = None
    expires_at: Optional[datetime] = None

class ClientAccess(ClientAccessBase):
    id: int
    access_token: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# =============================================================================
# USER CONTEXT SCHEMA FOR FRONTEND
# =============================================================================

class UserContext(BaseModel):
    """Complete user context for frontend"""
    user: User
    subscription_tier: Optional[SubscriptionTier] = None
    businesses: List[Business] = []
    current_business_id: Optional[int] = None
    seat_users: List[User] = []  # Only for master accounts

    class Config:
        from_attributes = True

# =============================================================================
# BUSINESS SWITCH SCHEMAS
# =============================================================================

class BusinessSwitchRequest(BaseModel):
    business_id: Optional[int] = None  # None for "all businesses" context

class BusinessSwitchResponse(BaseModel):
    access_token: str
    current_business_id: Optional[int] = None
    message: str = "Business context switched successfully"

# =============================================================================
# SUBSCRIPTION & CREDIT SCHEMAS
# =============================================================================

class SubscriptionTierBase(BaseModel):
    name: str
    slug: str
    description: Optional[str] = None
    price_monthly: Decimal
    price_yearly: Optional[Decimal] = None
    credits_included: int
    business_limit: int  # Renamed from client_limit
    seat_limit: int  # Renamed from user_limit
    storage_limit_gb: int = 5
    max_file_size_mb: int = 100
    features: Optional[List[str]] = []
    cross_business_chat: bool = False
    cross_business_files: bool = False
    client_access_enabled: bool = False
    workflow_access: Optional[List[str]] = []
    integration_access: Optional[List[str]] = []  # Simplified from integration_limits
    is_active: bool = True
    sort_order: int = 0

class SubscriptionTierCreate(SubscriptionTierBase):
    pass

class SubscriptionTierUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    price_monthly: Optional[Decimal] = None
    price_yearly: Optional[Decimal] = None
    credits_included: Optional[int] = None
    business_limit: Optional[int] = None
    seat_limit: Optional[int] = None
    storage_limit_gb: Optional[int] = None
    max_file_size_mb: Optional[int] = None
    features: Optional[List[str]] = None
    cross_business_chat: Optional[bool] = None
    cross_business_files: Optional[bool] = None
    client_access_enabled: Optional[bool] = None
    workflow_access: Optional[List[str]] = None
    integration_access: Optional[List[str]] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None

class SubscriptionTier(SubscriptionTierBase):
    id: int
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

class UserSubscriptionBase(BaseModel):
    tier_id: int
    status: Literal['trial', 'active', 'cancelled', 'expired']

class UserSubscriptionCreate(UserSubscriptionBase):
    user_id: int
    trial_starts_at: Optional[datetime] = None
    trial_ends_at: Optional[datetime] = None

class UserSubscription(UserSubscriptionBase):
    id: int
    user_id: int
    trial_starts_at: Optional[datetime] = None
    trial_ends_at: Optional[datetime] = None
    current_period_start: Optional[datetime] = None
    current_period_end: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    stripe_subscription_id: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    tier: Optional[SubscriptionTier] = None
    
    class Config:
        from_attributes = True

class CreditPoolBase(BaseModel):
    owner_id: int
    owner_type: Literal['user', 'agency']
    balance: int = 0
    overage_threshold: int = 100

class CreditPoolCreate(CreditPoolBase):
    pass

class CreditPool(CreditPoolBase):
    id: int
    total_purchased: int
    total_used: int
    is_suspended: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

class CreditTransactionBase(BaseModel):
    pool_id: int
    transaction_type: Literal['purchase', 'usage', 'refund', 'adjustment']
    amount: int
    description: Optional[str] = None
    transaction_metadata: Optional[Dict[str, Any]] = {}

class CreditTransactionCreate(CreditTransactionBase):
    business_id: Optional[int] = None
    workflow_execution_id: Optional[int] = None

class CreditTransaction(CreditTransactionBase):
    id: int
    business_id: Optional[int] = None
    workflow_execution_id: Optional[int] = None
    balance_after: int
    created_by: Optional[int] = None
    created_at: datetime
    
    class Config:
        from_attributes = True

# =============================================================================
# WORKFLOW SCHEMAS
# =============================================================================

class WorkflowTemplateBase(BaseModel):
    name: str
    description: Optional[str] = None
    category: str
    tags: Optional[List[str]] = []
    config: Dict[str, Any]
    credit_cost: int = 0
    estimated_duration: Optional[int] = None
    tier_access: Optional[List[str]] = []
    version: str = '1.0'
    icon: Optional[str] = None

class WorkflowTemplateCreate(WorkflowTemplateBase):
    status: Literal['draft', 'testing', 'beta', 'published', 'deprecated'] = 'draft'
    beta_users: Optional[List[int]] = []

class WorkflowTemplateUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    config: Optional[Dict[str, Any]] = None
    credit_cost: Optional[int] = None
    estimated_duration: Optional[int] = None
    tier_access: Optional[List[str]] = None
    status: Optional[Literal['draft', 'testing', 'beta', 'published', 'deprecated']] = None
    beta_users: Optional[List[int]] = None
    version: Optional[str] = None
    icon: Optional[str] = None

class WorkflowTemplate(WorkflowTemplateBase):
    id: int
    status: str
    beta_users: List[int]
    created_by: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

# =============================================================================
# TASK TEMPLATE SCHEMAS (Legacy support)
# =============================================================================

class TaskTemplateBase(BaseModel):
    name: str
    description: Optional[str] = None
    category: str
    integration_id: Optional[int] = None
    config_schema: Optional[Dict[str, Any]] = {}
    credit_cost: int = 1

class TaskTemplateCreate(TaskTemplateBase):
    pass

class TaskTemplateUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    integration_id: Optional[int] = None
    config_schema: Optional[Dict[str, Any]] = None
    credit_cost: Optional[int] = None
    is_active: Optional[bool] = None

class TaskTemplate(TaskTemplateBase):
    id: int
    is_active: bool
    created_at: datetime
    
    class Config:
        from_attributes = True

class WorkflowInstanceBase(BaseModel):
    template_id: int
    business_id: int
    name: Optional[str] = None
    custom_config: Optional[Dict[str, Any]] = {}

class WorkflowInstanceCreate(WorkflowInstanceBase):
    pass

class WorkflowInstanceUpdate(BaseModel):
    name: Optional[str] = None
    custom_config: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None

class WorkflowInstance(WorkflowInstanceBase):
    id: int
    is_active: bool
    last_executed_at: Optional[datetime] = None
    execution_count: int
    success_count: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    template: Optional[WorkflowTemplate] = None
    
    class Config:
        from_attributes = True

class WorkflowExecutionBase(BaseModel):
    instance_id: int
    business_id: int

class WorkflowExecutionCreate(WorkflowExecutionBase):
    pass

class WorkflowExecution(WorkflowExecutionBase):
    id: int
    status: Literal['pending', 'running', 'completed', 'failed']
    credits_used: int
    execution_data: Dict[str, Any]
    error_message: Optional[str] = None
    started_at: datetime
    completed_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

# =============================================================================
# INTEGRATION SCHEMAS
# =============================================================================

class IntegrationBase(BaseModel):
    name: str
    provider: str
    integration_type: Literal['system', 'agency', 'business']
    level: Literal['system', 'agency', 'business']
    config_schema: Optional[Dict[str, Any]] = {}
    is_mock: bool = False

class IntegrationCreate(IntegrationBase):
    pass

class IntegrationUpdate(BaseModel):
    name: Optional[str] = None
    provider: Optional[str] = None
    config_schema: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None
    is_mock: Optional[bool] = None

class Integration(IntegrationBase):
    id: int
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

class SystemIntegrationBase(BaseModel):
    integration_id: int
    custom_config: Optional[Dict[str, Any]] = {}
    credentials: Optional[Dict[str, Any]] = {}

class SystemIntegrationCreate(SystemIntegrationBase):
    pass

class SystemIntegration(SystemIntegrationBase):
    id: int
    is_active: bool
    last_tested: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    integration: Optional[Integration] = None
    
    class Config:
        from_attributes = True

class AgencyIntegrationBase(BaseModel):
    agency_id: int
    integration_id: int
    custom_config: Optional[Dict[str, Any]] = {}
    credentials: Optional[Dict[str, Any]] = {}

class AgencyIntegrationCreate(AgencyIntegrationBase):
    pass

class AgencyIntegration(AgencyIntegrationBase):
    id: int
    is_active: bool
    last_tested: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    integration: Optional[Integration] = None
    
    class Config:
        from_attributes = True

class BusinessIntegrationBase(BaseModel):
    business_id: int
    integration_id: int
    custom_config: Optional[Dict[str, Any]] = {}
    credentials: Optional[Dict[str, Any]] = {}

class BusinessIntegrationCreate(BusinessIntegrationBase):
    pass

class BusinessIntegration(BusinessIntegrationBase):
    id: int
    is_active: bool
    last_tested: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    integration: Optional[Integration] = None
    
    class Config:
        from_attributes = True

# =============================================================================
# ASSET & FILE SCHEMAS
# =============================================================================

class AssetUploadBase(BaseModel):
    owner_id: int
    owner_type: Literal['agency', 'business']
    file_name: str
    file_type: str
    file_size: Optional[int] = None
    asset_type: str  # logo, favicon, banner

class AssetUploadCreate(AssetUploadBase):
    file_path: str

class AssetUpload(AssetUploadBase):
    id: int
    file_path: str
    is_active: bool
    uploaded_by: Optional[int] = None
    created_at: datetime
    
    class Config:
        from_attributes = True

# =============================================================================
# API RESPONSE SCHEMAS
# =============================================================================

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

# =============================================================================
# DASHBOARD & ANALYTICS SCHEMAS
# =============================================================================

class DashboardStats(BaseModel):
    total_businesses: int
    active_workflows: int
    total_credits_used: int
    recent_executions: int
    credit_balance: int

class BusinessStats(BaseModel):
    business_id: int
    credits_used: int
    active_workflows: int
    total_executions: int
    success_rate: float

class AgencyStats(BaseModel):
    agency_id: int
    total_businesses: int
    total_credits_used: int
    active_workflows: int
    success_rate: float

# =============================================================================
# BUSINESS CONTEXT SCHEMAS
# =============================================================================

class BusinessContext(BaseModel):
    business_id: int
    business_name: str
    agency_id: int
    agency_name: str
    user_role: str
    permissions: Dict[str, Any]

class BusinessSwitchRequest(BaseModel):
    business_id: int

# =============================================================================
# NODE EXECUTION SCHEMAS (for workflow engine)
# =============================================================================

class NodeExecutionRequest(BaseModel):
    node_config: Dict[str, Any]
    input_data: Optional[Dict[str, Any]] = None

class NodeExecutionResponse(BaseModel):
    success: bool
    node_id: str
    execution_id: str
    data: Dict[str, Any]
    execution_time_ms: int
    credits_used: int = 0

# =============================================================================
# LEGACY WORKFLOW SCHEMAS (for backward compatibility)
# =============================================================================

class WorkflowBase(BaseModel):
    """Legacy workflow schema - maps to WorkflowInstance for backward compatibility"""
    name: str
    description: Optional[str] = None
    config: Dict[str, Any]
    is_active: bool = True

class WorkflowCreate(WorkflowBase):
    """Legacy workflow creation schema"""
    template_id: Optional[int] = None
    business_id: Optional[int] = None

class WorkflowUpdate(BaseModel):
    """Legacy workflow update schema"""
    name: Optional[str] = None
    description: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None

class Workflow(WorkflowBase):
    """Legacy workflow schema - maps to WorkflowInstance for backward compatibility"""
    id: int
    template_id: Optional[int] = None
    business_id: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

# =============================================================================
# DATA PROCESSING SCHEMAS
# =============================================================================

class DataFilterRequest(BaseModel):
    data: Dict[str, Any]
    filters: Dict[str, Any]
    operation: str = "filter"

class DataTransformRequest(BaseModel):
    data: Dict[str, Any]
    transformations: List[Dict[str, Any]]
    output_format: str = "json"

class DataValidationRequest(BaseModel):
    data: Dict[str, Any]
    schema_rules: Dict[str, Any]
    strict_mode: bool = True

# =============================================================================
# ANALYTICS SCHEMAS
# =============================================================================

class ClientStats(BaseModel):
    """Legacy client stats - maps to BusinessStats for backward compatibility"""
    client_id: int
    total_workflows: int
    active_workflows: int
    total_executions: int
    success_rate: float
    credits_used: int
    credits_remaining: int
    last_activity: Optional[datetime] = None

# =============================================================================
# FILE MANAGEMENT SCHEMAS
# =============================================================================

class FileBase(BaseModel):
    original_name: str
    tags: Optional[List[str]] = []

class FileCreate(FileBase):
    account_id: int
    account_type: Literal['user', 'agency']
    business_id: Optional[int] = None
    auto_process: bool = True

class FileUpdate(BaseModel):
    original_name: Optional[str] = None
    tags: Optional[List[str]] = None

class FileMetadataInfo(BaseModel):
    mime_type: str
    file_extension: str
    upload_timestamp: str
    processing_error: Optional[str] = None

class File(FileBase):
    id: int
    account_id: int
    account_type: str
    business_id: Optional[int] = None
    uploaded_by: int
    file_name: str
    file_type: str
    file_size: int
    file_path: str
    content_text: Optional[str] = None
    summary: Optional[str] = None
    summary_credits_used: int
    processing_status: str
    file_metadata: Dict[str, Any]
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

class FileUploadResponse(BaseModel):
    id: int
    file_name: str
    original_name: str
    file_size: int
    file_type: str
    processing_status: str
    created_at: datetime

class FileListResponse(BaseModel):
    files: List[File]
    total_count: int
    offset: int
    limit: int

class StorageUsageResponse(BaseModel):
    total_bytes: int
    file_count: int
    account_files_bytes: int
    business_files_bytes: int
    total_gb: float
    limit_gb: float
    usage_percentage: float

class FileSearchRequest(BaseModel):
    business_id: Optional[int] = None
    search_query: Optional[str] = None
    file_type: Optional[str] = None
    limit: int = 50
    offset: int = 0

class FileSummaryRequest(BaseModel):
    force_regenerate: bool = False

class FileMoveRequest(BaseModel):
    target_business_id: Optional[int] = None  # None means move to account level

class FilePermissionRequest(BaseModel):
    business_id: int
    permission_type: Literal['read', 'write']

class FilePermission(BaseModel):
    id: int
    file_id: int
    business_id: int
    permission_type: str
    granted_by: int
    created_at: datetime
    
    class Config:
        from_attributes = True

# =============================================================================
# VECTOR EMBEDDINGS & SEMANTIC SEARCH SCHEMAS
# =============================================================================

class EmbeddingGenerateRequest(BaseModel):
    """Request to generate embeddings for a file"""
    force_regenerate: bool = False

class EmbeddingGenerateResponse(BaseModel):
    """Response from embedding generation"""
    success: bool
    file_id: int
    message: Optional[str] = None
    summary_embedded: bool = False
    content_embedded: bool = False
    chunks_created: int = 0
    total_tokens_used: int = 0
    credits_used: int = 0

class SemanticSearchRequest(BaseModel):
    """Request for semantic search across files"""
    query: str
    business_id: int
    top_k: int = 5
    similarity_threshold: float = 0.7
    file_types: Optional[List[str]] = None
    search_content: bool = False  # If True, search full content; False = summaries (faster)

class SemanticSearchResult(BaseModel):
    """Single search result"""
    file_id: int
    filename: str
    file_type: str
    file_size: int
    summary: Optional[str]
    created_at: Optional[str]
    similarity: float

class SemanticSearchResponse(BaseModel):
    """Response from semantic search"""
    success: bool
    query: str
    results: List[SemanticSearchResult]
    count: int

class WorkflowContextRequest(BaseModel):
    """Request for workflow context injection"""
    query: str
    business_id: int
    max_tokens: int = 4000
    top_k: int = 10
    similarity_threshold: float = 0.7
    include_sources: bool = True

class ContextSource(BaseModel):
    """Source file for context"""
    file_id: int
    filename: str
    similarity: float

class WorkflowContextResponse(BaseModel):
    """Response with context for workflow"""
    success: bool
    context: str
    token_count: int
    sources: List[ContextSource]
    query: str
    results_used: int

class ChatRequest(BaseModel):
    """Request for RAG chat with documents"""
    message: str
    business_id: Optional[int] = None  # None for cross-business chat
    max_context_tokens: int = 4000
    top_k: int = 5
    similarity_threshold: float = 0.7
    model: str = "gpt-4"  # or gpt-3.5-turbo
    temperature: float = 0.7

class ChatResponse(BaseModel):
    """Response from RAG chat"""
    success: bool
    message: str  # User's message
    response: str  # AI's response
    sources: List[ContextSource]  # Documents used for context
    context_found: bool
    tokens_used: int
    credits_used: int