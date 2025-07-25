"""
DataForSEO API Service
Provides SEO analysis, keyword research, and SERP data
"""

from http.client import HTTPSConnection
from base64 import b64encode
from json import loads, dumps
from typing import Dict, List, Optional, Any
import logging
from datetime import datetime

from config import settings

logger = logging.getLogger(__name__)

class DataForSEOService:
    """DataForSEO API integration service"""
    
    def __init__(self):
        self.domain = "sandbox.dataforseo.com"  # Sandbox environment
        self.username = settings.dataforseo_username
        self.password = settings.dataforseo_password
        self.base_url = settings.dataforseo_base_url
        
    def _request(self, path: str, method: str = "GET", data: Optional[Dict] = None) -> Dict:
        """Make authenticated request to DataForSEO API"""
        connection = HTTPSConnection(self.domain)
        try:
            # Base64 encode credentials
            base64_bytes = b64encode(
                f"{self.username}:{self.password}".encode("ascii")
            ).decode("ascii")
            
            headers = {
                'Authorization': f'Basic {base64_bytes}',
                'Content-Type': 'application/json'
            }
            
            body = None
            if data:
                body = dumps(data) if not isinstance(data, str) else data
                
            connection.request(method, path, headers=headers, body=body)
            response = connection.getresponse()
            
            result = loads(response.read().decode())
            
            # Log API usage
            logger.info(f"DataForSEO API call: {method} {path} - Status: {result.get('status_code', 'Unknown')}")
            
            return result
            
        except Exception as e:
            logger.error(f"DataForSEO API error: {e}")
            raise
        finally:
            connection.close()
    
    def get_account_info(self) -> Dict:
        """Get account information and credits"""
        return self._request('/v3/appendix/user_data')
    
    def get_locations(self, country_code: Optional[str] = None) -> List[Dict]:
        """Get available locations for SERP analysis"""
        path = '/v3/serp/google/organic/locations'
        if country_code:
            path += f'?country_code={country_code}'
        
        result = self._request(path)
        return result.get('tasks', [{}])[0].get('result', [])
    
    def get_languages(self) -> List[Dict]:
        """Get available languages for SERP analysis"""
        result = self._request('/v3/serp/google/organic/languages')
        return result.get('tasks', [{}])[0].get('result', [])
    
    def post_serp_task(self, keyword: str, location_code: int = 2840, 
                      language_code: str = "en", device: str = "desktop") -> Dict:
        """Submit SERP analysis task"""
        post_data = [{
            'keyword': keyword,
            'location_code': location_code,
            'language_code': language_code,
            'device': device,
            'os': 'windows',
            'depth': 100,  # Number of results to retrieve
            'calculate_rectangles': True,
            'include_serp_info': True
        }]
        
        return self._request('/v3/serp/google/organic/task_post', 'POST', post_data)
    
    def get_serp_results(self, task_id: str) -> Dict:
        """Get SERP analysis results by task ID"""
        return self._request(f'/v3/serp/google/organic/task_get/advanced/{task_id}')
    
    def get_ready_serp_tasks(self) -> List[Dict]:
        """Get list of completed SERP tasks"""
        result = self._request('/v3/serp/google/organic/tasks_ready')
        return result.get('tasks', [{}])[0].get('result', [])
    
    def post_keywords_search_volume(self, keywords: List[str], 
                                   location_code: int = 2840,
                                   language_code: str = "en") -> Dict:
        """Submit keyword search volume analysis task"""
        post_data = [{
            'language_code': language_code,
            'location_code': location_code,
            'keywords': {i: keyword for i, keyword in enumerate(keywords)},
            'date_from': '2024-01-01'
        }]
        
        return self._request('/v3/keywords_data/google_ads/search_volume/task_post', 'POST', post_data)
    
    def get_keywords_search_volume_results(self, task_id: str) -> Dict:
        """Get keyword search volume results by task ID"""
        return self._request(f'/v3/keywords_data/google_ads/search_volume/task_get/{task_id}')
    
    def get_keywords_for_site(self, target_site: str, location_code: int = 2840,
                             language_code: str = "en") -> Dict:
        """Get keywords that a website ranks for"""
        post_data = [{
            'target': target_site,
            'location_code': location_code,
            'language_code': language_code,
            'limit': 1000
        }]
        
        return self._request('/v3/keywords_data/google_ads/keywords_for_site/task_post', 'POST', post_data)
    
    def get_competitors_domain(self, domain: str, location_code: int = 2840,
                              language_code: str = "en") -> Dict:
        """Get competitor domains for a given domain"""
        post_data = [{
            'target': domain,
            'location_code': location_code,
            'language_code': language_code,
            'limit': 100
        }]
        
        return self._request('/v3/dataforseo_labs/google/competitors_domain/task_post', 'POST', post_data)
    
    def analyze_content(self, content: str, keyword: str) -> Dict:
        """Analyze content for SEO optimization"""
        post_data = [{
            'text': content,
            'keyword': keyword,
            'language_code': 'en'
        }]
        
        return self._request('/v3/content_analysis/summary/task_post', 'POST', post_data)
    
    def get_serp_screenshot(self, keyword: str, location_code: int = 2840,
                           language_code: str = "en") -> Dict:
        """Get SERP screenshot for visual analysis"""
        post_data = [{
            'keyword': keyword,
            'location_code': location_code,
            'language_code': language_code,
            'device': 'desktop',
            'os': 'windows'
        }]
        
        return self._request('/v3/serp/google/organic/screenshot/task_post', 'POST', post_data)
    
    def standardize_response(self, raw_response: Dict, task_type: str) -> Dict:
        """Standardize DataForSEO response to RYVR format"""
        standardized = {
            'provider': 'DataForSEO',
            'task_type': task_type,
            'timestamp': datetime.utcnow().isoformat(),
            'status': 'success' if raw_response.get('status_code') == 20000 else 'error',
            'credits_used': raw_response.get('cost', 0),
            'data': {}
        }
        
        if raw_response.get('tasks'):
            task_data = raw_response['tasks'][0]
            standardized['task_id'] = task_data.get('id')
            standardized['data'] = task_data.get('result', {})
            
            # Add task-specific standardization
            if task_type == 'serp_analysis':
                standardized['data'] = self._standardize_serp_data(task_data.get('result', {}))
            elif task_type == 'keyword_volume':
                standardized['data'] = self._standardize_keyword_data(task_data.get('result', {}))
        
        return standardized
    
    def _standardize_serp_data(self, serp_data: Dict) -> Dict:
        """Standardize SERP data format"""
        if not serp_data:
            return {}
            
        return {
            'keyword': serp_data.get('keyword'),
            'location': serp_data.get('location_code'),
            'language': serp_data.get('language_code'),
            'total_results': serp_data.get('total_count', 0),
            'organic_results': [
                {
                    'position': item.get('rank_group', 0),
                    'title': item.get('title', ''),
                    'url': item.get('url', ''),
                    'description': item.get('description', ''),
                    'domain': item.get('domain', ''),
                    'breadcrumb': item.get('breadcrumb', '')
                }
                for item in serp_data.get('items', [])
                if item.get('type') == 'organic'
            ],
            'featured_snippets': [
                {
                    'type': item.get('type', ''),
                    'title': item.get('title', ''),
                    'description': item.get('description', ''),
                    'url': item.get('url', '')
                }
                for item in serp_data.get('items', [])
                if item.get('type') in ['featured_snippet', 'answer_box', 'knowledge_graph']
            ]
        }
    
    def _standardize_keyword_data(self, keyword_data: Dict) -> Dict:
        """Standardize keyword data format"""
        if not keyword_data:
            return {}
            
        return {
            'keywords': [
                {
                    'keyword': item.get('keyword', ''),
                    'search_volume': item.get('search_volume', 0),
                    'cpc': item.get('cpc', 0),
                    'competition': item.get('competition', 0),
                    'competition_level': item.get('competition_level', 'unknown'),
                    'trends': item.get('monthly_searches', [])
                }
                for item in keyword_data
            ] if isinstance(keyword_data, list) else []
        }

# Service instance
dataforseo_service = DataForSEOService() 