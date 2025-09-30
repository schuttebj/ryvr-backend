from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
import json
import openai
import os

from database import get_db
from auth import get_current_active_user, get_user_businesses
import models
import schemas

router = APIRouter(prefix="/api/v1/clients", tags=["clients"])

# Get all clients for current user
@router.get("/", response_model=List[schemas.Client])
def get_clients(
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = None,
    industry: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    # Get businesses accessible to current user
    accessible_businesses = get_user_businesses(current_user, db)
    business_ids = [b.id for b in accessible_businesses]
    
    if not business_ids:
        return []
    
    query = db.query(models.Business).filter(models.Business.id.in_(business_ids))
    
    if status == "active":
        query = query.filter(models.Business.is_active == True)
    elif status == "inactive":
        query = query.filter(models.Business.is_active == False)
    if industry:
        query = query.filter(models.Business.industry == industry)
    
    clients = query.offset(skip).limit(limit).all()
    return clients

# Get a specific client
@router.get("/{client_id}", response_model=schemas.Client)
def get_client(
    client_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    # Check if user has access to this business
    accessible_businesses = get_user_businesses(current_user, db)
    business_ids = [b.id for b in accessible_businesses]
    
    client = db.query(models.Business).filter(
        models.Business.id == client_id,
        models.Business.id.in_(business_ids)
    ).first()
    
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    
    return client

# Create a new client
@router.post("/", response_model=schemas.Client)
def create_client(
    client: schemas.ClientCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    # For individual users, get their agency_id
    if current_user.role == 'individual':
        # Get the user's personal agency
        user_agency = db.query(models.AgencyUser).filter(
            models.AgencyUser.user_id == current_user.id,
            models.AgencyUser.role == 'owner'
        ).first()
        if not user_agency:
            raise HTTPException(status_code=400, detail="User agency not found")
        agency_id = user_agency.agency_id
    else:
        # Use the provided agency_id (must be accessible by user)
        agency_id = client.agency_id
        # Verify user has access to this agency
        user_agency = db.query(models.AgencyUser).filter(
            models.AgencyUser.user_id == current_user.id,
            models.AgencyUser.agency_id == agency_id
        ).first()
        if not user_agency:
            raise HTTPException(status_code=403, detail="Access denied to agency")
    
    db_client = models.Business(
        **client.dict(),
        agency_id=agency_id
    )
    db.add(db_client)
    db.commit()
    db.refresh(db_client)
    return db_client

# Update a client
@router.put("/{client_id}", response_model=schemas.Client)
def update_client(
    client_id: int,
    client_update: schemas.ClientUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    # Check if user has access to this business
    accessible_businesses = get_user_businesses(current_user, db)
    business_ids = [b.id for b in accessible_businesses]
    
    client = db.query(models.Business).filter(
        models.Business.id == client_id,
        models.Business.id.in_(business_ids)
    ).first()
    
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    
    # Update only provided fields
    update_data = client_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(client, field, value)
    
    client.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(client)
    return client

# Delete a client
@router.delete("/{client_id}")
def delete_client(
    client_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    # Check if user has access to this business
    accessible_businesses = get_user_businesses(current_user, db)
    business_ids = [b.id for b in accessible_businesses]
    
    client = db.query(models.Business).filter(
        models.Business.id == client_id,
        models.Business.id.in_(business_ids)
    ).first()
    
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    
    # Soft delete
    client.is_active = False
    client.updated_at = datetime.utcnow()
    db.commit()
    return {"message": "Client deleted successfully"}

# Update questionnaire responses
@router.patch("/{client_id}/questionnaire", response_model=schemas.Client)
def update_questionnaire(
    client_id: int,
    questionnaire_data: dict,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    # Check if user has access to this business
    accessible_businesses = get_user_businesses(current_user, db)
    business_ids = [b.id for b in accessible_businesses]
    
    client = db.query(models.Business).filter(
        models.Business.id == client_id,
        models.Business.id.in_(business_ids)
    ).first()
    
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    
    # Merge with existing questionnaire data
    existing_responses = client.onboarding_data.get('questionnaire_responses', {}) if client.onboarding_data else {}
    existing_responses.update(questionnaire_data)
    
    # Update onboarding_data to include questionnaire responses
    onboarding_data = client.onboarding_data or {}
    onboarding_data['questionnaire_responses'] = existing_responses
    client.onboarding_data = onboarding_data
    client.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(client)
    return client

# Generate business profile using AI
@router.post("/{client_id}/generate-profile")
def generate_business_profile(
    client_id: int,
    generation_request: schemas.BusinessProfileGenerationRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    client = db.query(models.Client).filter(
        models.Client.id == client_id,
        models.Client.owner_id == current_user.id
    ).first()
    
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    
    questionnaire_responses = client.onboarding_data.get('questionnaire_responses') if client.onboarding_data else None
    if not questionnaire_responses:
        raise HTTPException(status_code=400, detail="Client must complete questionnaire before generating profile")
    
    try:
        # Get OpenAI API key from system integration (no hardcoded env vars)
        openai_api_key = None
        
        # Try to get from system integration first
        system_integration = db.query(models.SystemIntegration).join(
            models.Integration
        ).filter(
            models.Integration.provider == "openai",
            models.SystemIntegration.is_active == True,
            models.Integration.is_active == True
        ).first()
        
        if system_integration and system_integration.credentials:
            credentials = system_integration.credentials
            if isinstance(credentials, str):
                import json
                credentials = json.loads(credentials)
            openai_api_key = credentials.get("api_key")
        
        if not openai_api_key:
            # Try to get from business or agency integrations
            integration = db.query(models.BusinessIntegration).filter(
                models.BusinessIntegration.business_id == client_id
            ).join(models.Integration).filter(
                models.Integration.name == "openai",
                models.Integration.is_active == True
            ).first()
            
            if not integration:
                # Try agency-level integration
                integration = db.query(models.AgencyIntegration).filter(
                    models.AgencyIntegration.agency_id == client.agency_id
                ).join(models.Integration).filter(
                    models.Integration.name == "openai",
                    models.Integration.is_active == True
                ).first()
            
            if integration:
                if hasattr(integration, 'business_integration'):
                    config = integration.business_integration.config
                else:
                    config = integration.agency_integration.config
                openai_api_key = config.get("api_key")
        
        if not openai_api_key:
            raise HTTPException(status_code=400, detail="OpenAI API key not found. Please configure an OpenAI integration.")
        
        # Create the AI prompt for business profile generation
        system_prompt = """You are an expert business analyst. Given the following raw answers from a client intake questionnaire, synthesize a structured, concise but comprehensive business profile. Organize the profile into labeled sections, infer gaps where logical (note assumptions), and flag any potential strategic risks or immediate opportunities. Output must be in JSON following the schema provided. Do not include extraneous filler—be precise, actionable, and use bullet-style summaries where appropriate."""
        
        user_prompt = f"""
        Please analyze the following client questionnaire responses and generate a comprehensive business profile:
        
        {json.dumps(questionnaire_responses, indent=2)}
        
        Please provide the response in the following JSON structure:
        {{
          "business_summary": {{
            "name": "",
            "founder_or_lead": "",
            "industry": "",
            "core_offering": "",
            "value_proposition": ""
          }},
          "customer_profile": {{
            "target_audience": "",
            "primary_pain_points": [],
            "customer_journey_overview": "",
            "competitive_landscape": {{
              "top_competitors": [],
              "differentiators": []
            }}
          }},
          "business_model": {{
            "revenue_streams": [],
            "pricing": "",
            "distribution_channels": []
          }},
          "marketing_and_growth": {{
            "channels": [],
            "what_works": [],
            "growth_challenges": [],
            "quick_wins": []
          }},
          "operations": {{
            "key_processes": [],
            "technology_stack": [],
            "bottlenecks": []
          }},
          "financials_and_metrics": {{
            "primary_kpis": [],
            "current_performance_snapshot": "",
            "financial_pain_points": []
          }},
          "team_and_capacity": {{
            "team_structure": "",
            "constraints": [],
            "opportunities": []
          }},
          "goals_and_vision": {{
            "short_term": [],
            "long_term": [],
            "existential_risks": []
          }},
          "brand_and_positioning": {{
            "desired_perception": "",
            "voice_tone": "",
            "messaging_pillars": []
          }},
          "strategic_risks_and_opportunities": {{
            "risks": [],
            "immediate_opportunities": []
          }},
          "summary_recommendations": []
        }}
        
        Where client answers are missing or vague, infer the most likely scenario and mark it as an assumption.
        Highlight the top 3 strategic priorities based on current challenges vs. goals.
        Provide one "quick win" and one "high-leverage" initiative.
        Keep the entire output machine-readable (valid JSON) but human-friendly—short strings, arrays, and nested objects.
        """
        
        # Call OpenAI API
        response = openai.ChatCompletion.create(
            model=generation_request.ai_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3,
            max_tokens=3000,
            response_format={"type": "json_object"}
        )
        
        # Parse the AI response
        ai_response = response.choices[0].message.content
        business_profile = json.loads(ai_response)
        
        # Save the generated profile in onboarding_data
        onboarding_data = client.onboarding_data or {}
        onboarding_data['business_profile'] = business_profile
        onboarding_data['profile_generated_at'] = datetime.utcnow().isoformat()
        client.onboarding_data = onboarding_data
        client.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(client)
        
        return {
            "message": "Business profile generated successfully",
            "client": client,
            "business_profile": business_profile
        }
        
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse AI response: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate business profile: {str(e)}")

# Get client statistics
@router.get("/{client_id}/stats")
def get_client_stats(
    client_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    # Check if user has access to this business
    accessible_businesses = get_user_businesses(current_user, db)
    business_ids = [b.id for b in accessible_businesses]
    
    client = db.query(models.Business).filter(
        models.Business.id == client_id,
        models.Business.id.in_(business_ids)
    ).first()
    
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    
    # Calculate questionnaire completion percentage
    questionnaire_completion = 0
    questionnaire_responses = client.onboarding_data.get('questionnaire_responses') if client.onboarding_data else None
    if questionnaire_responses:
        total_categories = 12  # Total questionnaire categories
        completed_categories = sum(1 for category in questionnaire_responses.values() if category)
        questionnaire_completion = round((completed_categories / total_categories) * 100)
    
    # Get workflow statistics
    workflow_count = db.query(models.WorkflowInstance).filter(models.WorkflowInstance.business_id == client_id).count()
    
    # Get recent workflow executions
    recent_executions = db.query(models.WorkflowExecution).join(models.WorkflowInstance).filter(
        models.WorkflowInstance.business_id == client_id
    ).order_by(models.WorkflowExecution.created_at.desc()).limit(5).all()
    
    # Get credit information
    credit_pool = db.query(models.CreditPool).filter(
        models.CreditPool.business_id == client_id
    ).first()
    
    has_business_profile = bool(client.onboarding_data.get('business_profile') if client.onboarding_data else False)
    profile_generated_at = client.onboarding_data.get('profile_generated_at') if client.onboarding_data else None
    
    return {
        "client_id": client_id,
        "questionnaire_completion": questionnaire_completion,
        "has_business_profile": has_business_profile,
        "profile_generated_at": profile_generated_at,
        "workflow_count": workflow_count,
        "credits_used": credit_pool.total_purchased - credit_pool.balance if credit_pool else 0,
        "credits_remaining": credit_pool.balance if credit_pool else 0,
        "recent_executions": len(recent_executions),
        "last_activity": client.updated_at
    }