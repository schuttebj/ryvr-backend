from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float, Text, JSON, ForeignKey, UniqueConstraint, CheckConstraint, Numeric, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base
from decimal import Decimal
import uuid

# =============================================================================
# CORE USER MANAGEMENT MODELS
# =============================================================================

class User(Base):
    """Enhanced user model with role-based authentication"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    username = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False)  # admin, agency, individual
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    phone = Column(String(20), nullable=True)
    avatar_url = Column(String(500), nullable=True)
    email_verified = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    agency_memberships = relationship("AgencyUser", back_populates="user", foreign_keys="AgencyUser.user_id")
    business_memberships = relationship("BusinessUser", back_populates="user", foreign_keys="BusinessUser.user_id")
    created_agencies = relationship("Agency", foreign_keys="Agency.created_by")
    subscription = relationship("UserSubscription", back_populates="user", uselist=False)
    
    # Invitations sent by this user
    agency_invitations = relationship("AgencyUser", foreign_keys="AgencyUser.invited_by", overlaps="inviter")
    
    __table_args__ = (
        CheckConstraint("role IN ('admin', 'agency', 'individual')", name='check_user_role'),
    )

class Agency(Base):
    """Agency model for multi-client management"""
    __tablename__ = "agencies"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    slug = Column(String(100), unique=True, nullable=False)  # for custom domains
    branding_config = Column(JSON, default=dict)  # logo, colors, fonts
    settings = Column(JSON, default=dict)  # general settings
    onboarding_data = Column(JSON, default=dict)  # completed questionnaire
    website = Column(String(255), nullable=True)
    phone = Column(String(20), nullable=True)
    address = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    users = relationship("AgencyUser", back_populates="agency")
    businesses = relationship("Business", back_populates="agency")
    integrations = relationship("AgencyIntegration", back_populates="agency")
    credit_pool = relationship("CreditPool", foreign_keys="CreditPool.owner_id", 
                             primaryjoin="and_(Agency.id==CreditPool.owner_id, CreditPool.owner_type=='agency')")

class AgencyUser(Base):
    """Many-to-many relationship between agencies and users"""
    __tablename__ = "agency_users"
    
    id = Column(Integer, primary_key=True, index=True)
    agency_id = Column(Integer, ForeignKey("agencies.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(20), nullable=False)  # owner, manager, viewer
    permissions = Column(JSON, default=dict)  # specific permissions
    invited_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    invited_at = Column(DateTime(timezone=True), nullable=True)
    joined_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    agency = relationship("Agency", back_populates="users")
    user = relationship("User", back_populates="agency_memberships", foreign_keys=[user_id])
    inviter = relationship("User", foreign_keys=[invited_by], overlaps="agency_invitations")
    
    __table_args__ = (
        UniqueConstraint('agency_id', 'user_id', name='unique_agency_user'),
        CheckConstraint("role IN ('owner', 'manager', 'viewer')", name='check_agency_role'),
    )

class Business(Base):
    """Business model (replaces Client) with multi-tenancy support"""
    __tablename__ = "businesses"
    
    id = Column(Integer, primary_key=True, index=True)
    agency_id = Column(Integer, ForeignKey("agencies.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(200), nullable=False)
    slug = Column(String(100), nullable=True)  # for URLs
    industry = Column(String(100), nullable=True)
    website = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    onboarding_data = Column(JSON, default=dict)  # questionnaire responses
    settings = Column(JSON, default=dict)
    branding_config = Column(JSON, default=dict)  # inherited from agency + overrides
    contact_email = Column(String(255), nullable=True)
    contact_phone = Column(String(20), nullable=True)
    contact_address = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    agency = relationship("Agency", back_populates="businesses")
    users = relationship("BusinessUser", back_populates="business")
    workflow_instances = relationship("WorkflowInstance", back_populates="business")
    integrations = relationship("BusinessIntegration", back_populates="business")
    credit_transactions = relationship("CreditTransaction", back_populates="business")
    
    __table_args__ = (
        UniqueConstraint('agency_id', 'slug', name='unique_agency_business_slug'),
    )

class BusinessUser(Base):
    """Many-to-many relationship between businesses and users"""
    __tablename__ = "business_users"
    
    id = Column(Integer, primary_key=True, index=True)
    business_id = Column(Integer, ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(20), nullable=False)  # owner, manager, viewer
    permissions = Column(JSON, default=dict)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    business = relationship("Business", back_populates="users")
    user = relationship("User", back_populates="business_memberships")
    
    __table_args__ = (
        UniqueConstraint('business_id', 'user_id', name='unique_business_user'),
        CheckConstraint("role IN ('owner', 'manager', 'viewer')", name='check_business_role'),
    )

# =============================================================================
# ONBOARDING SYSTEM MODELS
# =============================================================================

class OnboardingTemplate(Base):
    """Configurable onboarding templates for agencies and businesses"""
    __tablename__ = "onboarding_templates"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    target_type = Column(String(20), nullable=False)  # agency, business
    is_default = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    questions = relationship("OnboardingQuestion", back_populates="template")
    responses = relationship("OnboardingResponse", back_populates="template")
    
    __table_args__ = (
        CheckConstraint("target_type IN ('agency', 'business')", name='check_target_type'),
    )

class OnboardingQuestion(Base):
    """Dynamic questions for onboarding templates"""
    __tablename__ = "onboarding_questions"
    
    id = Column(Integer, primary_key=True, index=True)
    template_id = Column(Integer, ForeignKey("onboarding_templates.id", ondelete="CASCADE"), nullable=False)
    section = Column(String(100), nullable=False)  # basic, business_model, etc.
    question_key = Column(String(100), nullable=False)  # business_name, target_audience
    question_text = Column(Text, nullable=False)
    question_type = Column(String(20), nullable=False)  # text, textarea, select, multiselect, file
    options = Column(JSON, default=list)  # for select/multiselect
    is_required = Column(Boolean, default=False)
    placeholder = Column(String(255), nullable=True)
    help_text = Column(Text, nullable=True)
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    template = relationship("OnboardingTemplate", back_populates="questions")
    responses = relationship("OnboardingResponse", back_populates="question")
    
    __table_args__ = (
        CheckConstraint("question_type IN ('text', 'textarea', 'select', 'multiselect', 'file')", name='check_question_type'),
    )

class OnboardingResponse(Base):
    """Responses to onboarding questions"""
    __tablename__ = "onboarding_responses"
    
    id = Column(Integer, primary_key=True, index=True)
    template_id = Column(Integer, ForeignKey("onboarding_templates.id"), nullable=False)
    respondent_id = Column(Integer, nullable=False)  # agency_id or business_id
    respondent_type = Column(String(20), nullable=False)  # agency, business
    question_id = Column(Integer, ForeignKey("onboarding_questions.id"), nullable=False)
    response_value = Column(Text, nullable=True)
    response_data = Column(JSON, default=dict)  # for file uploads, complex data
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    template = relationship("OnboardingTemplate", back_populates="responses")
    question = relationship("OnboardingQuestion", back_populates="responses")
    
    __table_args__ = (
        CheckConstraint("respondent_type IN ('agency', 'business')", name='check_respondent_type'),
    )

class AssetUpload(Base):
    """File uploads for branding and assets"""
    __tablename__ = "asset_uploads"
    
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, nullable=False)  # agency_id or business_id
    owner_type = Column(String(20), nullable=False)  # agency, business
    file_name = Column(String(255), nullable=False)
    file_type = Column(String(100), nullable=False)
    file_size = Column(Integer, nullable=True)
    file_path = Column(String(500), nullable=False)  # local path on persistent disk
    asset_type = Column(String(50), nullable=False)  # logo, favicon, banner
    is_active = Column(Boolean, default=True)
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    __table_args__ = (
        CheckConstraint("owner_type IN ('agency', 'business')", name='check_owner_type'),
    )

# =============================================================================
# SUBSCRIPTION & CREDIT SYSTEM MODELS
# =============================================================================

class SubscriptionTier(Base):
    """Configurable subscription tiers"""
    __tablename__ = "subscription_tiers"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    slug = Column(String(50), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    price_monthly = Column(Numeric(10, 2), nullable=False)
    price_yearly = Column(Numeric(10, 2), nullable=True)
    credits_included = Column(Integer, nullable=False)
    client_limit = Column(Integer, nullable=False)  # max businesses
    user_limit = Column(Integer, nullable=False)  # max agency users
    features = Column(JSON, default=list)  # array of feature flags
    workflow_access = Column(JSON, default=list)  # accessible workflow categories
    integration_limits = Column(JSON, default=dict)  # per-integration limits
    storage_limit_gb = Column(Integer, default=5)  # Storage limit in GB
    max_file_size_mb = Column(Integer, default=100)  # Max file size in MB
    is_active = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    subscriptions = relationship("UserSubscription", back_populates="tier")

class UserSubscription(Base):
    """User subscription tracking"""
    __tablename__ = "user_subscriptions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    tier_id = Column(Integer, ForeignKey("subscription_tiers.id"), nullable=False)
    status = Column(String(20), nullable=False)  # trial, active, cancelled, expired
    trial_starts_at = Column(DateTime(timezone=True), nullable=True)
    trial_ends_at = Column(DateTime(timezone=True), nullable=True)
    current_period_start = Column(DateTime(timezone=True), nullable=True)
    current_period_end = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    stripe_subscription_id = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    user = relationship("User", back_populates="subscription")
    tier = relationship("SubscriptionTier", back_populates="subscriptions")
    
    __table_args__ = (
        CheckConstraint("status IN ('trial', 'active', 'cancelled', 'expired')", name='check_subscription_status'),
    )

class CreditPool(Base):
    """Credit pools for agencies and individuals"""
    __tablename__ = "credit_pools"
    
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, nullable=False)  # user_id for individuals, agency_id for agencies
    owner_type = Column(String(20), nullable=False)  # user, agency
    balance = Column(Integer, nullable=False, default=0)
    total_purchased = Column(Integer, nullable=False, default=0)
    total_used = Column(Integer, nullable=False, default=0)
    overage_threshold = Column(Integer, default=100)  # negative balance allowed
    is_suspended = Column(Boolean, default=False)  # suspended when over threshold
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    transactions = relationship("CreditTransaction", back_populates="pool")
    
    __table_args__ = (
        UniqueConstraint('owner_id', 'owner_type', name='unique_credit_pool'),
        CheckConstraint("owner_type IN ('user', 'agency')", name='check_credit_owner_type'),
    )

class CreditTransaction(Base):
    """Credit transaction tracking"""
    __tablename__ = "credit_transactions"
    
    id = Column(Integer, primary_key=True, index=True)
    pool_id = Column(Integer, ForeignKey("credit_pools.id", ondelete="CASCADE"), nullable=False)
    business_id = Column(Integer, ForeignKey("businesses.id"), nullable=True)  # which business used credits
    workflow_execution_id = Column(Integer, nullable=True)  # will reference workflow_executions
    transaction_type = Column(String(20), nullable=False)  # purchase, usage, refund, adjustment
    amount = Column(Integer, nullable=False)  # positive for additions, negative for usage
    balance_after = Column(Integer, nullable=False)
    description = Column(String(255), nullable=True)
    transaction_metadata = Column(JSON, default=dict)  # additional transaction data
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    pool = relationship("CreditPool", back_populates="transactions")
    business = relationship("Business", back_populates="credit_transactions")
    
    __table_args__ = (
        CheckConstraint("transaction_type IN ('purchase', 'usage', 'refund', 'adjustment')", name='check_transaction_type'),
    )

# =============================================================================
# ENHANCED WORKFLOW SYSTEM MODELS
# =============================================================================

class WorkflowTemplate(Base):
    """Workflow templates with V2 schema support (ryvr.workflow.v1)"""
    __tablename__ = "workflow_templates"
    
    id = Column(Integer, primary_key=True, index=True)
    schema_version = Column(String(50), default="ryvr.workflow.v1")
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(100), nullable=False)  # seo, ppc, content, analytics
    tags = Column(JSON, default=list)
    
    # V2 Schema fields
    workflow_config = Column(JSON, nullable=False)  # Complete workflow JSON (inputs, globals, steps, etc.)
    execution_config = Column(JSON, nullable=False)  # Execution settings (mode, concurrency, timeouts)
    tool_catalog = Column(JSON, nullable=True)      # Provider definitions for this workflow
    
    # RYVR-specific fields
    business_id = Column(Integer, ForeignKey("businesses.id"), nullable=True)  # If business-specific
    agency_id = Column(Integer, ForeignKey("agencies.id"), nullable=True)     # If agency-specific
    credit_cost = Column(Integer, nullable=False, default=0)
    estimated_duration = Column(Integer, nullable=True)  # in minutes
    tier_access = Column(JSON, default=list)  # which tiers can access
    
    # Status and versioning
    status = Column(String(20), nullable=False, default='draft')  # draft, testing, beta, published, deprecated
    beta_users = Column(JSON, default=list)  # user IDs with beta access
    version = Column(String(20), default='1.0')
    icon = Column(String(100), nullable=True)
    
    # Audit fields
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    instances = relationship("WorkflowInstance", back_populates="template")
    executions = relationship("WorkflowExecution", back_populates="template")
    
    __table_args__ = (
        CheckConstraint("status IN ('draft', 'testing', 'beta', 'published', 'deprecated')", name='check_workflow_status'),
    )

class WorkflowInstance(Base):
    """Business-specific workflow instances"""
    __tablename__ = "workflow_instances"
    
    id = Column(Integer, primary_key=True, index=True)
    template_id = Column(Integer, ForeignKey("workflow_templates.id"), nullable=False)
    business_id = Column(Integer, ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(200), nullable=True)  # custom name override
    custom_config = Column(JSON, default=dict)  # business-specific overrides
    is_active = Column(Boolean, default=True)
    last_executed_at = Column(DateTime(timezone=True), nullable=True)
    execution_count = Column(Integer, default=0)
    success_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    template = relationship("WorkflowTemplate", back_populates="instances")
    business = relationship("Business", back_populates="workflow_instances")
    # Note: WorkflowExecution now relates directly to templates in V2, not instances

class WorkflowExecution(Base):
    """V2 workflow execution tracking with enhanced monitoring"""
    __tablename__ = "workflow_executions"
    
    id = Column(Integer, primary_key=True, index=True)
    template_id = Column(Integer, ForeignKey("workflow_templates.id"), nullable=False)
    business_id = Column(Integer, ForeignKey("businesses.id"), nullable=False)
    
    # Execution context
    execution_mode = Column(String(20), default="simulate")  # simulate, record, live
    runtime_state = Column(JSON, nullable=False)             # Complete execution state
    step_results = Column(JSON, default=dict)                # Per-step outputs
    
    # Progress tracking
    status = Column(String(20), default="pending")  # pending, running, completed, failed, paused
    current_step = Column(String(100), nullable=True)
    total_steps = Column(Integer, default=0)
    completed_steps = Column(Integer, default=0)
    
    # Flow Management: Kanban-style status tracking
    flow_status = Column(String(20), default="new")  # new, scheduled, in_progress, in_review, complete, error
    flow_title = Column(String(200), nullable=True)  # User-friendly flow name
    custom_field_values = Column(JSON, default=dict)  # Values for editable fields
    
    # Resource usage
    credits_used = Column(Integer, default=0)
    execution_time_ms = Column(Integer, default=0)
    
    # Timestamps
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Error handling
    error_message = Column(Text, nullable=True)
    failed_step = Column(String(100), nullable=True)
    
    # Relationships
    template = relationship("WorkflowTemplate", back_populates="executions")
    step_executions = relationship("WorkflowStepExecution", back_populates="execution")
    api_calls = relationship("APICall", back_populates="execution")
    review_approvals = relationship("FlowReviewApproval", back_populates="execution")
    
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'running', 'completed', 'failed', 'paused')", name='check_execution_status'),
        CheckConstraint("execution_mode IN ('simulate', 'record', 'live')", name='check_execution_mode'),
        CheckConstraint("flow_status IN ('new', 'scheduled', 'in_progress', 'in_review', 'complete', 'error')", name='check_flow_status'),
    )

class WorkflowStepExecution(Base):
    """Individual step execution tracking for detailed monitoring"""
    __tablename__ = "workflow_step_executions"
    
    id = Column(Integer, primary_key=True, index=True)
    execution_id = Column(Integer, ForeignKey("workflow_executions.id"), nullable=False)
    
    # Step identification
    step_id = Column(String(100), nullable=False)     # Step ID from workflow
    step_type = Column(String(50), nullable=False)    # task, ai, transform, foreach, gate, async_task
    step_name = Column(String(200), nullable=True)
    
    # Execution details
    status = Column(String(20), default="pending")    # pending, running, completed, failed, skipped
    input_data = Column(JSON, nullable=True)
    output_data = Column(JSON, nullable=True)
    error_data = Column(JSON, nullable=True)
    
    # Performance metrics
    credits_used = Column(Integer, default=0)
    execution_time_ms = Column(Integer, default=0)
    retry_count = Column(Integer, default=0)
    
    # Provider information
    provider_id = Column(String(50), nullable=True)
    operation_id = Column(String(100), nullable=True)
    external_task_id = Column(String(100), nullable=True)  # For async operations
    
    # Async operation tracking
    is_async = Column(Boolean, default=False)
    async_submit_time = Column(DateTime(timezone=True), nullable=True)
    async_complete_time = Column(DateTime(timezone=True), nullable=True)
    polling_count = Column(Integer, default=0)
    
    # Timestamps
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    execution = relationship("WorkflowExecution", back_populates="step_executions")
    
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'running', 'completed', 'failed', 'skipped')", name='check_step_status'),
        CheckConstraint("step_type IN ('task', 'ai', 'transform', 'foreach', 'gate', 'condition', 'async_task', 'review')", name='check_step_type'),
    )

class FlowReviewApproval(Base):
    """Review approval tracking for flow management"""
    __tablename__ = "flow_review_approvals"
    
    id = Column(Integer, primary_key=True, index=True)
    execution_id = Column(Integer, ForeignKey("workflow_executions.id"), nullable=False)
    step_id = Column(String(100), nullable=False)  # Step ID from workflow
    
    # Review details
    reviewer_type = Column(String(20), nullable=False)  # 'agency', 'client', 'admin'
    reviewed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved = Column(Boolean, nullable=False)
    comments = Column(Text, nullable=True)
    
    # Timestamps
    submitted_for_review_at = Column(DateTime(timezone=True), nullable=False)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    execution = relationship("WorkflowExecution")
    reviewer = relationship("User")
    
    __table_args__ = (
        CheckConstraint("reviewer_type IN ('agency', 'client', 'admin')", name='check_reviewer_type'),
    )

# =============================================================================
# INTEGRATION SYSTEM MODELS
# =============================================================================

class Integration(Base):
    """System-level integrations with V2 workflow support"""
    __tablename__ = "integrations"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)  # DataForSEO, OpenAI, Google Ads
    provider = Column(String(100), nullable=False)  # dataforseo, openai, google
    integration_type = Column(String(20), nullable=False)  # system, agency, business
    level = Column(String(20), nullable=False)  # system, agency, business (which level can configure)
    
    # NEW: Integration behavior configuration
    is_system_wide = Column(Boolean, default=False)  # If true, admin configures once for everyone
    requires_user_config = Column(Boolean, default=True)  # If false, uses system config only
    available_to_roles = Column(JSON, default=lambda: ["admin", "agency", "individual"])  # Which roles can use this
    
    # NEW: Admin control flags
    is_enabled_for_agencies = Column(Boolean, default=True)
    is_enabled_for_individuals = Column(Boolean, default=True)
    is_enabled_for_businesses = Column(Boolean, default=True)
    config_schema = Column(JSON, default=dict)  # configuration schema
    
    # V2 Workflow support
    provider_id = Column(String(50), nullable=True)     # Maps to tool catalog provider.id
    operation_configs = Column(JSON, default=dict)      # Available operations with schemas
    credit_multiplier = Column(Float, default=1.0)      # Cost adjustment factor
    tier_restrictions = Column(JSON, default=list)      # Which tiers can use this integration
    
    # Universal async support
    is_async_capable = Column(Boolean, default=False)   # Supports async operations
    async_config = Column(JSON, nullable=True)          # Default async configuration
    max_concurrent_requests = Column(Integer, default=5) # Rate limiting
    default_timeout_seconds = Column(Integer, default=300) # Default operation timeout
    
    # Status and testing
    is_active = Column(Boolean, default=True)
    is_mock = Column(Boolean, default=False)  # for demo purposes
    last_health_check = Column(DateTime(timezone=True), nullable=True)
    health_status = Column(String(20), default="unknown")  # healthy, degraded, failed, unknown
    
    # Audit fields
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    system_integrations = relationship("SystemIntegration", back_populates="integration")
    agency_integrations = relationship("AgencyIntegration", back_populates="integration")
    business_integrations = relationship("BusinessIntegration", back_populates="integration")
    
    __table_args__ = (
        CheckConstraint("integration_type IN ('system', 'agency', 'business')", name='check_integration_type'),
        CheckConstraint("level IN ('system', 'agency', 'business')", name='check_integration_level'),
        CheckConstraint("health_status IN ('healthy', 'degraded', 'failed', 'unknown')", name='check_health_status'),
    )

class SystemIntegration(Base):
    """System-level integration configurations (admin managed)"""
    __tablename__ = "system_integrations"
    
    id = Column(Integer, primary_key=True, index=True)
    integration_id = Column(Integer, ForeignKey("integrations.id"), nullable=False)
    custom_config = Column(JSON, default=dict)
    credentials = Column(JSON, default=dict)  # encrypted API keys, etc.
    is_active = Column(Boolean, default=True)
    last_tested = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    integration = relationship("Integration", back_populates="system_integrations")
    
    __table_args__ = (
        UniqueConstraint('integration_id', name='unique_system_integration'),
    )

class AgencyIntegration(Base):
    """Agency-level integration configurations"""
    __tablename__ = "agency_integrations"
    
    id = Column(Integer, primary_key=True, index=True)
    agency_id = Column(Integer, ForeignKey("agencies.id", ondelete="CASCADE"), nullable=False)
    integration_id = Column(Integer, ForeignKey("integrations.id"), nullable=False)
    custom_config = Column(JSON, default=dict)
    credentials = Column(JSON, default=dict)  # encrypted API keys, etc.
    is_active = Column(Boolean, default=True)
    last_tested = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    agency = relationship("Agency", back_populates="integrations")
    integration = relationship("Integration", back_populates="agency_integrations")
    
    __table_args__ = (
        UniqueConstraint('agency_id', 'integration_id', name='unique_agency_integration'),
    )

class BusinessIntegration(Base):
    """Business-level integration configurations"""
    __tablename__ = "business_integrations"
    
    id = Column(Integer, primary_key=True, index=True)
    business_id = Column(Integer, ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    integration_id = Column(Integer, ForeignKey("integrations.id"), nullable=False)
    custom_config = Column(JSON, default=dict)
    credentials = Column(JSON, default=dict)  # encrypted API keys, etc.
    is_active = Column(Boolean, default=True)
    last_tested = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    business = relationship("Business", back_populates="integrations")
    integration = relationship("Integration", back_populates="business_integrations")
    
    __table_args__ = (
        UniqueConstraint('business_id', 'integration_id', name='unique_business_integration'),
    )

# =============================================================================
# API TRACKING MODELS
# =============================================================================

class APICall(Base):
    """Enhanced API call tracking"""
    __tablename__ = "api_calls"
    
    id = Column(Integer, primary_key=True, index=True)
    workflow_execution_id = Column(Integer, ForeignKey("workflow_executions.id"), nullable=False)
    integration_name = Column(String(200), nullable=False)
    endpoint = Column(String(500), nullable=False)
    request_data = Column(JSON, default=dict)
    response_data = Column(JSON, default=dict)
    status_code = Column(Integer, nullable=True)
    credits_used = Column(Integer, default=0)
    execution_time_ms = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    execution = relationship("WorkflowExecution", back_populates="api_calls")

# =============================================================================
# FILE MANAGEMENT MODELS
# =============================================================================

class File(Base):
    """File management with account and business-level organization"""
    __tablename__ = "files"
    
    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, nullable=False)  # user_id for personal, agency_id for agencies
    account_type = Column(String(20), nullable=False)  # 'user', 'agency'
    business_id = Column(Integer, ForeignKey("businesses.id"), nullable=True)  # NULL for account-level files
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # File information
    file_name = Column(String(255), nullable=False)  # Stored filename with UUID
    original_name = Column(String(255), nullable=False)  # Original upload name
    file_type = Column(String(100), nullable=False)  # pdf, docx, txt, etc.
    file_size = Column(Integer, nullable=False)  # Size in bytes
    file_path = Column(String(500), nullable=False)  # Full storage path
    
    # Content and processing
    content_text = Column(Text, nullable=True)  # Extracted text content
    summary = Column(Text, nullable=True)  # AI-generated summary
    summary_credits_used = Column(Integer, default=0)  # OpenAI usage tracking
    processing_status = Column(String(20), default='pending')  # pending, processing, completed, failed
    
    # Metadata and organization
    tags = Column(JSON, default=list)  # User-added tags
    file_metadata = Column(JSON, default=dict)  # File metadata (mime type, etc.)
    
    # Audit fields
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    business = relationship("Business", foreign_keys=[business_id])
    uploader = relationship("User", foreign_keys=[uploaded_by])
    permissions = relationship("FilePermission", back_populates="file", cascade="all, delete-orphan")
    
    __table_args__ = (
        CheckConstraint("account_type IN ('user', 'agency')", name='check_account_type'),
        CheckConstraint("processing_status IN ('pending', 'processing', 'completed', 'failed')", name='check_processing_status'),
        # Index for efficient queries
        Index('idx_files_account', 'account_id', 'account_type'),
        Index('idx_files_business', 'business_id'),
        Index('idx_files_uploader', 'uploaded_by'),
    )

class StorageUsage(Base):
    """Track storage usage at account level"""
    __tablename__ = "storage_usage"
    
    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, nullable=False)  # user_id or agency_id
    account_type = Column(String(20), nullable=False)  # 'user', 'agency'
    
    # Usage tracking
    total_bytes = Column(Integer, nullable=False, default=0)
    file_count = Column(Integer, nullable=False, default=0)
    account_files_bytes = Column(Integer, nullable=False, default=0)  # Account-level files
    business_files_bytes = Column(Integer, nullable=False, default=0)  # All business files
    
    # Audit
    last_updated = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    __table_args__ = (
        UniqueConstraint('account_id', 'account_type', name='unique_storage_usage'),
        CheckConstraint("account_type IN ('user', 'agency')", name='check_storage_account_type'),
    )

class FilePermission(Base):
    """File sharing and access permissions between businesses"""
    __tablename__ = "file_permissions"
    
    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(Integer, ForeignKey("files.id", ondelete="CASCADE"), nullable=False)
    business_id = Column(Integer, ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    permission_type = Column(String(20), nullable=False)  # 'read', 'write'
    granted_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    file = relationship("File", back_populates="permissions")
    business = relationship("Business")
    granter = relationship("User")
    
    __table_args__ = (
        UniqueConstraint('file_id', 'business_id', name='unique_file_business_permission'),
        CheckConstraint("permission_type IN ('read', 'write')", name='check_permission_type'),
    )

# =============================================================================
# LEGACY COMPATIBILITY (TO BE REMOVED)
# =============================================================================

# TaskTemplate - keeping for now but will be merged into WorkflowTemplate
class TaskTemplate(Base):
    """Legacy task templates - will be merged into WorkflowTemplate"""
    __tablename__ = "task_templates"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(100), nullable=False)
    integration_id = Column(Integer, ForeignKey("integrations.id"), nullable=True)
    config_schema = Column(JSON, default=dict)
    credit_cost = Column(Integer, default=1)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())