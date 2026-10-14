"""product cost in AED, USD or EUR, and exchange rates

Revision ID: a3c9e5f2b7d4
Revises: d7e2b9f4c1a6
Create Date: 2026-10-14 18:00:00

"""
from datetime import datetime

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a3c9e5f2b7d4'
down_revision = 'd7e2b9f4c1a6'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('products', sa.Column('cost_currency', sa.String(length=3), nullable=True, server_default='AED'))
    op.add_column('products', sa.Column('cost_amount', sa.Float(), nullable=True))
    # Existing costs are in AED
    op.execute("UPDATE products SET cost_currency = 'AED', cost_amount = cost_price")

    rates = op.create_table(
        'exchange_rates',
        sa.Column('currency', sa.String(length=3), primary_key=True),
        sa.Column('rate', sa.Float(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('updated_by', sa.String(length=64), nullable=True),
    )
    # The dirham is pegged to the dollar; EUR is left for the user to set
    op.bulk_insert(rates, [{'currency': 'USD', 'rate': 3.6725, 'updated_at': datetime.utcnow(), 'updated_by': 'system'}])


def downgrade():
    op.drop_table('exchange_rates')
    op.drop_column('products', 'cost_amount')
    op.drop_column('products', 'cost_currency')
