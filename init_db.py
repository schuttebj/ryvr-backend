#!/usr/bin/env python3
"""
Database initialization script for RYVR multi-tenant platform
Creates tables, default data, and admin user
"""
import sys
import os
from datetime import datetime, timedelta
from decimal import Decimal
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from database import engine, Base
from models import (
    User, Agency, AgencyUser, Business, BusinessUser,
    OnboardingTemplate, OnboardingQuestion,
    SubscriptionTier, UserSubscription, CreditPool,
    WorkflowTemplate, Integration, AssetUpload
)
from auth import get_password_hash

def test_connection():
    """Test database connection"""
    try:
        with engine.connect() as connection:
            result = connection.execute(text("SELECT 1"))
            print("✅ Database connection successful!")
            return True
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return False

def create_tables():
    """Create all tables"""
    try:
        print("Creating database tables...")
        Base.metadata.create_all(bind=engine)
        print("✅ Tables created successfully!")
        return True
    except Exception as e:
        print(f"❌ Failed to create tables: {e}")
        return False

def create_default_subscription_tiers():
    """Create default subscription tiers"""
    try:
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        db = SessionLocal()
        
        # Check if tiers already exist
        existing_tiers = db.query(SubscriptionTier).count()
        if existing_tiers > 0:
            print("✅ Subscription tiers already exist")
            db.close()
            return True
        
        # Create default tiers
        tiers = [
            {
                'name': 'Starter',
                'slug': 'starter',
                'description': 'Perfect for small agencies getting started',
                'price_monthly': Decimal('49.00'),
                'price_yearly': Decimal('490.00'),
                'credits_included': 5000,
                'client_limit': 5,
                'user_limit': 2,
                'features': ['basic_workflows', 'email_support', 'basic_analytics'],
                'workflow_access': ['seo_basic', 'content_basic'],
                'integration_limits': {'dataforseo': 1000, 'openai': 500},
                'sort_order': 1
            },
            {
                'name': 'Professional',
                'slug': 'professional',
                'description': 'For growing agencies with multiple clients',
                'price_monthly': Decimal('149.00'),
                'price_yearly': Decimal('1490.00'),
                'credits_included': 20000,
                'client_limit': 25,
                'user_limit': 5,
                'features': ['advanced_workflows', 'priority_support', 'advanced_analytics', 'white_label'],
                'workflow_access': ['seo_basic', 'seo_advanced', 'content_basic', 'content_advanced', 'ppc_basic'],
                'integration_limits': {'dataforseo': 5000, 'openai': 2000},
                'sort_order': 2
            },
            {
                'name': 'Enterprise',
                'slug': 'enterprise',
                'description': 'For large agencies with unlimited potential',
                'price_monthly': Decimal('499.00'),
                'price_yearly': Decimal('4990.00'),
                'credits_included': 100000,
                'client_limit': 100,
                'user_limit': 25,
                'features': ['all_workflows', 'dedicated_support', 'custom_analytics', 'white_label', 'custom_domain', 'api_access'],
                'workflow_access': ['all'],
                'integration_limits': {'dataforseo': 25000, 'openai': 10000},
                'sort_order': 3
            }
        ]
        
        for tier_data in tiers:
            tier = SubscriptionTier(**tier_data)
            db.add(tier)
        
        db.commit()
        print(f"✅ Created {len(tiers)} subscription tiers")
        db.close()
        return True
        
    except Exception as e:
        print(f"❌ Failed to create subscription tiers: {e}")
        return False

def create_default_admin():
    """Create default admin user"""
    try:
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        db = SessionLocal()
        
        # Check if admin user already exists
        existing_admin = db.query(User).filter(User.email == "admin@ryvr.com").first()
        if existing_admin:
            print("✅ Admin user already exists")
            db.close()
            return True
        
        # Get starter tier for trial
        starter_tier = db.query(SubscriptionTier).filter(SubscriptionTier.slug == "starter").first()
        if not starter_tier:
            print("❌ Starter tier not found - create tiers first")
            db.close()
            return False
        
        # Create admin user
        admin_user = User(
            email="admin@ryvr.com",
            username="admin",
            hashed_password=get_password_hash("password"),
            role="admin",
            first_name="Admin",
            last_name="User",
            email_verified=True,
            is_active=True
        )
        
        db.add(admin_user)
        db.commit()
        db.refresh(admin_user)
        
        # Create admin subscription (no trial for admin)
        admin_subscription = UserSubscription(
            user_id=admin_user.id,
            tier_id=starter_tier.id,
            status="active",
            current_period_start=datetime.utcnow(),
            current_period_end=datetime.utcnow() + timedelta(days=365)
        )
        
        db.add(admin_subscription)
        db.commit()
        
        print("✅ Default admin user created (admin@ryvr.com / password)")
        db.close()
        return True
        
    except Exception as e:
        print(f"❌ Failed to create admin user: {e}")
        return False

def create_demo_agency():
    """Create a demo agency with sample data"""
    try:
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        db = SessionLocal()
        
        # Check if demo agency already exists
        existing_agency = db.query(Agency).filter(Agency.slug == "demo-agency").first()
        if existing_agency:
            print("✅ Demo agency already exists")
            db.close()
            return True
        
        # Get professional tier for demo
        pro_tier = db.query(SubscriptionTier).filter(SubscriptionTier.slug == "professional").first()
        if not pro_tier:
            print("❌ Professional tier not found")
            db.close()
            return False
        
        # Create demo agency user
        agency_user = User(
            email="demo@agency.com",
            username="demo_agency",
            hashed_password=get_password_hash("password"),
            role="agency",
            first_name="Demo",
            last_name="Agency",
            email_verified=True,
            is_active=True
        )
        
        db.add(agency_user)
        db.commit()
        db.refresh(agency_user)
        
        # Create trial subscription
        trial_subscription = UserSubscription(
            user_id=agency_user.id,
            tier_id=pro_tier.id,
            status="trial",
            trial_starts_at=datetime.utcnow(),
            trial_ends_at=datetime.utcnow() + timedelta(days=14)
        )
        
        db.add(trial_subscription)
        db.commit()
        
        # Create demo agency
        demo_agency = Agency(
            name="Demo Marketing Agency",
            slug="demo-agency",
            website="https://demo-agency.com",
            phone="+1-555-0123",
            address="123 Demo Street, Demo City, DC 12345",
            branding_config={
                "logo_url": "/assets/demo-logo.png",
                "primary_color": "#3f51b5",
                "secondary_color": "#f50057",
                "font_family": "Inter"
            },
            settings={
                "timezone": "America/New_York",
                "currency": "USD",
                "language": "en"
            },
            onboarding_data={
                "business_type": "Digital Marketing Agency",
                "team_size": "5-10",
                "primary_services": ["SEO", "PPC", "Content Marketing"],
                "target_clients": "Small to Medium Businesses"
            },
            created_by=agency_user.id,
            is_active=True
        )
        
        db.add(demo_agency)
        db.commit()
        db.refresh(demo_agency)
        
        # Link user to agency as owner
        agency_membership = AgencyUser(
            agency_id=demo_agency.id,
            user_id=agency_user.id,
            role="owner",
            joined_at=datetime.utcnow(),
            is_active=True
        )
        
        db.add(agency_membership)
        db.commit()
        
        # Create credit pool for agency
        credit_pool = CreditPool(
            owner_id=demo_agency.id,
            owner_type="agency",
            balance=5000,  # Trial credits
            total_purchased=5000,
            overage_threshold=100
        )
        
        db.add(credit_pool)
        db.commit()
        
        # Create demo businesses
        businesses = [
            {
                "name": "Tech Startup Inc",
                "slug": "tech-startup",
                "industry": "Technology",
                "website": "https://techstartup.com",
                "description": "Innovative SaaS platform for small businesses",
                "contact_email": "hello@techstartup.com"
            },
            {
                "name": "Green Gardens Landscaping",
                "slug": "green-gardens",
                "industry": "Landscaping",
                "website": "https://greengardens.local",
                "description": "Professional landscaping and garden design",
                "contact_email": "info@greengardens.local"
            }
        ]
        
        for business_data in businesses:
            business = Business(
                agency_id=demo_agency.id,
                **business_data,
                onboarding_data={
                    "target_audience": "Local homeowners" if "gardens" in business_data["slug"] else "Small business owners",
                    "primary_goals": ["Increase online visibility", "Generate more leads"],
                    "current_challenges": ["Limited online presence", "Low search rankings"]
                },
                is_active=True
            )
            
            db.add(business)
        
        db.commit()
        
        print("✅ Demo agency created with sample businesses")
        db.close()
        return True
        
    except Exception as e:
        print(f"❌ Failed to create demo agency: {e}")
        return False

def create_default_integrations():
    """Create default system integrations"""
    try:
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        db = SessionLocal()
        
        # Check if integrations already exist
        existing_integrations = db.query(Integration).count()
        if existing_integrations > 0:
            print("✅ Integrations already exist")
            db.close()
            return True
        
        # Create system-level integrations
        integrations = [
            {
                'name': 'DataForSEO',
                'provider': 'dataforseo',
                'integration_type': 'system',
                'level': 'system',
                'config_schema': {
                    'username': {'type': 'string', 'required': True},
                    'password': {'type': 'string', 'required': True},
                    'base_url': {'type': 'string', 'default': 'https://sandbox.dataforseo.com'}
                },
                'is_active': True
            },
            {
                'name': 'OpenAI',
                'provider': 'openai',
                'integration_type': 'system',
                'level': 'system',
                'config_schema': {
                    'api_key': {'type': 'string', 'required': True},
                    'model': {'type': 'string', 'default': 'gpt-4o-mini'},
                    'max_tokens': {'type': 'integer', 'default': 2000}
                },
                'is_active': True
            },
            {
                'name': 'Google Ads',
                'provider': 'google',
                'integration_type': 'business',
                'level': 'business',
                'config_schema': {
                    'client_id': {'type': 'string', 'required': True},
                    'client_secret': {'type': 'string', 'required': True},
                    'refresh_token': {'type': 'string', 'required': True},
                    'customer_id': {'type': 'string', 'required': True}
                },
                'is_active': True
            },
            {
                'name': 'Google Analytics',
                'provider': 'google',
                'integration_type': 'business',
                'level': 'business',
                'config_schema': {
                    'property_id': {'type': 'string', 'required': True},
                    'service_account_key': {'type': 'object', 'required': True}
                },
                'is_active': True
            },
            {
                'name': 'Meta Ads',
                'provider': 'meta',
                'integration_type': 'business',
                'level': 'business',
                'config_schema': {
                    'app_id': {'type': 'string', 'required': True},
                    'app_secret': {'type': 'string', 'required': True},
                    'access_token': {'type': 'string', 'required': True},
                    'ad_account_id': {'type': 'string', 'required': True}
                },
                'is_active': True
            }
        ]
        
        for integration_data in integrations:
            integration = Integration(**integration_data)
            db.add(integration)
        
        db.commit()
        print(f"✅ Created {len(integrations)} default integrations")
        db.close()
        return True
        
    except Exception as e:
        print(f"❌ Failed to create integrations: {e}")
        return False

def create_default_onboarding_templates():
    """Create default onboarding templates"""
    try:
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        db = SessionLocal()
        
        # Check if templates already exist
        existing_templates = db.query(OnboardingTemplate).count()
        if existing_templates > 0:
            print("✅ Onboarding templates already exist")
            db.close()
            return True
        
        # Agency onboarding template
        agency_template = OnboardingTemplate(
            name="Agency Onboarding",
            description="Standard onboarding questionnaire for new agencies",
            target_type="agency",
            is_default=True,
            is_active=True
        )
        
        db.add(agency_template)
        db.commit()
        db.refresh(agency_template)
        
        # Agency questions
        agency_questions = [
            # Basic Information
            {'section': 'basic', 'question_key': 'agency_name', 'question_text': 'What is your agency name?', 'question_type': 'text', 'is_required': True, 'sort_order': 1},
            {'section': 'basic', 'question_key': 'website', 'question_text': 'What is your agency website?', 'question_type': 'text', 'sort_order': 2},
            {'section': 'basic', 'question_key': 'team_size', 'question_text': 'How many people are in your team?', 'question_type': 'select', 'options': ['1-2', '3-5', '6-10', '11-25', '25+'], 'sort_order': 3},
            
            # Services
            {'section': 'services', 'question_key': 'primary_services', 'question_text': 'What are your primary services?', 'question_type': 'multiselect', 'options': ['SEO', 'PPC', 'Content Marketing', 'Social Media', 'Web Design', 'Email Marketing', 'Analytics'], 'sort_order': 4},
            {'section': 'services', 'question_key': 'specialization', 'question_text': 'What is your specialization or niche?', 'question_type': 'textarea', 'sort_order': 5},
            
            # Clients
            {'section': 'clients', 'question_key': 'client_types', 'question_text': 'What types of clients do you typically work with?', 'question_type': 'multiselect', 'options': ['Small Business', 'Mid-Market', 'Enterprise', 'E-commerce', 'SaaS', 'Local Services', 'B2B', 'B2C'], 'sort_order': 6},
            {'section': 'clients', 'question_key': 'client_count', 'question_text': 'How many clients do you currently have?', 'question_type': 'select', 'options': ['1-5', '6-10', '11-25', '26-50', '50+'], 'sort_order': 7},
            
            # Goals
            {'section': 'goals', 'question_key': 'goals', 'question_text': 'What are your main goals for using RYVR?', 'question_type': 'multiselect', 'options': ['Automate Workflows', 'Scale Operations', 'Improve Client Results', 'Save Time', 'Better Reporting', 'White-label Solution'], 'sort_order': 8}
        ]
        
        for q_data in agency_questions:
            question = OnboardingQuestion(template_id=agency_template.id, **q_data)
            db.add(question)
        
        # Business onboarding template
        business_template = OnboardingTemplate(
            name="Business Onboarding",
            description="Standard onboarding questionnaire for new businesses",
            target_type="business",
            is_default=True,
            is_active=True
        )
        
        db.add(business_template)
        db.commit()
        db.refresh(business_template)
        
        # Business questions
        business_questions = [
            # Basic Information
            {'section': 'basic', 'question_key': 'business_name', 'question_text': 'What is your business name?', 'question_type': 'text', 'is_required': True, 'sort_order': 1},
            {'section': 'basic', 'question_key': 'industry', 'question_text': 'What industry are you in?', 'question_type': 'text', 'is_required': True, 'sort_order': 2},
            {'section': 'basic', 'question_key': 'website', 'question_text': 'What is your website URL?', 'question_type': 'text', 'sort_order': 3},
            {'section': 'basic', 'question_key': 'business_type', 'question_text': 'What type of business are you?', 'question_type': 'select', 'options': ['E-commerce', 'Service-based', 'SaaS', 'Local Business', 'B2B', 'B2C', 'Non-profit'], 'sort_order': 4},
            
            # Target Audience
            {'section': 'audience', 'question_key': 'target_audience', 'question_text': 'Who is your target audience?', 'question_type': 'textarea', 'is_required': True, 'sort_order': 5},
            {'section': 'audience', 'question_key': 'geographic_focus', 'question_text': 'What is your geographic focus?', 'question_type': 'select', 'options': ['Local', 'Regional', 'National', 'International'], 'sort_order': 6},
            
            # Marketing
            {'section': 'marketing', 'question_key': 'current_marketing', 'question_text': 'What marketing channels are you currently using?', 'question_type': 'multiselect', 'options': ['SEO', 'Google Ads', 'Facebook Ads', 'Social Media', 'Email Marketing', 'Content Marketing', 'Traditional Advertising'], 'sort_order': 7},
            {'section': 'marketing', 'question_key': 'marketing_goals', 'question_text': 'What are your main marketing goals?', 'question_type': 'multiselect', 'options': ['Increase Website Traffic', 'Generate More Leads', 'Improve Brand Awareness', 'Boost Sales', 'Better Customer Engagement'], 'sort_order': 8},
            {'section': 'marketing', 'question_key': 'biggest_challenges', 'question_text': 'What are your biggest marketing challenges?', 'question_type': 'textarea', 'sort_order': 9}
        ]
        
        for q_data in business_questions:
            question = OnboardingQuestion(template_id=business_template.id, **q_data)
            db.add(question)
        
        db.commit()
        print("✅ Created default onboarding templates")
        db.close()
        return True
        
    except Exception as e:
        print(f"❌ Failed to create onboarding templates: {e}")
        return False

def create_sample_workflow_templates():
    """Create sample workflow templates"""
    try:
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        db = SessionLocal()
        
        # Check if templates already exist
        existing_templates = db.query(WorkflowTemplate).count()
        if existing_templates > 0:
            print("✅ Workflow templates already exist")
            db.close()
            return True
        
        # Get admin user
        admin_user = db.query(User).filter(User.role == "admin").first()
        if not admin_user:
            print("❌ Admin user not found")
            db.close()
            return False
        
        # Sample workflow templates
        templates = [
            {
                'name': 'Basic SEO Analysis',
                'description': 'Comprehensive SEO analysis including keyword research and competitor analysis',
                'category': 'seo',
                'tags': ['seo', 'analysis', 'keywords'],
                'config': {
                    'nodes': [
                        {'id': '1', 'type': 'seo_serp_analyze', 'label': 'SERP Analysis'},
                        {'id': '2', 'type': 'seo_keywords_volume', 'label': 'Keyword Volume'},
                        {'id': '3', 'type': 'ai_analysis', 'label': 'AI Insights'}
                    ],
                    'edges': [
                        {'id': 'e1', 'source': '1', 'target': '2'},
                        {'id': 'e2', 'source': '2', 'target': '3'}
                    ]
                },
                'credit_cost': 25,
                'estimated_duration': 15,
                'tier_access': ['starter', 'professional', 'enterprise'],
                'status': 'published',
                'version': '1.0',
                'icon': 'search',
                'created_by': admin_user.id
            },
            {
                'name': 'Content Creation Workflow',
                'description': 'AI-powered content creation with SEO optimization',
                'category': 'content',
                'tags': ['content', 'ai', 'seo'],
                'config': {
                    'nodes': [
                        {'id': '1', 'type': 'client_profile', 'label': 'Load Client Data'},
                        {'id': '2', 'type': 'ai_content_seo', 'label': 'Generate Content'},
                        {'id': '3', 'type': 'ai_analysis', 'label': 'Review Content'}
                    ],
                    'edges': [
                        {'id': 'e1', 'source': '1', 'target': '2'},
                        {'id': 'e2', 'source': '2', 'target': '3'}
                    ]
                },
                'credit_cost': 15,
                'estimated_duration': 10,
                'tier_access': ['professional', 'enterprise'],
                'status': 'published',
                'version': '1.0',
                'icon': 'edit',
                'created_by': admin_user.id
            },
            {
                'name': 'Competitor Analysis Suite',
                'description': 'Complete competitor analysis including backlinks and keywords',
                'category': 'analysis',
                'tags': ['competitors', 'analysis', 'seo'],
                'config': {
                    'nodes': [
                        {'id': '1', 'type': 'seo_labs_serp_competitors', 'label': 'Find Competitors'},
                        {'id': '2', 'type': 'seo_backlinks_competitors', 'label': 'Backlink Analysis'},
                        {'id': '3', 'type': 'ai_analysis', 'label': 'Generate Report'}
                    ],
                    'edges': [
                        {'id': 'e1', 'source': '1', 'target': '2'},
                        {'id': 'e2', 'source': '2', 'target': '3'}
                    ]
                },
                'credit_cost': 50,
                'estimated_duration': 30,
                'tier_access': ['enterprise'],
                'status': 'beta',
                'beta_users': [admin_user.id],
                'version': '1.0',
                'icon': 'trending_up',
                'created_by': admin_user.id
            }
        ]
        
        for template_data in templates:
            template = WorkflowTemplate(**template_data)
            db.add(template)
        
        db.commit()
        print(f"✅ Created {len(templates)} sample workflow templates")
        db.close()
        return True
        
    except Exception as e:
        print(f"❌ Failed to create workflow templates: {e}")
        return False

def main():
    """Main initialization function"""
    print("🚀 Initializing RYVR Multi-Tenant Platform...")
    print(f"Database URL: {os.getenv('DATABASE_URL', 'Not set')}")
    
    # Test connection
    if not test_connection():
        sys.exit(1)
    
    # Create tables
    if not create_tables():
        sys.exit(1)
    
    # Create default data in order
    if not create_default_subscription_tiers():
        sys.exit(1)
    
    if not create_default_admin():
        sys.exit(1)
    
    if not create_demo_agency():
        sys.exit(1)
    
    if not create_default_integrations():
        sys.exit(1)
    
    if not create_default_onboarding_templates():
        sys.exit(1)
    
    if not create_sample_workflow_templates():
        sys.exit(1)
    
    print("\n🎉 Database initialization completed successfully!")
    print("\nDefault accounts created:")
    print("👤 Admin: admin@ryvr.com / password")
    print("🏢 Demo Agency: demo@agency.com / password")
    print("\nSubscription tiers: Starter, Professional, Enterprise")
    print("🔌 System integrations: DataForSEO, OpenAI, Google Ads, Analytics, Meta")
    print("📋 Onboarding templates ready for agencies and businesses")
    print("⚡ Sample workflow templates published")
    print("\nYou can now:")
    print("1. Start the server with: uvicorn main:app --reload")
    print("2. Access API docs at: http://localhost:8000/docs")
    print("3. Login as admin or demo agency")

if __name__ == "__main__":
    main()