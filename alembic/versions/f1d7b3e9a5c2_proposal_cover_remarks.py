"""quotation proposal: cover photo, general remarks per system, datasheet pages on/off

Revision ID: f1d7b3e9a5c2
Revises: e5c1a7d3f9b2
Create Date: 2026-10-23 19:00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f1d7b3e9a5c2'
down_revision = 'e5c1a7d3f9b2'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('quotations', sa.Column('proposal_cover', sa.String(length=500), nullable=True))
    op.add_column('quotations', sa.Column('proposal_remarks', sa.JSON(), nullable=True))
    op.add_column('quotations', sa.Column('proposal_datasheets', sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade():
    with op.batch_alter_table('quotations') as b:
        b.drop_column('proposal_datasheets')
        b.drop_column('proposal_remarks')
        b.drop_column('proposal_cover')
