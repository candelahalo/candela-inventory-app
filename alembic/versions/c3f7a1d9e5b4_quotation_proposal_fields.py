"""quotation proposal (by system): consultant, main contractor, scope notes per
section, inclusions, exclusions, payment milestones, unit prices shown or not

Revision ID: c3f7a1d9e5b4
Revises: b9e3d1f7a5c2
Create Date: 2026-10-21 13:00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c3f7a1d9e5b4'
down_revision = 'b9e3d1f7a5c2'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('quotations', sa.Column('consultant', sa.String(length=255), nullable=True))
    op.add_column('quotations', sa.Column('main_contractor', sa.String(length=255), nullable=True))
    op.add_column('quotations', sa.Column('section_notes', sa.JSON(), nullable=True))
    op.add_column('quotations', sa.Column('inclusions', sa.Text(), nullable=True))
    op.add_column('quotations', sa.Column('exclusions', sa.Text(), nullable=True))
    op.add_column('quotations', sa.Column('milestones', sa.Text(), nullable=True))
    op.add_column('quotations', sa.Column('proposal_prices', sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade():
    for c in ('proposal_prices', 'milestones', 'exclusions', 'inclusions', 'section_notes', 'main_contractor', 'consultant'):
        op.drop_column('quotations', c)
