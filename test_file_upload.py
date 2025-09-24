#!/usr/bin/env python3
"""
File Upload Test Script
Simple test to verify file upload functionality works
"""

import os
import sys
import asyncio
import tempfile
from io import BytesIO

# Add the backend directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.orm import Session
from database import SessionLocal
from services.file_service import FileService

async def test_file_upload():
    """Test basic file upload functionality"""
    
    # Create a test session
    db = SessionLocal()
    file_service = FileService(db)
    
    try:
        # Create a test text file
        test_content = """
        This is a test document for the RYVR file management system.
        
        It contains some sample content that should be extracted and summarized.
        
        Features being tested:
        1. File upload
        2. Content extraction  
        3. AI summarization
        4. Storage management
        
        The system should be able to handle various file types including:
        - Plain text files (.txt)
        - PDF documents (.pdf)
        - Word documents (.docx)
        - Markdown files (.md)
        
        This content is long enough to trigger the AI summarization feature,
        which should create a concise summary of the key points.
        """
        
        # Create a BytesIO object with the test content
        file_data = BytesIO(test_content.encode('utf-8'))
        
        print("🧪 Testing file upload...")
        
        # Test upload
        uploaded_file = await file_service.upload_file(
            file_data=file_data,
            original_filename="test_document.txt",
            account_id=1,  # Test account
            account_type="user",
            uploaded_by=1,  # Test user
            business_id=None,  # Account-level file
            auto_process=True
        )
        
        print(f"✅ File uploaded successfully!")
        print(f"   File ID: {uploaded_file.id}")
        print(f"   Original name: {uploaded_file.original_name}")
        print(f"   File size: {uploaded_file.file_size} bytes")
        print(f"   Processing status: {uploaded_file.processing_status}")
        
        # Wait for processing to complete (in real app this would be async)
        if uploaded_file.processing_status == 'pending':
            print("⏳ Processing file content...")
            # In a real implementation, this would be handled by background tasks
            await file_service._process_file_content(uploaded_file)
            print(f"✅ Processing complete!")
        
        # Check results
        db.refresh(uploaded_file)
        print(f"\n📄 File Content Summary:")
        print(f"   Content length: {len(uploaded_file.content_text or '')} characters")
        print(f"   Summary: {uploaded_file.summary[:100] if uploaded_file.summary else 'None'}...")
        print(f"   Credits used for summary: {uploaded_file.summary_credits_used}")
        
        # Test storage usage
        usage = await file_service.get_storage_usage(1, "user")
        print(f"\n💾 Storage Usage:")
        print(f"   Total bytes: {usage['total_bytes']}")
        print(f"   File count: {usage['file_count']}")
        print(f"   Account files: {usage['account_files_bytes']} bytes")
        
        # Test file search
        files = await file_service.search_files(
            account_id=1,
            account_type="user", 
            user_id=1,
            search_query="test",
            limit=10
        )
        print(f"\n🔍 Search Results:")
        print(f"   Found {len(files)} files matching 'test'")
        
        print("\n🎉 All tests passed!")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

async def test_pdf_extraction():
    """Test PDF content extraction (requires a sample PDF)"""
    
    # This would test PDF extraction if you have a sample PDF file
    # For now, just demonstrate the capability
    
    print("\n📑 PDF Extraction Test:")
    print("   To test PDF extraction, place a sample PDF in the test directory")
    print("   and uncomment the PDF test code in this function.")
    
    # Uncomment and modify this section to test with an actual PDF:
    # 
    # db = SessionLocal()
    # file_service = FileService(db)
    # 
    # with open("sample.pdf", "rb") as pdf_file:
    #     uploaded_pdf = await file_service.upload_file(
    #         file_data=pdf_file,
    #         original_filename="sample.pdf",
    #         account_id=1,
    #         account_type="user",
    #         uploaded_by=1
    #     )
    #     print(f"✅ PDF uploaded: {uploaded_pdf.original_name}")

if __name__ == "__main__":
    print("🚀 Starting File Management Tests...")
    
    # Run the async test
    asyncio.run(test_file_upload())
    asyncio.run(test_pdf_extraction())
    
    print("✨ Tests complete!")
