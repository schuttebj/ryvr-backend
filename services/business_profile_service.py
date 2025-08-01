import json
import openai
import os
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from datetime import datetime

import models

class BusinessProfileService:
    """Service for generating AI-powered business profiles from questionnaire data"""
    
    @staticmethod
    def get_openai_client(db: Session, user_id: int) -> Optional[str]:
        """Get OpenAI API key from environment or user integrations"""
        # First try environment variable
        api_key = os.getenv("OPENAI_API_KEY")
        
        if not api_key:
            # Try to get from user's integrations
            integration = db.query(models.Integration).filter(
                models.Integration.owner_id == user_id,
                models.Integration.type == "openai",
                models.Integration.status == "connected"
            ).first()
            
            if integration:
                config = json.loads(integration.config) if isinstance(integration.config, str) else integration.config
                api_key = config.get("apiKey")
        
        return api_key
    
    @staticmethod
    def create_business_profile_prompt(questionnaire_responses: Dict[str, Any]) -> tuple[str, str]:
        """Create the system and user prompts for business profile generation"""
        
        system_prompt = """You are an expert business analyst. Given the following raw answers from a client intake questionnaire, synthesize a structured, concise but comprehensive business profile. 

Organize the profile into labeled sections, infer gaps where logical (note assumptions), and flag any potential strategic risks or immediate opportunities. 

Output must be in JSON following the exact schema provided. Do not include extraneous filler—be precise, actionable, and use bullet-style summaries where appropriate.

Guidelines:
- Where client answers are missing or vague, infer the most likely scenario and mark it as an assumption
- Highlight the top 3 strategic priorities based on current challenges vs. goals
- Provide one "quick win" and one "high-leverage" initiative
- Keep the entire output machine-readable (valid JSON) but human-friendly—short strings, arrays, and nested objects"""
        
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

Ensure all fields are populated with meaningful content. For arrays, provide at least 2-3 relevant items where possible.
"""
        
        return system_prompt, user_prompt
    
    @staticmethod
    async def generate_business_profile(
        questionnaire_responses: Dict[str, Any],
        api_key: str,
        model: str = "gpt-4o-mini",
        temperature: float = 0.3
    ) -> Dict[str, Any]:
        """Generate a business profile using OpenAI"""
        
        system_prompt, user_prompt = BusinessProfileService.create_business_profile_prompt(questionnaire_responses)
        
        # Call OpenAI API
        response = await openai.ChatCompletion.acreate(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=temperature,
            max_tokens=3000,
            response_format={"type": "json_object"}
        )
        
        # Parse the AI response
        ai_response = response.choices[0].message.content
        business_profile = json.loads(ai_response)
        
        # Add metadata
        business_profile["_metadata"] = {
            "generated_at": datetime.utcnow().isoformat(),
            "model_used": model,
            "temperature": temperature,
            "version": "1.0"
        }
        
        return business_profile
    
    @staticmethod
    def validate_business_profile(profile: Dict[str, Any]) -> bool:
        """Validate that the generated business profile has the required structure"""
        required_sections = [
            "business_summary",
            "customer_profile", 
            "business_model",
            "marketing_and_growth",
            "operations",
            "financials_and_metrics",
            "team_and_capacity",
            "goals_and_vision",
            "brand_and_positioning",
            "strategic_risks_and_opportunities",
            "summary_recommendations"
        ]
        
        return all(section in profile for section in required_sections)
    
    @staticmethod
    def format_profile_for_workflow(profile: Dict[str, Any]) -> Dict[str, Any]:
        """Format business profile data for use in workflow variables"""
        
        formatted = {
            "business_name": profile.get("business_summary", {}).get("name", ""),
            "industry": profile.get("business_summary", {}).get("industry", ""),
            "value_proposition": profile.get("business_summary", {}).get("value_proposition", ""),
            "target_audience": profile.get("customer_profile", {}).get("target_audience", ""),
            "main_challenges": profile.get("strategic_risks_and_opportunities", {}).get("risks", []),
            "opportunities": profile.get("strategic_risks_and_opportunities", {}).get("immediate_opportunities", []),
            "marketing_channels": profile.get("marketing_and_growth", {}).get("channels", []),
            "competitive_advantages": profile.get("customer_profile", {}).get("competitive_landscape", {}).get("differentiators", []),
            "key_metrics": profile.get("financials_and_metrics", {}).get("primary_kpis", []),
            "short_term_goals": profile.get("goals_and_vision", {}).get("short_term", []),
            "long_term_goals": profile.get("goals_and_vision", {}).get("long_term", []),
            "brand_voice": profile.get("brand_and_positioning", {}).get("voice_tone", ""),
            "recommendations": profile.get("summary_recommendations", []),
            "full_profile": profile
        }
        
        return formatted