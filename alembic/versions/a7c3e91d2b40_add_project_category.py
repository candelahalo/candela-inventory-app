"""add project category (retail / residential)

Revision ID: a7c3e91d2b40
Revises: 95f0c25e35de
Create Date: 2026-10-08 18:20:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a7c3e91d2b40'
down_revision = '95f0c25e35de'
branch_labels = None
depends_on = None


def upgrade():
    # Nullable on purpose: existing projects stay unassigned until someone
    # sorts them into Retail or Residential from the Projects page.
    op.add_column('projects', sa.Column('category', sa.String(length=20), nullable=True))
    op.create_index('ix_projects_category', 'projects', ['category'])


def downgrade():
    op.drop_index('ix_projects_category', table_name='projects')
    op.drop_column('projects', 'category')
