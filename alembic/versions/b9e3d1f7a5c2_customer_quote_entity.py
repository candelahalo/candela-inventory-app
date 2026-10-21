"""customers: which company their quotations come from - Candelaria Light
Fittings Trading LLC (all) or Candela Lighting and Automation LLC (Infinia)

Revision ID: b9e3d1f7a5c2
Revises: a7c1e5b9d3f6
Create Date: 2026-10-21 12:00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b9e3d1f7a5c2'
down_revision = 'a7c1e5b9d3f6'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('customers', sa.Column('quote_entity', sa.String(length=20), nullable=False,
                                         server_default='candelaria'))
    op.execute("UPDATE customers SET quote_entity = 'candela' "
               "WHERE lower(name) LIKE '%infinia%' OR lower(coalesce(company, '')) LIKE '%infinia%'")


def downgrade():
    op.drop_column('customers', 'quote_entity')
