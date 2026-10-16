"""one naming pattern for all products: name in capitals, SKU in the same
order (KOR S 17W 3000K WHITE / QB-KOR-S-17W-30K-WH; DRIVER ON/OFF — KOR 17W;
BAMBOO ENDCAP). Quotations show the new names since their lines link to the
products.

Revision ID: c4e6a8b0d2f5
Revises: b9d3f5a7c2e4
Create Date: 2026-10-16 17:30:00

"""
from alembic import op
import sqlalchemy as sa

from app.naming import standard_name, standard_sku


# revision identifiers, used by Alembic.
revision = 'c4e6a8b0d2f5'
down_revision = 'b9d3f5a7c2e4'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, sku, name, brand, category FROM products ORDER BY id")).fetchall()
    taken = {r[1] for r in rows}
    for pid, sku, name, brand, category in rows:
        new_name = standard_name(name, brand, category)
        new_sku = standard_sku(name, brand, category)
        if new_sku != sku:
            base, i = new_sku, 2
            while new_sku in taken:
                new_sku = f"{base[:60]}-{i}"
                i += 1
            taken.discard(sku)
            taken.add(new_sku)
        if (new_name, new_sku) != (name, sku):
            conn.execute(sa.text("UPDATE products SET name = :n, sku = :s WHERE id = :i"),
                         {"n": new_name, "s": new_sku, "i": pid})


def downgrade():
    # Old names aren't kept (a backup has them)
    pass
