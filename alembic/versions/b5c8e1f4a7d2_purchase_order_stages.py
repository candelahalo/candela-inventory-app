"""supplier order stages: payment, readiness, shipment, customs, delivery to client

Revision ID: b5c8e1f4a7d2
Revises: a9d4e7f2b8c3
Create Date: 2026-10-13 19:30:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b5c8e1f4a7d2'
down_revision = 'a9d4e7f2b8c3'
branch_labels = None
depends_on = None

COLUMNS = [
    ('payment_terms', sa.String(length=255)), ('advance_paid_date', sa.DateTime()), ('balance_paid_date', sa.DateTime()),
    ('ready_expected', sa.DateTime()), ('ready_date', sa.DateTime()),
    ('ship_mode', sa.String(length=20)), ('incoterm', sa.String(length=10)), ('forwarder', sa.String(length=255)),
    ('tracking_no', sa.String(length=120)), ('dispatch_date', sa.DateTime()), ('arrived_date', sa.DateTime()),
    ('customs_agent', sa.String(length=255)), ('customs_ref', sa.String(length=120)), ('cleared_date', sa.DateTime()),
    ('delivery_planned', sa.DateTime()), ('delivered_date', sa.DateTime()),
    ('delivery_note', sa.String(length=120)), ('delivered_to', sa.String(length=255)),
]


def upgrade():
    # Only adds empty columns; existing orders are unchanged.
    for name, type_ in COLUMNS:
        op.add_column('purchase_orders', sa.Column(name, type_, nullable=True))
    op.add_column('purchase_orders', sa.Column('quotation_id', sa.Integer(), nullable=True))
    op.create_index('ix_purchase_orders_quotation_id', 'purchase_orders', ['quotation_id'])
    op.add_column('purchase_order_items', sa.Column('delivered_qty', sa.Integer(), nullable=True))


def downgrade():
    op.drop_column('purchase_order_items', 'delivered_qty')
    op.drop_index('ix_purchase_orders_quotation_id', table_name='purchase_orders')
    op.drop_column('purchase_orders', 'quotation_id')
    for name, _ in reversed(COLUMNS):
        op.drop_column('purchase_orders', name)
