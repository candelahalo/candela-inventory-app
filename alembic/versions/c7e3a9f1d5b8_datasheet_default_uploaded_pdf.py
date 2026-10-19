"""datasheets: uploaded PDF is the default; the automatic HALO sheet is only
used when chosen on the product

Revision ID: c7e3a9f1d5b8
Revises: b5d1f7a3c9e2
Create Date: 2026-10-19 17:00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c7e3a9f1d5b8'
down_revision = 'b5d1f7a3c9e2'
branch_labels = None
depends_on = None


def upgrade():
    # 'supplier' now means "the uploaded PDF" (a supplier's or our own HALO one)
    op.execute("UPDATE products SET datasheet_mode = 'supplier' WHERE datasheet_mode = 'halo'")
    with op.batch_alter_table('products') as b:
        b.alter_column('datasheet_mode', existing_type=sa.String(length=16), existing_nullable=False,
                       server_default='supplier')


def downgrade():
    with op.batch_alter_table('products') as b:
        b.alter_column('datasheet_mode', existing_type=sa.String(length=16), existing_nullable=False,
                       server_default='halo')
