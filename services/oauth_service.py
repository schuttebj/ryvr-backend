"""
OAuth 2.0 Service
Handles authorization flows, token exchange, and token refresh for OAuth integrations
"""

import httpx
import secrets
import logging
from typing import Dict, Optional, Any
from datetime import datetime, timedelta
from urllib.parse import urlencode
from sqlalchemy.orm import Session

import models

logger = logging.getLogger(__name__)


class OAuthService:
    """
    Service for managing OAuth 2.0 authentication flows.
    Supports authorization code flow with PKCE and automatic token refresh.
    """
    
    def __init__(self, db: Session):
        self.db = db
        self._pending_states: Dict[str, Dict[str, Any]] = {}  # In-memory state storage (consider Redis in production)
    
    def generate_authorization_url(
        self,
        integration_id: int,
        business_id: int,
        redirect_uri: str,
        user_id: int
    ) -> Dict[str, Any]:
        """
        Generate OAuth authorization URL for user to grant permissions
        
        Args:
            integration_id: ID of the integration
            business_id: Business to connect integration to
            redirect_uri: Callback URL after authorization
            user_id: User initiating the connection
            
        Returns:
            Dict with authorization_url and state
        """
        try:
            # Load integration
            integration = self.db.query(models.Integration).filter(
                models.Integration.id == integration_id,
                models.Integration.is_active == True
            ).first()
            
            if not integration or not integration.oauth_config:
                raise ValueError("Integration not found or OAuth not configured")
            
            oauth_config = integration.oauth_config
            
            # Generate state parameter for CSRF protection
            state = secrets.token_urlsafe(32)
            
            # Store state with context
            self._pending_states[state] = {
                "integration_id": integration_id,
                "business_id": business_id,
                "user_id": user_id,
                "created_at": datetime.utcnow(),
                "redirect_uri": redirect_uri
            }
            
            # Build authorization URL
            auth_params = {
                "client_id": oauth_config.get("client_id", ""),
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "state": state,
                "scope": " ".join(oauth_config.get("scopes", [])),
                "access_type": "offline",  # Request refresh token
                "prompt": "consent"  # Force consent to get refresh token
            }
            
            # Add any provider-specific parameters
            extra_params = oauth_config.get("extra_auth_params", {})
            auth_params.update(extra_params)
            
            auth_url = oauth_config["auth_url"]
            authorization_url = f"{auth_url}?{urlencode(auth_params)}"
            
            logger.info(f"Generated OAuth URL for integration {integration_id}, business {business_id}")
            
            return {
                "authorization_url": authorization_url,
                "state": state
            }
            
        except Exception as e:
            logger.error(f"Failed to generate authorization URL: {e}", exc_info=True)
            raise
    
    async def handle_callback(
        self,
        code: str,
        state: str,
        redirect_uri: str
    ) -> Dict[str, Any]:
        """
        Handle OAuth callback and exchange authorization code for tokens
        
        Args:
            code: Authorization code from provider
            state: State parameter for validation
            redirect_uri: Redirect URI used in authorization request
            
        Returns:
            Dict with success status and integration details
        """
        try:
            # Validate state
            if state not in self._pending_states:
                return {
                    "success": False,
                    "error": "Invalid or expired state parameter"
                }
            
            state_data = self._pending_states.pop(state)
            integration_id = state_data["integration_id"]
            business_id = state_data["business_id"]
            user_id = state_data["user_id"]
            
            # Load integration
            integration = self.db.query(models.Integration).filter(
                models.Integration.id == integration_id
            ).first()
            
            if not integration:
                return {
                    "success": False,
                    "error": "Integration not found"
                }
            
            oauth_config = integration.oauth_config
            
            # Exchange code for tokens
            tokens = await self._exchange_code_for_tokens(
                oauth_config,
                code,
                redirect_uri
            )
            
            if not tokens.get("access_token"):
                return {
                    "success": False,
                    "error": "Failed to obtain access token"
                }
            
            # Store tokens in BusinessIntegration
            await self._store_tokens(
                integration_id,
                business_id,
                tokens,
                oauth_config
            )
            
            logger.info(f"Successfully connected OAuth integration {integration_id} for business {business_id}")
            
            return {
                "success": True,
                "integration_id": integration_id,
                "business_id": business_id,
                "integration_name": integration.name
            }
            
        except Exception as e:
            logger.error(f"OAuth callback failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _exchange_code_for_tokens(
        self,
        oauth_config: Dict[str, Any],
        code: str,
        redirect_uri: str
    ) -> Dict[str, Any]:
        """Exchange authorization code for access and refresh tokens"""
        
        token_url = oauth_config["token_url"]
        
        token_params = {
            "client_id": oauth_config.get("client_id", ""),
            "client_secret": oauth_config.get("client_secret", ""),
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code"
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                token_url,
                data=token_params,
                headers={"Accept": "application/json"}
            )
            
            if response.status_code != 200:
                logger.error(f"Token exchange failed: {response.status_code} - {response.text}")
                raise Exception(f"Token exchange failed: {response.text}")
            
            return response.json()
    
    async def _store_tokens(
        self,
        integration_id: int,
        business_id: int,
        tokens: Dict[str, Any],
        oauth_config: Dict[str, Any]
    ):
        """Store OAuth tokens in BusinessIntegration"""
        
        # Check if business integration already exists
        business_integration = self.db.query(models.BusinessIntegration).filter(
            models.BusinessIntegration.business_id == business_id,
            models.BusinessIntegration.integration_id == integration_id
        ).first()
        
        # Prepare credentials
        credentials = {
            "access_token": tokens["access_token"],
            "refresh_token": tokens.get("refresh_token"),
            "expires_at": None,
            "token_type": tokens.get("token_type", "Bearer"),
            "scope": tokens.get("scope", "")
        }
        
        # Calculate expiration time
        if "expires_in" in tokens:
            expires_at = datetime.utcnow() + timedelta(seconds=tokens["expires_in"])
            credentials["expires_at"] = expires_at.isoformat()
        
        # Extract account info if available (provider-specific)
        if "account_info" in tokens:
            credentials["account_info"] = tokens["account_info"]
        
        if business_integration:
            # Update existing
            business_integration.credentials = credentials
            business_integration.is_active = True
            business_integration.last_tested = datetime.utcnow()
        else:
            # Create new
            business_integration = models.BusinessIntegration(
                business_id=business_id,
                integration_id=integration_id,
                credentials=credentials,
                custom_config={},
                is_active=True
            )
            self.db.add(business_integration)
        
        self.db.commit()
        self.db.refresh(business_integration)
        
        return business_integration
    
    async def refresh_access_token(
        self,
        business_integration: models.BusinessIntegration
    ) -> Dict[str, Any]:
        """
        Refresh expired OAuth access token
        
        Args:
            business_integration: BusinessIntegration with expired token
            
        Returns:
            Updated credentials dict with new access token
        """
        try:
            integration = business_integration.integration
            
            if not integration.oauth_config:
                raise ValueError("OAuth not configured for this integration")
            
            oauth_config = integration.oauth_config
            credentials = business_integration.credentials
            
            refresh_token = credentials.get("refresh_token")
            if not refresh_token:
                raise ValueError("No refresh token available")
            
            # Request new access token
            token_url = oauth_config["token_url"]
            
            token_params = {
                "client_id": oauth_config.get("client_id", ""),
                "client_secret": oauth_config.get("client_secret", ""),
                "refresh_token": refresh_token,
                "grant_type": "refresh_token"
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    token_url,
                    data=token_params,
                    headers={"Accept": "application/json"}
                )
                
                if response.status_code != 200:
                    logger.error(f"Token refresh failed: {response.status_code} - {response.text}")
                    raise Exception(f"Token refresh failed: {response.text}")
                
                new_tokens = response.json()
            
            # Update credentials
            credentials["access_token"] = new_tokens["access_token"]
            
            if "refresh_token" in new_tokens:
                credentials["refresh_token"] = new_tokens["refresh_token"]
            
            if "expires_in" in new_tokens:
                expires_at = datetime.utcnow() + timedelta(seconds=new_tokens["expires_in"])
                credentials["expires_at"] = expires_at.isoformat()
            
            # Save updated credentials
            business_integration.credentials = credentials
            self.db.commit()
            
            logger.info(f"Successfully refreshed token for business integration {business_integration.id}")
            
            return credentials
            
        except Exception as e:
            logger.error(f"Failed to refresh access token: {e}", exc_info=True)
            raise
    
    def is_token_expired(self, credentials: Dict[str, Any]) -> bool:
        """Check if access token is expired"""
        
        expires_at_str = credentials.get("expires_at")
        if not expires_at_str:
            return False  # No expiration info, assume valid
        
        try:
            expires_at = datetime.fromisoformat(expires_at_str)
            # Add 5-minute buffer
            return datetime.utcnow() >= (expires_at - timedelta(minutes=5))
        except:
            return False
    
    async def ensure_valid_token(
        self,
        business_integration: models.BusinessIntegration
    ) -> Dict[str, Any]:
        """
        Ensure business integration has a valid access token, refreshing if necessary
        
        Args:
            business_integration: BusinessIntegration to check
            
        Returns:
            Valid credentials dict
        """
        credentials = business_integration.credentials
        
        if self.is_token_expired(credentials):
            logger.info(f"Token expired for business integration {business_integration.id}, refreshing...")
            credentials = await self.refresh_access_token(business_integration)
        
        return credentials
    
    def disconnect_integration(
        self,
        business_id: int,
        integration_id: int
    ) -> bool:
        """
        Disconnect OAuth integration by removing credentials
        
        Args:
            business_id: Business ID
            integration_id: Integration ID
            
        Returns:
            Success status
        """
        try:
            business_integration = self.db.query(models.BusinessIntegration).filter(
                models.BusinessIntegration.business_id == business_id,
                models.BusinessIntegration.integration_id == integration_id
            ).first()
            
            if business_integration:
                business_integration.credentials = {}
                business_integration.is_active = False
                self.db.commit()
                
                logger.info(f"Disconnected integration {integration_id} from business {business_id}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to disconnect integration: {e}")
            return False

