"""product series, size and options (e.g. CHERUB S / M / L / XL with watt,
beam, CCT, dimming and colour picked on the quote line)

Revision ID: b5d1f7a3c9e2
Revises: d6f8b2c4e0a7
Create Date: 2026-10-17 11:00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b5d1f7a3c9e2'
down_revision = 'd6f8b2c4e0a7'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('products', sa.Column('series', sa.String(length=120), nullable=True))
    op.add_column('products', sa.Column('variant', sa.String(length=40), nullable=True))
    op.add_column('products', sa.Column('options', sa.JSON(), nullable=True))
    op.create_index('ix_products_series', 'products', ['series'])
    op.add_column('quotation_items', sa.Column('options', sa.JSON(), nullable=True))


def downgrade():
    op.drop_column('quotation_items', 'options')
    op.drop_index('ix_products_series', 'products')
    op.drop_column('products', 'options')
    op.drop_column('products', 'variant')
    op.drop_column('products', 'series')
