#!/usr/bin/env python3
"""
Test File Summary Fix
Quick test to verify the OpenAI summarization fix works
"""

import os
import sys
import asyncio

# Add the backend directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from services.openai_service import OpenAIService

async def test_openai_service():
    """Test the OpenAI service directly"""
    print("🧪 Testing OpenAI Service Integration...")
    
    # Test content
    test_content = """
    CURRICULUM VITAE M J KOEGELENBERG
    
    Name: Marthinus Johannes Koegelenberg (Hannes)
    
    EDUCATION:
    - Bachelor of Science in Computer Science
    - Master of Science in Software Engineering
    
    EXPERIENCE:
    - Software Developer at TechCorp (2018-2020)
    - Senior Software Engineer at InnovateTech (2020-2023)
    - Lead Developer at FutureCode (2023-Present)
    
    SKILLS:
    - Programming: Python, JavaScript, Java
    - Frameworks: React, Django, Spring Boot
    - Databases: PostgreSQL, MongoDB, Redis
    - Cloud: AWS, Azure, Google Cloud
    """
    
    try:
        # Create OpenAI service instance
        service = OpenAIService()
        
        # Check if API key is configured
        if not service.client:
            print("❌ OpenAI API key not configured!")
            print("   Please set OPENAI_API_KEY environment variable")
            return False
        
        print("✅ OpenAI client initialized successfully")
        print(f"   Using model: {service.default_model}")
        
        # Test the generate_completion method
        print("🔄 Testing completion generation...")
        
        system_prompt = """You are an expert at creating concise, informative summaries of documents. 
        Create a summary that captures the key points, main topics, and essential information from the document.
        Keep the summary under 200 words but ensure it's comprehensive enough to understand the document's purpose and content."""
        
        result = await service.generate_completion(
            prompt=f"Please summarize the following document:\n\n{test_content}",
            system_prompt=system_prompt,
            temperature=0.3,
            max_completion_tokens=300
        )
        
        print(f"📄 Response received:")
        print(f"   Success: {result.get('success')}")
        
        if result.get('success'):
            print(f"   Content length: {len(result.get('content', ''))}")
            print(f"   Tokens used: {result.get('usage', {}).get('total_tokens', 0)}")
            print(f"   Summary preview: {result.get('content', '')[:100]}...")
            return True
        else:
            print(f"   Error: {result.get('error')}")
            return False
            
    except Exception as e:
        print(f"❌ Error testing OpenAI service: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_file_service_summary():
    """Test the file service summary method with the fix"""
    print("\n🧪 Testing File Service Summary Generation...")
    
    try:
        from sqlalchemy.orm import sessionmaker
        from database import engine
        from services.file_service import FileService
        
        # Create test session
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        db = SessionLocal()
        
        file_service = FileService(db)
        
        test_content = """
        CURRICULUM VITAE M J KOEGELENBERG
        
        This is a professional resume for Marthinus Johannes Koegelenberg, 
        showing his education in Computer Science and Software Engineering,
        along with progressive work experience from Software Developer to Lead Developer
        at various technology companies. The resume highlights skills in multiple
        programming languages, frameworks, databases, and cloud platforms.
        """
        
        print("🔄 Generating summary via FileService...")
        
        result = await file_service.generate_file_summary(
            test_content, 
            business_id=None,  # Account-level test
            account_id=1, 
            account_type="user"
        )
        
        print(f"📄 Summary result:")
        print(f"   Summary length: {len(result.get('summary', ''))}")
        print(f"   Credits used: {result.get('credits_used', 0)}")
        print(f"   Summary: {result.get('summary', '')[:200]}...")
        
        # Check if we got a real summary (not the fallback)
        if "Auto-generated summary unavailable" in result.get('summary', ''):
            print("❌ Still getting fallback summary")
            return False
        else:
            print("✅ Real AI summary generated successfully!")
            return True
            
    except Exception as e:
        print(f"❌ Error testing file service: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🚀 Starting OpenAI Summary Fix Test...")
    
    # Check for API key
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("⚠️  OPENAI_API_KEY environment variable not set")
        print("   This test will show the configuration issue")
    else:
        print(f"✅ Found OPENAI_API_KEY: {api_key[:10]}...{api_key[-4:]}")
    
    async def run_tests():
        # Test OpenAI service directly
        openai_success = await test_openai_service()
        
        # Test file service if OpenAI works
        if openai_success:
            file_service_success = await test_file_service_summary()
            
            if file_service_success:
                print("\n🎉 All tests passed! Summary generation should work now.")
            else:
                print("\n❌ File service test failed. Check the logs for details.")
        else:
            print("\n❌ OpenAI service test failed. Check API key configuration.")
    
    # Run the async tests
    asyncio.run(run_tests())
