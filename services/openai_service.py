"""
OpenAI API Service
Provides AI content generation, analysis, and automation capabilities
"""

from openai import OpenAI
from typing import Dict, List, Optional, Any, AsyncIterator
import logging
from datetime import datetime
import json

from config import settings

logger = logging.getLogger(__name__)

class OpenAIService:
    """Enhanced OpenAI API integration service with multi-tier support"""
    
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None, max_completion_tokens: Optional[int] = None):
        # Support both new multi-tier initialization and legacy initialization
        if api_key:
            # New multi-tier initialization
            self.api_key = api_key
            self.default_model = model or "gpt-4o-mini"
            self.default_max_completion_tokens = max_completion_tokens or 32768
        else:
            # Legacy initialization (fallback to settings)
            self.api_key = getattr(settings, 'openai_api_key', None)
            self.default_model = getattr(settings, 'openai_model', "gpt-4o-mini")
            self.default_max_completion_tokens = getattr(settings, 'openai_max_completion_tokens', 32768)
        
        # Initialize client if API key is available
        if self.api_key:
            self.client = OpenAI(api_key=self.api_key)
        else:
            self.client = None
        
    def generate_content(self, 
                        prompt: str, 
                        model: str = "gpt-4o-mini",
                        max_completion_tokens: int = 32768,
                        temperature: float = 1.0,
                        top_p: float = 1.0,
                        frequency_penalty: float = 0.0,
                        presence_penalty: float = 0.0,
                        stop: Optional[List[str]] = None,
                        system_message: Optional[str] = None,
                        response_format: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """Generate content using OpenAI's chat completion API"""
        try:
            messages = []
            
            if system_message:
                messages.append({
                    "role": "system", 
                    "content": [{"type": "text", "text": system_message}]
                })
            
            messages.append({
                "role": "user", 
                "content": [{"type": "text", "text": prompt}]
            })
            
            # Prepare API call parameters
            api_params = {
                "model": model,
                "messages": messages,
                "max_completion_tokens": max_completion_tokens,
                "temperature": temperature,
                "top_p": top_p,
                "frequency_penalty": frequency_penalty,
                "presence_penalty": presence_penalty
            }
            
            # Add optional parameters
            if stop:
                api_params["stop"] = stop
            
            if response_format:
                api_params["response_format"] = response_format
            else:
                api_params["response_format"] = {"type": "text"}
            
            response = self.client.chat.completions.create(**api_params)
            
            return {
                "content": response.choices[0].message.content,
                "model": response.model,
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens
                },
                "finish_reason": response.choices[0].finish_reason
            }
            
        except Exception as e:
            logger.error(f"OpenAI content generation error: {e}")
            raise
    
    def generate_seo_content(self, 
                           keyword: str, 
                           content_type: str = "blog_post",
                           tone: str = "professional",
                           length: int = 800,
                           target_audience: str = "general") -> Dict[str, Any]:
        """Generate SEO-optimized content"""
        
        content_templates = {
            "blog_post": f"""Write a comprehensive {length}-word blog post about '{keyword}' that:
- Targets the '{target_audience}' audience
- Uses a {tone} tone
- Includes relevant headers (H1, H2, H3)
- Naturally incorporates the keyword throughout
- Provides valuable, actionable information
- Includes a compelling introduction and conclusion
- Uses proper SEO structure""",
            
            "product_description": f"""Write a compelling product description for '{keyword}' that:
- Highlights key benefits and features
- Uses a {tone} tone
- Targets '{target_audience}' customers
- Includes relevant keywords naturally
- Is approximately {length} words
- Drives conversions""",
            
            "meta_description": f"""Write a meta description for '{keyword}' that:
- Is exactly 150-160 characters
- Uses a {tone} tone
- Includes the target keyword
- Compels users to click
- Accurately describes the content""",
            
            "social_media": f"""Create social media content about '{keyword}' that:
- Uses a {tone} tone
- Targets '{target_audience}' audience
- Is engaging and shareable
- Includes relevant hashtags
- Encourages interaction""",
            
            "email_campaign": f"""Write an email campaign about '{keyword}' that:
- Uses a {tone} tone
- Targets '{target_audience}' subscribers
- Includes compelling subject line
- Has clear call-to-action
- Is approximately {length} words
- Drives engagement"""
        }
        
        prompt = content_templates.get(content_type, content_templates["blog_post"])
        
        system_message = f"""You are an expert content writer and SEO specialist. Create high-quality, 
        engaging content that ranks well in search engines and provides value to readers. 
        Focus on natural keyword integration and readability."""
        
        return self.generate_content(
            prompt=prompt,
            system_message=system_message,
            temperature=0.7,
            max_completion_tokens=32768 if length > 800 else 16384
        )
    
    def analyze_content(self, 
                       content: str, 
                       keyword: str,
                       analysis_type: str = "seo") -> Dict[str, Any]:
        """Analyze content for SEO, readability, and quality"""
        
        analysis_prompts = {
            "seo": f"""Analyze the following content for SEO optimization targeting the keyword '{keyword}':

Content: {content}

Provide analysis on:
1. Keyword density and distribution
2. Header structure (H1, H2, H3)
3. Content quality and relevance
4. Readability score
5. Missing SEO elements
6. Improvement suggestions

Return your analysis in JSON format with scores and recommendations.""",
            
            "readability": f"""Analyze the following content for readability and user experience:

Content: {content}

Provide analysis on:
1. Reading level and complexity
2. Sentence structure and length
3. Paragraph organization
4. Engagement factors
5. Clarity improvements
6. User experience recommendations

Return your analysis in JSON format.""",
            
            "competitive": f"""Analyze the following content for competitive advantage:

Content: {content}
Target keyword: {keyword}

Provide analysis on:
1. Unique value proposition
2. Content depth and coverage
3. Competitive differentiation
4. Market positioning
5. Content gaps
6. Enhancement opportunities

Return your analysis in JSON format."""
        }
        
        prompt = analysis_prompts.get(analysis_type, analysis_prompts["seo"])
        
        system_message = """You are an expert content analyst specializing in SEO, readability, 
        and content strategy. Provide detailed, actionable analysis with specific recommendations."""
        
        return self.generate_content(
            prompt=prompt,
            system_message=system_message,
            temperature=0.3,
            max_completion_tokens=16384
        )
    
    def generate_keywords(self, 
                         topic: str, 
                         industry: str = "general",
                         keyword_type: str = "long_tail",
                         count: int = 20) -> Dict[str, Any]:
        """Generate keyword suggestions for a given topic"""
        
        prompt = f"""Generate {count} {keyword_type} keywords for the topic '{topic}' in the {industry} industry.

Requirements:
- Focus on search intent and user queries
- Include various match types (broad, phrase, exact)
- Consider commercial and informational keywords
- Provide search volume estimates (high/medium/low)
- Include difficulty level (easy/medium/hard)

Return the results in JSON format with the following structure:
{{
  "keywords": [
    {{
      "keyword": "example keyword",
      "type": "long_tail",
      "intent": "informational",
      "volume": "medium",
      "difficulty": "easy"
    }}
  ]
}}"""
        
        system_message = """You are an expert keyword researcher with deep knowledge of SEO 
        and search behavior. Generate relevant, high-value keywords that users actually search for."""
        
        return self.generate_content(
            prompt=prompt,
            system_message=system_message,
            temperature=0.4,
            max_completion_tokens=16384
        )
    
    def generate_ad_copy(self, 
                        product: str, 
                        platform: str = "google_ads",
                        campaign_type: str = "search",
                        target_audience: str = "general") -> Dict[str, Any]:
        """Generate ad copy for various platforms"""
        
        platform_specs = {
            "google_ads": {
                "headlines": "3 headlines, 30 characters each",
                "descriptions": "2 descriptions, 90 characters each",
                "format": "Google Ads format"
            },
            "facebook_ads": {
                "headlines": "1 headline, 40 characters",
                "descriptions": "1 description, 125 characters",
                "format": "Facebook Ads format"
            },
            "linkedin_ads": {
                "headlines": "1 headline, 50 characters",
                "descriptions": "1 description, 150 characters",
                "format": "LinkedIn Ads format"
            }
        }
        
        spec = platform_specs.get(platform, platform_specs["google_ads"])
        
        prompt = f"""Create compelling ad copy for '{product}' on {platform}:

Platform: {platform}
Campaign Type: {campaign_type}
Target Audience: {target_audience}

Requirements:
- {spec['headlines']}
- {spec['descriptions']}
- Include strong call-to-action
- Highlight unique selling propositions
- Use persuasive language
- Follow {spec['format']} best practices

Return the results in JSON format with headlines and descriptions."""
        
        system_message = """You are an expert copywriter specializing in high-converting ad copy. 
        Create compelling, action-oriented copy that drives clicks and conversions."""
        
        return self.generate_content(
            prompt=prompt,
            system_message=system_message,
            temperature=0.8,
            max_completion_tokens=8192
        )
    
    def generate_email_sequence(self, 
                              topic: str, 
                              sequence_type: str = "welcome",
                              email_count: int = 5,
                              tone: str = "professional") -> Dict[str, Any]:
        """Generate email sequence for marketing campaigns"""
        
        sequence_templates = {
            "welcome": f"Create a {email_count}-email welcome sequence for new subscribers about '{topic}'",
            "nurture": f"Create a {email_count}-email nurture sequence for leads interested in '{topic}'",
            "onboarding": f"Create a {email_count}-email onboarding sequence for new users of '{topic}'",
            "re_engagement": f"Create a {email_count}-email re-engagement sequence for inactive subscribers about '{topic}'",
            "product_launch": f"Create a {email_count}-email product launch sequence for '{topic}'"
        }
        
        prompt = f"""{sequence_templates.get(sequence_type, sequence_templates['welcome'])}

Requirements:
- Use a {tone} tone
- Include compelling subject lines
- Progressive value delivery
- Clear call-to-actions
- Personalization opportunities
- Mobile-friendly format

Return the results in JSON format with each email including:
- Subject line
- Preview text
- Body content
- Call-to-action
- Send timing (days from start)"""
        
        system_message = """You are an expert email marketer with deep knowledge of 
        customer psychology and email best practices. Create sequences that build 
        relationships and drive desired actions."""
        
        return self.generate_content(
            prompt=prompt,
            system_message=system_message,
            temperature=0.7,
            max_completion_tokens=32768
        )
    
    def standardize_response(self, raw_response: Dict, task_type: str) -> Dict[str, Any]:
        """Standardize OpenAI response to RYVR format"""
        return {
            'provider': 'OpenAI',
            'task_type': task_type,
            'timestamp': datetime.utcnow().isoformat(),
            'status': 'success',
            'credits_used': raw_response.get('usage', {}).get('total_tokens', 0),
            'model': raw_response.get('model', 'unknown'),
            'data': {
                'content': raw_response.get('content', ''),
                'usage': raw_response.get('usage', {}),
                'finish_reason': raw_response.get('finish_reason', '')
            }
        }
    
    def batch_generate(self, 
                      prompts: List[str], 
                      model: str = "gpt-4o-mini",
                      **kwargs) -> List[Dict[str, Any]]:
        """Generate content for multiple prompts"""
        results = []
        
        for prompt in prompts:
            try:
                result = self.generate_content(prompt=prompt, model=model, **kwargs)
                results.append(result)
            except Exception as e:
                logger.error(f"Batch generation error for prompt: {e}")
                results.append({
                    "error": str(e),
                    "prompt": prompt[:100] + "..." if len(prompt) > 100 else prompt
                })
        
        return results
    
    def get_available_models(self) -> List[Dict[str, Any]]:
        """Get available models from database instead of API"""
        from services.openai_model_service import OpenAIModelService
        try:
            # This should be called with a database session
            # For now, return fallback models - this method should be deprecated
            logger.warning("get_available_models called without database session, returning fallback models")
            return [
                {"id": "gpt-4o", "created": 0, "owned_by": "openai"},
                {"id": "gpt-4o-mini", "created": 0, "owned_by": "openai"},
                {"id": "gpt-4-turbo", "created": 0, "owned_by": "openai"},
                {"id": "gpt-3.5-turbo", "created": 0, "owned_by": "openai"}
            ]
            
        except Exception as e:
            logger.error(f"Failed to get available models: {e}")
            return [
                {"id": "gpt-4o", "created": 0, "owned_by": "openai"},
                {"id": "gpt-4o-mini", "created": 0, "owned_by": "openai"},
                {"id": "gpt-4-turbo", "created": 0, "owned_by": "openai"},
                {"id": "gpt-3.5-turbo", "created": 0, "owned_by": "openai"}
            ]
    
    def get_recommended_model(self, task_type: str = "general") -> str:
        """Get recommended model based on task type"""
        # Get available models
        models = self.get_available_models()
        
        # Define preferences based on task type
        preferences = {
            "general": ["gpt-4o-mini", "gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"],
            "complex": ["gpt-4o", "gpt-4-turbo", "gpt-4o-mini", "gpt-3.5-turbo"],
            "fast": ["gpt-4o-mini", "gpt-3.5-turbo", "gpt-4o", "gpt-4-turbo"],
            "creative": ["gpt-4o", "gpt-4-turbo", "gpt-4o-mini", "gpt-3.5-turbo"]
        }
        
        preferred_models = preferences.get(task_type, preferences["general"])
        available_model_ids = [model["id"] for model in models]
        
        # Return first available preferred model
        for preferred_model in preferred_models:
            if preferred_model in available_model_ids:
                return preferred_model
        
        # Fallback to first available model or default
        return available_model_ids[0] if available_model_ids else "gpt-4o-mini"
    
    # =============================================================================
    # NEW INTEGRATION FRAMEWORK METHODS
    # =============================================================================
    
    async def test_connection(self) -> Dict[str, Any]:
        """Test OpenAI API connection"""
        try:
            if not self.client:
                return {
                    "success": False,
                    "error": "OpenAI API key not configured"
                }
            
            # Test with a simple completion
            response = self.client.chat.completions.create(
                model=self.default_model,
                messages=[{
                    "role": "user", 
                    "content": [{"type": "text", "text": "Test connection"}]
                }],
                max_completion_tokens=5,
                temperature=0,
                response_format={"type": "text"}
            )
            
            if response and response.choices:
                return {
                    "success": True,
                    "message": "OpenAI connection successful",
                    "model": self.default_model,
                    "response": response.choices[0].message.content
                }
            else:
                return {
                    "success": False,
                    "error": "OpenAI API returned empty response"
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": f"OpenAI connection test failed: {str(e)}"
            }
    
    async def generate_completion(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_completion_tokens: Optional[int] = None,
        model: Optional[str] = None
    ) -> Dict[str, Any]:
        """Generate completion for integration framework"""
        try:
            if not self.client:
                raise Exception("OpenAI API key not configured")
            
            # Use provided parameters or defaults
            model = model or self.default_model
            max_completion_tokens = max_completion_tokens or self.default_max_completion_tokens
            
            messages = []
            
            if system_prompt:
                messages.append({
                    "role": "system", 
                    "content": [{"type": "text", "text": system_prompt}]
                })
            
            messages.append({
                "role": "user", 
                "content": [{"type": "text", "text": prompt}]
            })
            
            response = self.client.chat.completions.create(
                model=model,
                messages=messages,
                max_completion_tokens=max_completion_tokens,
                temperature=temperature,
                response_format={"type": "text"}
            )
            
            if response and response.choices:
                return {
                    "success": True,
                    "content": response.choices[0].message.content,
                    "model": model,
                    "usage": {
                        "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                        "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                        "total_tokens": response.usage.total_tokens if response.usage else 0
                    },
                    "finish_reason": response.choices[0].finish_reason
                }
            else:
                raise Exception("OpenAI API returned empty response")
                
        except Exception as e:
            logger.error(f"OpenAI completion generation failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "prompt": prompt[:100] + "..." if len(prompt) > 100 else prompt
            }
    
    async def analyze_content(
        self,
        content: str,
        analysis_type: str = "general",
        instructions: Optional[str] = None
    ) -> Dict[str, Any]:
        """Analyze content using OpenAI for integration framework"""
        try:
            if not self.client:
                raise Exception("OpenAI API key not configured")
            
            # Prepare analysis prompt based on type
            if analysis_type == "seo":
                system_prompt = "You are an SEO expert. Analyze the provided content for SEO optimization opportunities."
                prompt = f"Analyze this content for SEO: {content}"
            elif analysis_type == "sentiment":
                system_prompt = "You are a sentiment analysis expert. Analyze the sentiment of the provided content."
                prompt = f"Analyze the sentiment of this content: {content}"
            elif analysis_type == "keywords":
                system_prompt = "You are a keyword research expert. Extract and suggest relevant keywords from the provided content."
                prompt = f"Extract keywords from this content: {content}"
            else:
                system_prompt = "You are a content analysis expert. Provide a comprehensive analysis of the provided content."
                prompt = f"Analyze this content: {content}"
            
            # Add custom instructions if provided
            if instructions:
                prompt += f"\n\nAdditional instructions: {instructions}"
            
            result = await self.generate_completion(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=0.3  # Lower temperature for analysis
            )
            
            if result.get("success"):
                return {
                    "success": True,
                    "analysis": result["content"],
                    "analysis_type": analysis_type,
                    "usage": result.get("usage", {})
                }
            else:
                return result
                
        except Exception as e:
            logger.error(f"OpenAI content analysis failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "analysis_type": analysis_type
            }

# Service instance (legacy compatibility)
openai_service = OpenAIService() 