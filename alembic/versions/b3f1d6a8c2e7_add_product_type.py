"""add product type (Spotlight, Downlight, ...)

Revision ID: b3f1d6a8c2e7
Revises: a7c3e91d2b40
Create Date: 2026-10-10 18:05:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b3f1d6a8c2e7'
down_revision = 'a7c3e91d2b40'
branch_labels = None
depends_on = None

# Types for the original catalogue items. Home automation and the outdoor
# wall light don't fit any type yet, so they stay unset.
INITIAL_TYPES = {
    "CND-DL-100": "Downlight",
    "CND-DL-101": "Downlight",
    "CND-TR-210": "Track Light",
    "CND-PD-330": "Pendant",
    "CND-STR-050": "Strip Light",
}


def upgrade():
    op.add_column('products', sa.Column('product_type', sa.String(length=40), nullable=True))
    op.create_index('ix_products_product_type', 'products', ['product_type'])
    products = sa.table('products', sa.column('sku', sa.String), sa.column('product_type', sa.String))
    for sku, ptype in INITIAL_TYPES.items():
        op.execute(products.update().where(products.c.sku == sku).values(product_type=ptype))


def downgrade():
    op.drop_index('ix_products_product_type', table_name='products')
    op.drop_column('products', 'product_type')
