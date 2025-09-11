from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float, Text, JSON, ForeignKey, UniqueConstraint, CheckConstraint, Numeric
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
    agency_memberships = relationship("AgencyUser", back_populates="user")
    business_memberships = relationship("BusinessUser", back_populates="user")
    created_agencies = relationship("Agency", foreign_keys="Agency.created_by")
    subscription = relationship("UserSubscription", back_populates="user", uselist=False)
    
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
    metadata = Column(JSON, default=dict)  # additional transaction data
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
    """Admin-created workflow templates"""
    __tablename__ = "workflow_templates"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(100), nullable=False)  # seo, ppc, content, analytics
    tags = Column(JSON, default=list)
    config = Column(JSON, nullable=False)  # workflow definition
    credit_cost = Column(Integer, nullable=False, default=0)
    estimated_duration = Column(Integer, nullable=True)  # in minutes
    tier_access = Column(JSON, default=list)  # which tiers can access
    status = Column(String(20), nullable=False, default='draft')  # draft, testing, beta, published, deprecated
    beta_users = Column(JSON, default=list)  # user IDs with beta access
    version = Column(String(20), default='1.0')
    icon = Column(String(100), nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    instances = relationship("WorkflowInstance", back_populates="template")
    
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
    executions = relationship("WorkflowExecution", back_populates="instance")

class WorkflowExecution(Base):
    """Enhanced workflow execution tracking"""
    __tablename__ = "workflow_executions"
    
    id = Column(Integer, primary_key=True, index=True)
    instance_id = Column(Integer, ForeignKey("workflow_instances.id"), nullable=False)
    business_id = Column(Integer, ForeignKey("businesses.id"), nullable=False)  # for direct queries
    status = Column(String(20), default="pending")  # pending, running, completed, failed
    credits_used = Column(Integer, default=0)
    execution_data = Column(JSON, default=dict)  # execution results and logs
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    instance = relationship("WorkflowInstance", back_populates="executions")
    api_calls = relationship("APICall", back_populates="execution")
    
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'running', 'completed', 'failed')", name='check_execution_status'),
    )

# =============================================================================
# INTEGRATION SYSTEM MODELS
# =============================================================================

class Integration(Base):
    """System-level integrations"""
    __tablename__ = "integrations"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)  # DataForSEO, OpenAI, Google Ads
    provider = Column(String(100), nullable=False)  # dataforseo, openai, google
    integration_type = Column(String(20), nullable=False)  # system, agency, business
    level = Column(String(20), nullable=False)  # system, agency, business (which level can configure)
    config_schema = Column(JSON, default=dict)  # configuration schema
    is_active = Column(Boolean, default=True)
    is_mock = Column(Boolean, default=False)  # for demo purposes
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    agency_integrations = relationship("AgencyIntegration", back_populates="integration")
    business_integrations = relationship("BusinessIntegration", back_populates="integration")
    
    __table_args__ = (
        CheckConstraint("integration_type IN ('system', 'agency', 'business')", name='check_integration_type'),
        CheckConstraint("level IN ('system', 'agency', 'business')", name='check_integration_level'),
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