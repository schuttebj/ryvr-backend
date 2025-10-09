"""
Add dynamic integration fields to Integration table

Revision ID: add_dynamic_integration_fields
Created: 2025-01-09
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = 'add_dynamic_integration_fields'
down_revision = None  # Set this to the previous migration ID
branch_labels = None
depends_on = None


def upgrade():
    # Add new columns to integrations table
    op.add_column('integrations', sa.Column('is_dynamic', sa.Boolean(), default=False, nullable=False, server_default='false'))
    op.add_column('integrations', sa.Column('platform_config', postgresql.JSON(astext_type=sa.Text()), nullable=True))
    op.add_column('integrations', sa.Column('auth_config', postgresql.JSON(astext_type=sa.Text()), nullable=True))
    op.add_column('integrations', sa.Column('oauth_config', postgresql.JSON(astext_type=sa.Text()), nullable=True))


def downgrade():
    # Remove columns
    op.drop_column('integrations', 'oauth_config')
    op.drop_column('integrations', 'auth_config')
    op.drop_column('integrations', 'platform_config')
    op.drop_column('integrations', 'is_dynamic')

