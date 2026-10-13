"""add supplier orders (purchase orders)

Revision ID: a9d4e7f2b8c3
Revises: e2b7c4d9a1f5
Create Date: 2026-10-13 18:00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a9d4e7f2b8c3'
down_revision = 'e2b7c4d9a1f5'
branch_labels = None
depends_on = None


def upgrade():
    # Two new tables. Nothing existing is changed.
    op.create_table(
        'purchase_orders',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('po_number', sa.String(length=32), nullable=False),
        sa.Column('supplier', sa.String(length=255), nullable=False),
        sa.Column('supplier_ref', sa.String(length=120), nullable=True),
        sa.Column('project_id', sa.Integer(), sa.ForeignKey('projects.id'), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='draft'),
        sa.Column('order_date', sa.DateTime(), nullable=True),
        sa.Column('expected_date', sa.DateTime(), nullable=True),
        sa.Column('received_date', sa.DateTime(), nullable=True),
        sa.Column('currency', sa.String(length=8), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_purchase_orders_id', 'purchase_orders', ['id'])
    op.create_index('ix_purchase_orders_po_number', 'purchase_orders', ['po_number'], unique=True)
    op.create_index('ix_purchase_orders_supplier', 'purchase_orders', ['supplier'])
    op.create_index('ix_purchase_orders_status', 'purchase_orders', ['status'])
    op.create_table(
        'purchase_order_items',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('order_id', sa.Integer(), sa.ForeignKey('purchase_orders.id'), nullable=False),
        sa.Column('product_id', sa.Integer(), sa.ForeignKey('products.id'), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('unit_cost', sa.Float(), nullable=True),
        sa.Column('received_qty', sa.Integer(), nullable=True),
    )
    op.create_index('ix_purchase_order_items_id', 'purchase_order_items', ['id'])
    op.create_index('ix_purchase_order_items_order_id', 'purchase_order_items', ['order_id'])


def downgrade():
    op.drop_table('purchase_order_items')
    op.drop_table('purchase_orders')
