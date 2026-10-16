"""quotation line runs (e.g. a 34 m linear light made of 9 m + 10 m + 15 m)

Revision ID: e1a7c3f5b9d2
Revises: d9f2b4c6e8a1
Create Date: 2026-10-16 10:40:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e1a7c3f5b9d2'
down_revision = 'd9f2b4c6e8a1'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('quotation_items', sa.Column('runs', sa.String(length=255), nullable=True))


def downgrade():
    op.drop_column('quotation_items', 'runs')
