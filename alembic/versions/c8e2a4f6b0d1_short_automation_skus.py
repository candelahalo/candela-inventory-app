"""shorter SKUs for automation products: AUTO-BRAND-first words

Revision ID: c8e2a4f6b0d1
Revises: a3d9f5b1c7e4
Create Date: 2026-10-21 21:00:00

Data only: products in the automation categories get a short SKU
(AUTO-CONTROL4-T4-SERIES-TOUCHSCREENS). Quote lines point at products by id,
so nothing else changes. Downgrade leaves the new SKUs.
"""
import re

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c8e2a4f6b0d1'
down_revision = 'a3d9f5b1c7e4'
branch_labels = None
depends_on = None

AUTOMATION = ["Lighting Control", "Keypads & Switches", "Curtains & Blinds", "Audio / Video / Security",
              "AC Controls", "Sensors", "Intercom", "Automation Accessories"]


def _slug(s):
    return re.sub(r"[^A-Z0-9]+", "-", (s or "").upper()).strip("-")


def _sku(name, brand):
    b = _slug(brand)
    words = [w for w in (_slug(x) for x in " ".join((name or "").split()).upper().split()) if w]
    if b and words[:1] == [b]:
        words = words[1:]
    take = words[:3] if b else words[:4]
    return "-".join(["AUTO"] + ([b] if b else []) + take)[:48].rstrip("-") or "AUTO"


def upgrade():
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, sku, name, brand, category FROM products")).fetchall()
    taken = {r[1] for r in rows}
    for pid, sku, name, brand, category in sorted(rows, key=lambda r: r[0]):
        if category not in AUTOMATION:
            continue
        base = _sku(name, brand)
        if sku == base or re.fullmatch(re.escape(base) + r"-\d+", sku or ""):
            continue
        new, i = base, 2
        while new in taken:
            new = f"{base[:44]}-{i}"
            i += 1
        conn.execute(sa.text("UPDATE products SET sku = :s WHERE id = :i"), {"s": new, "i": pid})
        taken.discard(sku)
        taken.add(new)


def downgrade():
    pass
