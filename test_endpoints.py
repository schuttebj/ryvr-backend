#!/usr/bin/env python3
"""
Test script to verify all core API endpoints are working
"""

import requests
import json
from typing import Dict, Any

# Backend URL
BASE_URL = "https://ryvr-backend.onrender.com"

def test_endpoint(method: str, endpoint: str, headers: Dict[str, str] = None, data: Dict[str, Any] = None) -> Dict[str, Any]:
    """Test a single endpoint and return the result"""
    url = f"{BASE_URL}{endpoint}"
    
    try:
        if method.upper() == "GET":
            response = requests.get(url, headers=headers)
        elif method.upper() == "POST":
            response = requests.post(url, headers=headers, json=data)
        else:
            return {"error": f"Unsupported method: {method}"}
        
        return {
            "endpoint": endpoint,
            "method": method,
            "status_code": response.status_code,
            "success": response.status_code < 400,
            "response": response.json() if response.headers.get('content-type', '').startswith('application/json') else response.text[:200]
        }
    except Exception as e:
        return {
            "endpoint": endpoint,
            "method": method,
            "error": str(e),
            "success": False
        }

def main():
    """Test all core endpoints"""
    print("🔍 Testing RYVR Backend Endpoints")
    print("=" * 50)
    
    # Test basic endpoints
    endpoints_to_test = [
        ("GET", "/"),
        ("GET", "/health"),
        ("POST", "/api/v1/auth/login", {"username": "admin", "password": "admin123"}),
        ("GET", "/api/v1/files"),
        ("GET", "/api/v1/businesses"),
        ("GET", "/api/v1/embeddings/files/1"),
        ("GET", "/api/simple/integrations"),
    ]
    
    results = []
    
    for method, endpoint, *data in endpoints_to_test:
        test_data = data[0] if data else None
        result = test_endpoint(method, endpoint, data=test_data)
        results.append(result)
        
        status = "✅" if result.get("success") else "❌"
        print(f"{status} {method} {endpoint} - Status: {result.get('status_code', 'ERROR')}")
        
        if not result.get("success"):
            print(f"   Error: {result.get('error', result.get('response', 'Unknown error'))}")
    
    print("\n" + "=" * 50)
    print("📊 Summary:")
    successful = sum(1 for r in results if r.get("success"))
    total = len(results)
    print(f"✅ Successful: {successful}/{total}")
    print(f"❌ Failed: {total - successful}/{total}")
    
    if successful < total:
        print("\n🔧 Failed endpoints need investigation:")
        for result in results:
            if not result.get("success"):
                print(f"   - {result['method']} {result['endpoint']}")

if __name__ == "__main__":
    main()
