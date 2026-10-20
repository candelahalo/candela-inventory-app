"""Track Accessories category: accessories of a track system move there
from Accessories - any with "TRACK" in the name, and the rest of the same
family (BAMBOO connectors, end caps ... go with the BAMBOO track channel).

Revision ID: e5a9c3d7f1b2
Revises: d8f4b2a6c1e9
Create Date: 2026-10-20 15:30:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e5a9c3d7f1b2'
down_revision = 'd8f4b2a6c1e9'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    products = sa.table('products', sa.column('id', sa.Integer), sa.column('name', sa.String),
                        sa.column('brand', sa.String), sa.column('category', sa.String))
    rows = bind.execute(sa.select(products.c.id, products.c.name, products.c.brand)
                        .where(products.c.category == 'Accessories')).fetchall()
    family = lambda name, brand: ((brand or '').upper(), (name or '').split()[0].upper() if name and name.split() else '')  # noqa: E731
    track_families = {family(n, b) for _, n, b in rows if 'TRACK' in (n or '').upper()}
    ids = [pid for pid, n, b in rows if 'TRACK' in (n or '').upper() or family(n, b) in track_families]
    if ids:
        bind.execute(products.update().where(products.c.id.in_(ids)).values(category='Track Accessories'))


def downgrade():
    op.execute("UPDATE products SET category = 'Accessories' WHERE category = 'Track Accessories'")
