"""quotation sections: a heading over a group of lines (FRONT END MATERIALS,
INTERCOM ...), optionally with a subtotal per section

Revision ID: f2b6d8a4c0e3
Revises: e5a9c3d7f1b2
Create Date: 2026-10-21 11:30:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f2b6d8a4c0e3'
down_revision = 'e5a9c3d7f1b2'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('quotation_items', sa.Column('section', sa.String(length=120), nullable=True))
    op.add_column('quotations', sa.Column('section_subtotals', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    op.drop_column('quotations', 'section_subtotals')
    op.drop_column('quotation_items', 'section')
