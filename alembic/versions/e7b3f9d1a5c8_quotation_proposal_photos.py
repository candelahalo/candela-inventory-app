"""quotation proposal photos: chosen / replaced photos and their size

Revision ID: e7b3f9d1a5c8
Revises: d4a8e2c6f0b3
Create Date: 2026-10-21 16:00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e7b3f9d1a5c8'
down_revision = 'd4a8e2c6f0b3'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('quotations', sa.Column('proposal_photos', sa.JSON(), nullable=True))
    op.add_column('quotations', sa.Column('proposal_photo_size', sa.String(length=4), nullable=False, server_default='M'))


def downgrade():
    with op.batch_alter_table('quotations') as b:
        b.drop_column('proposal_photo_size')
        b.drop_column('proposal_photos')
