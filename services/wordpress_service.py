"""
WordPress Integration Service
Handles communication with WordPress sites via the RYVR WordPress plugin REST API
"""

import asyncio
import aiohttp
import logging
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from datetime import datetime

logger = logging.getLogger(__name__)

class WordPressService:
    """Service for communicating with WordPress sites via RYVR plugin"""
    
    def __init__(self, site_url: str, api_key: str, db: Session):
        self.site_url = site_url.rstrip('/')
        self.api_key = api_key
        self.db = db
        self.timeout = 30
        
        # WordPress plugin REST API endpoints
        self.endpoints = {
            'extract_posts': '/wp-json/ryvr/v1/content/posts',
            'get_single_post': '/wp-json/ryvr/v1/content/posts/{id}',
            'publish_content': '/wp-json/ryvr/v1/content/publish',
            'update_content': '/wp-json/ryvr/v1/content/update/{id}',
            'delete_content': '/wp-json/ryvr/v1/content/delete/{id}',
            'get_site_info': '/wp-json/ryvr/v1/site/info',
            'get_users': '/wp-json/ryvr/v1/site/users',
            'get_post_types': '/wp-json/ryvr/v1/site/post-types',
            'get_taxonomies': '/wp-json/ryvr/v1/site/taxonomies',
            'trigger_sync': '/wp-json/ryvr/v1/sync/trigger',
            'get_sync_logs': '/wp-json/ryvr/v1/sync/logs',
            'integration_status': '/wp-json/ryvr/v1/integration/status'
        }
    
    async def _make_request(self, method: str, endpoint: str, data: Optional[Dict] = None, params: Optional[Dict] = None) -> Dict[str, Any]:
        """Make authenticated request to WordPress plugin API"""
        url = f"{self.site_url}{endpoint}"
        
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
            'User-Agent': 'RYVR-Backend/1.0'
        }
        
        timeout = aiohttp.ClientTimeout(total=self.timeout)
        
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.request(
                    method=method.upper(),
                    url=url,
                    headers=headers,
                    json=data,
                    params=params
                ) as response:
                    
                    if response.content_type == 'application/json':
                        result = await response.json()
                    else:
                        result = {'text': await response.text()}
                    
                    if response.status >= 400:
                        logger.error(f"WordPress API error {response.status}: {result}")
                        return {
                            'success': False,
                            'error': f"HTTP {response.status}: {result.get('message', 'Unknown error')}",
                            'status_code': response.status
                        }
                    
                    return {
                        'success': True,
                        'data': result,
                        'status_code': response.status
                    }
                    
        except asyncio.TimeoutError:
            logger.error(f"WordPress API timeout for {url}")
            return {
                'success': False,
                'error': 'Request timeout',
                'status_code': 408
            }
        except Exception as e:
            logger.error(f"WordPress API request failed: {e}")
            return {
                'success': False,
                'error': str(e),
                'status_code': 500
            }
    
    async def extract_posts(self, post_type: str = "post", status: str = "any", 
                          limit: int = 50, modified_after: Optional[str] = None,
                          include_acf: bool = True, include_seo: bool = True, 
                          include_taxonomies: bool = True) -> Dict[str, Any]:
        """Extract posts from WordPress"""
        
        params = {
            'post_type': post_type,
            'status': status,
            'limit': min(limit, 100),  # Enforce maximum limit
            'offset': 0
        }
        
        if modified_after:
            params['modified_after'] = modified_after
        
        response = await self._make_request('GET', self.endpoints['extract_posts'], params=params)
        
        if not response['success']:
            return response
        
        posts_data = response['data']
        
        # Filter and enhance data based on include flags
        if 'data' in posts_data and isinstance(posts_data['data'], list):
            for post in posts_data['data']:
                if not include_acf and 'acf_fields' in post:
                    del post['acf_fields']
                if not include_seo and 'rankmath_seo' in post:
                    del post['rankmath_seo']
                if not include_taxonomies and 'taxonomies' in post:
                    del post['taxonomies']
        
        return posts_data
    
    async def get_single_post(self, post_id: int) -> Dict[str, Any]:
        """Get a single post by ID"""
        endpoint = self.endpoints['get_single_post'].format(id=post_id)
        return await self._make_request('GET', endpoint)
    
    async def publish_content(self, content_data: Dict[str, Any]) -> Dict[str, Any]:
        """Publish content to WordPress"""
        
        # Validate required fields
        if not content_data.get('title'):
            return {
                'success': False,
                'error': 'Title is required for content publishing'
            }
        
        # Prepare data for WordPress plugin
        wordpress_data = {
            'title': content_data['title'],
            'content': content_data.get('content', ''),
            'excerpt': content_data.get('excerpt', ''),
            'status': content_data.get('status', 'draft'),
            'post_type': content_data.get('post_type', 'post'),
            'slug': content_data.get('slug'),
            'author': content_data.get('author'),
            'acf_fields': content_data.get('acf_fields'),
            'rankmath_seo': content_data.get('rankmath_seo'),
            'taxonomies': content_data.get('taxonomies'),
            'featured_image': content_data.get('featured_image'),
            'custom_fields': content_data.get('custom_fields'),
            'ryvr_post_id': content_data.get('ryvr_post_id')
        }
        
        # Remove None values
        wordpress_data = {k: v for k, v in wordpress_data.items() if v is not None}
        
        return await self._make_request('POST', self.endpoints['publish_content'], data=wordpress_data)
    
    async def update_content(self, post_id: int, content_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update existing WordPress content"""
        endpoint = self.endpoints['update_content'].format(id=post_id)
        
        # Remove None values
        wordpress_data = {k: v for k, v in content_data.items() if v is not None}
        
        return await self._make_request('PUT', endpoint, data=wordpress_data)
    
    async def delete_content(self, post_id: int) -> Dict[str, Any]:
        """Delete WordPress content"""
        endpoint = self.endpoints['delete_content'].format(id=post_id)
        return await self._make_request('DELETE', endpoint)
    
    async def get_site_info(self) -> Dict[str, Any]:
        """Get WordPress site information"""
        return await self._make_request('GET', self.endpoints['get_site_info'])
    
    async def get_users(self, limit: int = 50, offset: int = 0) -> Dict[str, Any]:
        """Get WordPress users"""
        params = {
            'limit': min(limit, 100),
            'offset': offset
        }
        return await self._make_request('GET', self.endpoints['get_users'], params=params)
    
    async def get_post_types(self) -> Dict[str, Any]:
        """Get available post types"""
        return await self._make_request('GET', self.endpoints['get_post_types'])
    
    async def get_taxonomies(self, post_type: Optional[str] = None) -> Dict[str, Any]:
        """Get available taxonomies"""
        params = {}
        if post_type:
            params['post_type'] = post_type
        
        return await self._make_request('GET', self.endpoints['get_taxonomies'], params=params)
    
    async def sync_content(self, direction: str = "both", post_ids: Optional[List[int]] = None,
                          sync_acf: bool = True, sync_seo: bool = True, 
                          sync_taxonomies: bool = True, conflict_resolution: str = "skip") -> Dict[str, Any]:
        """Trigger content synchronization"""
        
        sync_data = {
            'direction': direction,
            'post_ids': post_ids,
            'sync_acf': sync_acf,
            'sync_seo': sync_seo,
            'sync_taxonomies': sync_taxonomies,
            'conflict_resolution': conflict_resolution
        }
        
        # Remove None values
        sync_data = {k: v for k, v in sync_data.items() if v is not None}
        
        return await self._make_request('POST', self.endpoints['trigger_sync'], data=sync_data)
    
    async def get_sync_logs(self, limit: int = 50, offset: int = 0) -> Dict[str, Any]:
        """Get synchronization logs"""
        params = {
            'limit': min(limit, 100),
            'offset': offset
        }
        return await self._make_request('GET', self.endpoints['get_sync_logs'], params=params)
    
    async def get_integration_status(self) -> Dict[str, Any]:
        """Get WordPress integration status"""
        return await self._make_request('GET', self.endpoints['integration_status'])
    
    async def test_connection(self) -> Dict[str, Any]:
        """Test connection to WordPress site"""
        try:
            # Try to get site info as a connection test
            result = await self.get_site_info()
            
            if result['success']:
                return {
                    'success': True,
                    'message': 'Connection successful',
                    'site_info': result['data']
                }
            else:
                return {
                    'success': False,
                    'message': f"Connection failed: {result.get('error', 'Unknown error')}"
                }
                
        except Exception as e:
            return {
                'success': False,
                'message': f"Connection test failed: {str(e)}"
            }
    
    async def validate_api_key(self) -> Dict[str, Any]:
        """Validate API key with WordPress plugin"""
        try:
            result = await self.get_integration_status()
            
            if result['success']:
                return {
                    'valid': True,
                    'message': 'API key is valid',
                    'status': result['data']
                }
            else:
                return {
                    'valid': False,
                    'message': 'API key validation failed',
                    'error': result.get('error')
                }
                
        except Exception as e:
            return {
                'valid': False,
                'message': f"API key validation error: {str(e)}"
            }
    
    # Utility methods
    
    def get_full_url(self, endpoint: str) -> str:
        """Get full URL for an endpoint"""
        return f"{self.site_url}{endpoint}"
    
    def is_configured(self) -> bool:
        """Check if service is properly configured"""
        return bool(self.site_url and self.api_key)
    
    async def get_capabilities(self) -> Dict[str, Any]:
        """Get WordPress site capabilities"""
        try:
            site_info = await self.get_site_info()
            post_types = await self.get_post_types()
            integration_status = await self.get_integration_status()
            
            capabilities = {
                'site_configured': site_info['success'],
                'post_types_available': post_types['success'],
                'integration_active': integration_status['success'],
                'acf_available': False,
                'rankmath_available': False,
                'sync_enabled': False
            }
            
            if integration_status['success'] and 'data' in integration_status:
                status_data = integration_status['data']
                capabilities.update({
                    'acf_available': status_data.get('acf_active', False),
                    'rankmath_available': status_data.get('rankmath_active', False),
                    'sync_enabled': status_data.get('sync_enabled', False)
                })
            
            return {
                'success': True,
                'capabilities': capabilities
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f"Failed to get capabilities: {str(e)}"
            }
