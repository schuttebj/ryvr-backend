from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
import json
import openai
import os

from database import get_db
from auth import get_current_active_user
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
    query = db.query(models.Client).filter(models.Client.owner_id == current_user.id)
    
    if status:
        query = query.filter(models.Client.status == status)
    if industry:
        query = query.filter(models.Client.industry == industry)
    
    clients = query.offset(skip).limit(limit).all()
    return clients

# Get a specific client
@router.get("/{client_id}", response_model=schemas.Client)
def get_client(
    client_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    client = db.query(models.Client).filter(
        models.Client.id == client_id,
        models.Client.owner_id == current_user.id
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
    db_client = models.Client(
        **client.dict(),
        owner_id=current_user.id
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
    client = db.query(models.Client).filter(
        models.Client.id == client_id,
        models.Client.owner_id == current_user.id
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
    client = db.query(models.Client).filter(
        models.Client.id == client_id,
        models.Client.owner_id == current_user.id
    ).first()
    
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    
    db.delete(client)
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
    client = db.query(models.Client).filter(
        models.Client.id == client_id,
        models.Client.owner_id == current_user.id
    ).first()
    
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    
    # Merge with existing questionnaire data
    existing_responses = client.questionnaire_responses or {}
    existing_responses.update(questionnaire_data)
    
    client.questionnaire_responses = existing_responses
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
    
    if not client.questionnaire_responses:
        raise HTTPException(status_code=400, detail="Client must complete questionnaire before generating profile")
    
    try:
        # Get OpenAI API key from environment or integrations
        openai_api_key = os.getenv("OPENAI_API_KEY")
        
        if not openai_api_key:
            # Try to get from user's integrations
            integration = db.query(models.Integration).filter(
                models.Integration.owner_id == current_user.id,
                models.Integration.type == "openai",
                models.Integration.status == "connected"
            ).first()
            
            if integration:
                config = json.loads(integration.config) if isinstance(integration.config, str) else integration.config
                openai_api_key = config.get("apiKey")
        
        if not openai_api_key:
            raise HTTPException(status_code=400, detail="OpenAI API key not found. Please configure an OpenAI integration.")
        
        # Create the AI prompt for business profile generation
        system_prompt = """You are an expert business analyst. Given the following raw answers from a client intake questionnaire, synthesize a structured, concise but comprehensive business profile. Organize the profile into labeled sections, infer gaps where logical (note assumptions), and flag any potential strategic risks or immediate opportunities. Output must be in JSON following the schema provided. Do not include extraneous filler—be precise, actionable, and use bullet-style summaries where appropriate."""
        
        user_prompt = f"""
        Please analyze the following client questionnaire responses and generate a comprehensive business profile:
        
        {json.dumps(client.questionnaire_responses, indent=2)}
        
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
        
        # Save the generated profile
        client.business_profile = business_profile
        client.profile_generated_at = datetime.utcnow()
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
    client = db.query(models.Client).filter(
        models.Client.id == client_id,
        models.Client.owner_id == current_user.id
    ).first()
    
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    
    # Calculate questionnaire completion percentage
    questionnaire_completion = 0
    if client.questionnaire_responses:
        total_categories = 12  # Total questionnaire categories
        completed_categories = sum(1 for category in client.questionnaire_responses.values() if category)
        questionnaire_completion = round((completed_categories / total_categories) * 100)
    
    # Get workflow statistics
    workflow_count = db.query(models.Workflow).filter(models.Workflow.client_id == client_id).count()
    
    # Get recent workflow executions
    recent_executions = db.query(models.WorkflowExecution).join(models.Workflow).filter(
        models.Workflow.client_id == client_id
    ).order_by(models.WorkflowExecution.created_at.desc()).limit(5).all()
    
    return {
        "client_id": client_id,
        "questionnaire_completion": questionnaire_completion,
        "has_business_profile": bool(client.business_profile),
        "profile_generated_at": client.profile_generated_at,
        "workflow_count": workflow_count,
        "credits_used": client.credits_used,
        "credits_remaining": client.credits_balance,
        "recent_executions": len(recent_executions),
        "last_activity": client.updated_at
    }