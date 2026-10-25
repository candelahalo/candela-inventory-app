"""quotation proposal: layout (portrait document / landscape slides) and the hero photos

Revision ID: a6c2e8f4b0d3
Revises: f1d7b3e9a5c2
Create Date: 2026-10-25 20:40:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a6c2e8f4b0d3'
down_revision = 'f1d7b3e9a5c2'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('quotations', sa.Column('proposal_layout', sa.String(length=12), nullable=False, server_default='portrait'))
    op.add_column('quotations', sa.Column('proposal_hero', sa.JSON(), nullable=True))


def downgrade():
    with op.batch_alter_table('quotations') as b:
        b.drop_column('proposal_hero')
        b.drop_column('proposal_layout')
