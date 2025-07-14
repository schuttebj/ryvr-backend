from pydantic import BaseSettings
from typing import Optional
import os

class Settings(BaseSettings):
    # Database
    database_url: str = os.getenv(
        "DATABASE_URL", 
        "postgresql://ryvr_user:Iodphi5TaXFwShKSvWiECxyGSRoTn93h@dpg-d1qmjl0dl3ps739393u0-a.oregon-postgres.render.com/ryvr"
    )
    
    # JWT
    secret_key: str = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    
    # API Keys
    openai_api_key: Optional[str] = os.getenv("OPENAI_API_KEY")
    dataforseo_username: Optional[str] = os.getenv("DATAFORSEO_USERNAME")
    dataforseo_password: Optional[str] = os.getenv("DATAFORSEO_PASSWORD")
    dataforseo_base_url: str = "https://sandbox.dataforseo.com"  # Sandbox environment
    
    # Environment
    environment: str = os.getenv("ENVIRONMENT", "production")
    debug: bool = os.getenv("DEBUG", "false").lower() == "true"
    
    class Config:
        env_file = ".env"
        case_sensitive = False

# Create global settings instance
settings = Settings() 