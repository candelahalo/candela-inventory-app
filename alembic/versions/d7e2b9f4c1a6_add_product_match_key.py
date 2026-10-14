"""add product match key (recognises items imported from PDF quotations)

Revision ID: d7e2b9f4c1a6
Revises: f6a3d8b2c5e1
Create Date: 2026-10-14 15:30:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd7e2b9f4c1a6'
down_revision = 'f6a3d8b2c5e1'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('products', sa.Column('match_key', sa.String(length=500), nullable=True))
    op.create_index('ix_products_match_key', 'products', ['match_key'])


def downgrade():
    op.drop_index('ix_products_match_key', table_name='products')
    op.drop_column('products', 'match_key')
