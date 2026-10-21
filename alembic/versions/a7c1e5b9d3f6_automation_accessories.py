"""Automation Accessories category: bus / data cables and enclosures already
filed under (lighting) Accessories move there

Revision ID: a7c1e5b9d3f6
Revises: f2b6d8a4c0e3
Create Date: 2026-10-21 11:45:00

"""
import re

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a7c1e5b9d3f6'
down_revision = 'f2b6d8a4c0e3'
branch_labels = None
depends_on = None

AUTOMATION = re.compile(r"knx|\beib\b|cat ?6|cat ?5|\butp\b|dali cable|enclosure|db box|din rail|patch panel", re.I)


def upgrade():
    bind = op.get_bind()
    products = sa.table('products', sa.column('id', sa.Integer), sa.column('name', sa.String),
                        sa.column('category', sa.String))
    rows = bind.execute(sa.select(products.c.id, products.c.name).where(products.c.category == 'Accessories')).fetchall()
    ids = [pid for pid, name in rows if AUTOMATION.search(name or '')]
    if ids:
        bind.execute(products.update().where(products.c.id.in_(ids)).values(category='Automation Accessories'))


def downgrade():
    op.execute("UPDATE products SET category = 'Accessories' WHERE category = 'Automation Accessories'")
