"""quotation room matrix: rooms per floor x products, quantities fill the lines

Revision ID: d4a8e2c6f0b3
Revises: c3f7a1d9e5b4
Create Date: 2026-10-21 15:00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd4a8e2c6f0b3'
down_revision = 'c3f7a1d9e5b4'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('quotations', sa.Column('room_matrix', sa.JSON(), nullable=True))


def downgrade():
    with op.batch_alter_table('quotations') as b:
        b.drop_column('room_matrix')
