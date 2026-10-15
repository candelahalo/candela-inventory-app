"""move products and datasheets to the new category list (Spotlight,
Downlight, 230V / 48V Track Light, Surface Mounted, Linear Light, Semi
Recessed Light, Strip Light, Neon Light, Accessories)

Anything without a clear match keeps its old category and shows under
"Other" until someone picks one.

Revision ID: c7e3a1d5f9b2
Revises: b5d1f7a9c3e2
Create Date: 2026-10-15 15:40:00

"""
from alembic import op
import sqlalchemy as sa

from app.categories import from_old


# revision identifiers, used by Alembic.
revision = 'c7e3a1d5f9b2'
down_revision = 'b5d1f7a9c3e2'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    rows = conn.execute(sa.text(
        "SELECT id, category, product_type, name, spec_summary FROM products")).fetchall()
    for pid, cat, ptype, name, spec in rows:
        new = from_old(cat, ptype, " ".join(filter(None, [name, spec])))
        if new and new != cat:
            conn.execute(sa.text("UPDATE products SET category = :c WHERE id = :i"), {"c": new, "i": pid})

    rows = conn.execute(sa.text("SELECT id, category, title FROM datasheets")).fetchall()
    for did, cat, title in rows:
        new = from_old(cat, None, title or "")
        if new and new != cat:
            conn.execute(sa.text("UPDATE datasheets SET category = :c WHERE id = :i"), {"c": new, "i": did})


def downgrade():
    # The old categories aren't kept; nothing to undo
    pass
