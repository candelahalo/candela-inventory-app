"""datasheet kind: "supplier" (the brand's PDF) or "halo" (a HALO sheet made
outside the app and uploaded - used instead of the automatic one)

Revision ID: d6f8b2c4e0a7
Revises: c4e6a8b0d2f5
Create Date: 2026-10-16 17:50:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd6f8b2c4e0a7'
down_revision = 'c4e6a8b0d2f5'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('datasheets', sa.Column('kind', sa.String(length=16), nullable=False, server_default='supplier'))


def downgrade():
    op.drop_column('datasheets', 'kind')
