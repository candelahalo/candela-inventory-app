"""product datasheet choice: HALO (made automatically, the default), supplier
PDF, or not needed; plus the description / features texts for the HALO sheet

Revision ID: b9d3f5a7c2e4
Revises: a8c2e4f6b1d3
Create Date: 2026-10-16 15:30:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b9d3f5a7c2e4'
down_revision = 'a8c2e4f6b1d3'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('products', sa.Column('datasheet_mode', sa.String(length=16), nullable=False, server_default='halo'))
    op.add_column('products', sa.Column('description', sa.Text(), nullable=True))
    op.add_column('products', sa.Column('features', sa.Text(), nullable=True))
    # Products with an uploaded PDF keep using it; ticked "not needed" stays so
    op.execute("UPDATE products SET datasheet_mode = 'supplier' "
               "WHERE id IN (SELECT DISTINCT product_id FROM datasheets WHERE product_id IS NOT NULL)")
    op.execute("UPDATE products SET datasheet_mode = 'none' WHERE no_datasheet = true")


def downgrade():
    op.drop_column('products', 'features')
    op.drop_column('products', 'description')
    op.drop_column('products', 'datasheet_mode')
