"""rename sales role to office

Revision ID: 95f0c25e35de
Revises: f43413f595e4
Create Date: 2026-09-10 16:25:35.259813

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '95f0c25e35de'
down_revision = 'f43413f595e4'
branch_labels = None
depends_on = None


def upgrade():
    # Any account created before the rename still says "sales"; without
    # this they would fall through to no role defaults and lose access.
    op.execute("UPDATE users SET role = 'office' WHERE role = 'sales'")


def downgrade():
    op.execute("UPDATE users SET role = 'sales' WHERE role = 'office'")
