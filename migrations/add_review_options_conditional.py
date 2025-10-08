"""
Database migration script for Review, Options, and Conditional nodes implementation

This migration adds support for:
1. New flow status 'input_required'
2. Enhanced WorkflowStepExecution with review and rerun fields
3. New FlowOptionsSelection table
4. Enhanced FlowReviewApproval with edit tracking

Run this migration BEFORE deploying the new code
"""

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
import os
import sys

# Add parent directory to path to import models
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def run_migration():
    """Execute the migration"""
    
    # Get database URL from environment
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        print("❌ Error: DATABASE_URL environment variable not set")
        return False
    
    # Handle Render postgres:// URLs
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    
    print("🔄 Starting migration...")
    print(f"📊 Database: {database_url.split('@')[-1]}")  # Print without credentials
    
    engine = create_engine(database_url)
    
    try:
        with engine.begin() as conn:
            print("\n" + "="*80)
            print("STEP 1: Update WorkflowExecution flow_status constraint")
            print("="*80)
            
            # Drop old constraint
            conn.execute(text("""
                ALTER TABLE workflow_executions 
                DROP CONSTRAINT IF EXISTS check_flow_status;
            """))
            print("✅ Dropped old flow_status constraint")
            
            # Add new constraint with 'input_required'
            conn.execute(text("""
                ALTER TABLE workflow_executions 
                ADD CONSTRAINT check_flow_status 
                CHECK (flow_status IN ('new', 'scheduled', 'in_progress', 'in_review', 'input_required', 'complete', 'error'));
            """))
            print("✅ Added new flow_status constraint with 'input_required'")
            
            print("\n" + "="*80)
            print("STEP 2: Add new columns to workflow_step_executions")
            print("="*80)
            
            # Add editable_fields column
            conn.execute(text("""
                ALTER TABLE workflow_step_executions 
                ADD COLUMN IF NOT EXISTS editable_fields JSON DEFAULT '[]';
            """))
            print("✅ Added editable_fields column")
            
            # Add rerun_count column
            conn.execute(text("""
                ALTER TABLE workflow_step_executions 
                ADD COLUMN IF NOT EXISTS rerun_count INTEGER DEFAULT 0;
            """))
            print("✅ Added rerun_count column")
            
            # Add parent_execution_id column
            conn.execute(text("""
                ALTER TABLE workflow_step_executions 
                ADD COLUMN IF NOT EXISTS parent_execution_id INTEGER REFERENCES workflow_step_executions(id);
            """))
            print("✅ Added parent_execution_id column")
            
            # Add modified_input_data column
            conn.execute(text("""
                ALTER TABLE workflow_step_executions 
                ADD COLUMN IF NOT EXISTS modified_input_data JSON;
            """))
            print("✅ Added modified_input_data column")
            
            # Update step_type constraint to include new types
            conn.execute(text("""
                ALTER TABLE workflow_step_executions 
                DROP CONSTRAINT IF EXISTS check_step_type;
            """))
            conn.execute(text("""
                ALTER TABLE workflow_step_executions 
                ADD CONSTRAINT check_step_type 
                CHECK (step_type IN ('task', 'ai', 'transform', 'foreach', 'gate', 'condition', 'async_task', 'review', 'options', 'conditional'));
            """))
            print("✅ Updated step_type constraint with new node types")
            
            print("\n" + "="*80)
            print("STEP 3: Create flow_options_selections table")
            print("="*80)
            
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS flow_options_selections (
                    id SERIAL PRIMARY KEY,
                    execution_id INTEGER NOT NULL REFERENCES workflow_executions(id),
                    step_id VARCHAR(100) NOT NULL,
                    available_options JSON NOT NULL,
                    selected_options JSON NOT NULL,
                    selection_mode VARCHAR(20) NOT NULL,
                    selected_by INTEGER REFERENCES users(id),
                    selected_at TIMESTAMP WITH TIME ZONE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT check_selection_mode CHECK (selection_mode IN ('single', 'multiple'))
                );
            """))
            print("✅ Created flow_options_selections table")
            
            # Add index for faster lookups
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_flow_options_selections_execution 
                ON flow_options_selections(execution_id, step_id);
            """))
            print("✅ Created index on flow_options_selections")
            
            print("\n" + "="*80)
            print("STEP 4: Add new columns to flow_review_approvals")
            print("="*80)
            
            # Add edited_steps column
            conn.execute(text("""
                ALTER TABLE flow_review_approvals 
                ADD COLUMN IF NOT EXISTS edited_steps JSON DEFAULT '[]';
            """))
            print("✅ Added edited_steps column")
            
            # Add edited_data column
            conn.execute(text("""
                ALTER TABLE flow_review_approvals 
                ADD COLUMN IF NOT EXISTS edited_data JSON DEFAULT '{}';
            """))
            print("✅ Added edited_data column")
            
            # Add rerun_steps column
            conn.execute(text("""
                ALTER TABLE flow_review_approvals 
                ADD COLUMN IF NOT EXISTS rerun_steps JSON DEFAULT '[]';
            """))
            print("✅ Added rerun_steps column")
            
            print("\n" + "="*80)
            print("STEP 5: Verify migration")
            print("="*80)
            
            # Verify tables exist
            result = conn.execute(text("""
                SELECT table_name FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name IN ('flow_options_selections');
            """))
            tables = [row[0] for row in result]
            
            if 'flow_options_selections' in tables:
                print("✅ flow_options_selections table exists")
            else:
                print("❌ flow_options_selections table NOT FOUND")
                return False
            
            # Verify columns exist
            result = conn.execute(text("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name = 'workflow_step_executions' 
                AND column_name IN ('editable_fields', 'rerun_count', 'parent_execution_id', 'modified_input_data');
            """))
            columns = [row[0] for row in result]
            
            expected_columns = ['editable_fields', 'rerun_count', 'parent_execution_id', 'modified_input_data']
            for col in expected_columns:
                if col in columns:
                    print(f"✅ workflow_step_executions.{col} column exists")
                else:
                    print(f"❌ workflow_step_executions.{col} column NOT FOUND")
                    return False
            
            print("\n" + "="*80)
            print("✅ MIGRATION COMPLETED SUCCESSFULLY")
            print("="*80)
            print("\nSummary:")
            print("- Updated WorkflowExecution flow_status constraint")
            print("- Added 4 new columns to workflow_step_executions")
            print("- Created flow_options_selections table")
            print("- Added 3 new columns to flow_review_approvals")
            print("\nYou can now deploy the new code with Review, Options, and Conditional nodes support.")
            
            return True
            
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        print("\nPlease check the error and try again.")
        return False


def rollback_migration():
    """Rollback the migration (for testing purposes)"""
    
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        print("❌ Error: DATABASE_URL environment variable not set")
        return False
    
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    
    print("🔄 Rolling back migration...")
    
    engine = create_engine(database_url)
    
    try:
        with engine.begin() as conn:
            # Drop flow_options_selections table
            conn.execute(text("DROP TABLE IF EXISTS flow_options_selections CASCADE;"))
            print("✅ Dropped flow_options_selections table")
            
            # Remove columns from workflow_step_executions
            conn.execute(text("ALTER TABLE workflow_step_executions DROP COLUMN IF EXISTS editable_fields;"))
            conn.execute(text("ALTER TABLE workflow_step_executions DROP COLUMN IF EXISTS rerun_count;"))
            conn.execute(text("ALTER TABLE workflow_step_executions DROP COLUMN IF EXISTS parent_execution_id;"))
            conn.execute(text("ALTER TABLE workflow_step_executions DROP COLUMN IF EXISTS modified_input_data;"))
            print("✅ Removed columns from workflow_step_executions")
            
            # Remove columns from flow_review_approvals
            conn.execute(text("ALTER TABLE flow_review_approvals DROP COLUMN IF EXISTS edited_steps;"))
            conn.execute(text("ALTER TABLE flow_review_approvals DROP COLUMN IF EXISTS edited_data;"))
            conn.execute(text("ALTER TABLE flow_review_approvals DROP COLUMN IF EXISTS rerun_steps;"))
            print("✅ Removed columns from flow_review_approvals")
            
            # Restore old flow_status constraint
            conn.execute(text("ALTER TABLE workflow_executions DROP CONSTRAINT IF EXISTS check_flow_status;"))
            conn.execute(text("""
                ALTER TABLE workflow_executions 
                ADD CONSTRAINT check_flow_status 
                CHECK (flow_status IN ('new', 'scheduled', 'in_progress', 'in_review', 'complete', 'error'));
            """))
            print("✅ Restored old flow_status constraint")
            
            # Restore old step_type constraint
            conn.execute(text("ALTER TABLE workflow_step_executions DROP CONSTRAINT IF EXISTS check_step_type;"))
            conn.execute(text("""
                ALTER TABLE workflow_step_executions 
                ADD CONSTRAINT check_step_type 
                CHECK (step_type IN ('task', 'ai', 'transform', 'foreach', 'gate', 'condition', 'async_task', 'review'));
            """))
            print("✅ Restored old step_type constraint")
            
            print("\n✅ ROLLBACK COMPLETED")
            return True
            
    except Exception as e:
        print(f"\n❌ Rollback failed: {e}")
        return False


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Migrate database for Review, Options, and Conditional nodes')
    parser.add_argument('--rollback', action='store_true', help='Rollback the migration')
    args = parser.parse_args()
    
    if args.rollback:
        success = rollback_migration()
    else:
        success = run_migration()
    
    sys.exit(0 if success else 1)

