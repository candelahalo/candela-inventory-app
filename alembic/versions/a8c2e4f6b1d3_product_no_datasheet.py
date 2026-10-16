"""product "no datasheet needed" (e.g. accessories), so the submittal doesn't
ask for one

Revision ID: a8c2e4f6b1d3
Revises: f3b8d6a2c4e7
Create Date: 2026-10-16 13:40:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a8c2e4f6b1d3'
down_revision = 'f3b8d6a2c4e7'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('products', sa.Column('no_datasheet', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    op.drop_column('products', 'no_datasheet')
