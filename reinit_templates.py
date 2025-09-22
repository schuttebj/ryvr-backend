#!/usr/bin/env python3
"""
Quick script to reinitialize workflow templates with V2 schema
Run this after backend changes to update predefined templates
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from init_db import create_sample_workflow_templates
from database import SessionLocal
from models import WorkflowTemplate

def reinitialize_templates():
    """Delete old templates and create new V2 templates"""
    try:
        print("🔄 Reinitializing workflow templates...")
        
        # Delete existing templates
        db = SessionLocal()
        existing_count = db.query(WorkflowTemplate).count()
        if existing_count > 0:
            print(f"🗑️  Deleting {existing_count} existing templates...")
            db.query(WorkflowTemplate).delete()
            db.commit()
        
        db.close()
        
        # Create new V2 templates
        success = create_sample_workflow_templates()
        
        if success:
            print("✅ Successfully reinitialized workflow templates with V2 schema!")
            print("\nAvailable templates:")
            print("📊 Basic SEO Analysis (ryvr.workflow.v1)")
            print("✍️  AI Content Creation (ryvr.workflow.v1)")
            print("🔍 Competitor Analysis Suite (ryvr.workflow.v1)")
            return True
        else:
            print("❌ Failed to create new templates")
            return False
            
    except Exception as e:
        print(f"❌ Error reinitializing templates: {e}")
        return False

if __name__ == "__main__":
    success = reinitialize_templates()
    sys.exit(0 if success else 1)
