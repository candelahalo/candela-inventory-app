"""add project division (lighting / automation)

Revision ID: c5e2a9d7f104
Revises: b3f1d6a8c2e7
Create Date: 2026-10-10 18:45:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c5e2a9d7f104'
down_revision = 'b3f1d6a8c2e7'
branch_labels = None
depends_on = None


def upgrade():
    # Nullable: existing projects show under "Not set" until someone picks
    # Lighting or Automation from Edit.
    op.add_column('projects', sa.Column('division', sa.String(length=20), nullable=True))
    op.create_index('ix_projects_division', 'projects', ['division'])


def downgrade():
    op.drop_index('ix_projects_division', table_name='projects')
    op.drop_column('projects', 'division')
