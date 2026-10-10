"""add customer category (retail / residential)

Revision ID: d8a4f1c6e9b3
Revises: c5e2a9d7f104
Create Date: 2026-10-10 19:20:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd8a4f1c6e9b3'
down_revision = 'c5e2a9d7f104'
branch_labels = None
depends_on = None


def upgrade():
    # Nullable: existing customers show under "Not set" until someone picks
    # Retail or Residential from Edit.
    op.add_column('customers', sa.Column('category', sa.String(length=20), nullable=True))
    op.create_index('ix_customers_category', 'customers', ['category'])


def downgrade():
    op.drop_index('ix_customers_category', table_name='customers')
    op.drop_column('customers', 'category')
