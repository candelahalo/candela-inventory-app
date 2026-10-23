"""CCTV and Wi-Fi & Network categories: move matching products out of Audio / Video / Security

Revision ID: e5c1a7d3f9b2
Revises: d2b6f8a0c4e7
Create Date: 2026-10-23 13:20:00

Data only: products in "Audio / Video / Security" that are cameras, recorders,
hard disks (CCTV) or access points, routers, network switches, racks
(Wi-Fi & Network) move to the new category; their datasheets follow.
Speakers, amplifiers etc. stay where they are.
"""
import re

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e5c1a7d3f9b2'
down_revision = 'd2b6f8a0c4e7'
branch_labels = None
depends_on = None

AV = "Audio / Video / Security"
CCTV_RE = r"cctv|camera|\bnvr\b|\bdvr\b|video recorder|surveillance|\bhdd\b|hard dis[ck]"
WIFI_RE = (r"wi-?fi|access point|\brouter\b|cloud gateway|firewall|poe switch|network switch|\bswitch\b.*\bport\b"
           r"|\d+\s*-?\s*port\b.*switch|it rack|\brack\b|patch panel")


def upgrade():
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, name, spec_summary FROM products WHERE category = :c"), {"c": AV}).fetchall()
    for pid, name, spec in rows:
        t = f"{name or ''} {spec or ''}".lower()
        new = "CCTV" if re.search(CCTV_RE, t) else "Wi-Fi & Network" if re.search(WIFI_RE, t) else None
        if not new:
            continue
        conn.execute(sa.text("UPDATE products SET category = :n WHERE id = :i"), {"n": new, "i": pid})
        conn.execute(sa.text("UPDATE datasheets SET category = :n WHERE product_id = :i AND category = :c"),
                     {"n": new, "i": pid, "c": AV})


def downgrade():
    conn = op.get_bind()
    for c in ("CCTV", "Wi-Fi & Network"):
        conn.execute(sa.text("UPDATE datasheets SET category = :a WHERE category = :c"), {"a": AV, "c": c})
        conn.execute(sa.text("UPDATE products SET category = :a WHERE category = :c"), {"a": AV, "c": c})
