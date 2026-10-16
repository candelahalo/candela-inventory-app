"""rename the "Linear Light" category to "Custom Light"

Revision ID: d9f2b4c6e8a1
Revises: c7e3a1d5f9b2
Create Date: 2026-10-16 10:15:00

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'd9f2b4c6e8a1'
down_revision = 'c7e3a1d5f9b2'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("UPDATE products SET category = 'Custom Light' WHERE category = 'Linear Light'")
    op.execute("UPDATE datasheets SET category = 'Custom Light' WHERE category = 'Linear Light'")


def downgrade():
    op.execute("UPDATE products SET category = 'Linear Light' WHERE category = 'Custom Light'")
    op.execute("UPDATE datasheets SET category = 'Linear Light' WHERE category = 'Custom Light'")
