"""quotation lines without a product (custom lines), with their own unit and photo

Revision ID: f6a3d8b2c5e1
Revises: e2b7c4d9a1f5
Create Date: 2026-10-10 23:00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f6a3d8b2c5e1'
down_revision = 'e2b7c4d9a1f5'
branch_labels = None
depends_on = None


def upgrade():
    # Adds two empty columns and lets product be left empty. Existing lines
    # are unchanged.
    with op.batch_alter_table('quotation_items') as batch:
        batch.alter_column('product_id', existing_type=sa.Integer(), nullable=True)
        batch.add_column(sa.Column('unit', sa.String(length=16), nullable=True))
        batch.add_column(sa.Column('image_path', sa.String(length=255), nullable=True))


def downgrade():
    with op.batch_alter_table('quotation_items') as batch:
        batch.drop_column('image_path')
        batch.drop_column('unit')
        batch.alter_column('product_id', existing_type=sa.Integer(), nullable=False)
