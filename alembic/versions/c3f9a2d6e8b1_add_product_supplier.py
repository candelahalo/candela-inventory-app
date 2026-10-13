"""add product usual supplier

Revision ID: c3f9a2d6e8b1
Revises: b5c8e1f4a7d2
Create Date: 2026-10-13 19:05:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c3f9a2d6e8b1'
down_revision = 'b5c8e1f4a7d2'
branch_labels = None
depends_on = None


def upgrade():
    # One empty column; nothing existing changes.
    op.add_column('products', sa.Column('supplier', sa.String(length=255), nullable=True))


def downgrade():
    op.drop_column('products', 'supplier')
