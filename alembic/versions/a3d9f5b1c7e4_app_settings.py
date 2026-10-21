"""app settings (key / value): standard automation proposal terms

Revision ID: a3d9f5b1c7e4
Revises: e7b3f9d1a5c8
Create Date: 2026-10-21 18:00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a3d9f5b1c7e4'
down_revision = 'e7b3f9d1a5c8'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'app_settings',
        sa.Column('key', sa.String(length=64), primary_key=True),
        sa.Column('value', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )


def downgrade():
    op.drop_table('app_settings')
