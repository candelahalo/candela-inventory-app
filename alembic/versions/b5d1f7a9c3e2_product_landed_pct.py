"""product landed-cost % (freight, duty, clearing on top of the supplier price)

Revision ID: b5d1f7a9c3e2
Revises: a3c9e5f2b7d4
Create Date: 2026-10-14 16:40:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b5d1f7a9c3e2'
down_revision = 'a3c9e5f2b7d4'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('products', sa.Column('landed_pct', sa.Float(), nullable=True, server_default='0'))
    op.execute("UPDATE products SET landed_pct = 0 WHERE landed_pct IS NULL")


def downgrade():
    op.drop_column('products', 'landed_pct')
