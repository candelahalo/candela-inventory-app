"""Audio / Video / Security goes: CCTV, Wi-Fi & Network and Background Music instead

Revision ID: e5c1a7d3f9b2
Revises: d2b6f8a0c4e7
Create Date: 2026-10-23 13:20:00

Data only: every product in "Audio / Video / Security" moves - access points,
routers, network switches, racks to Wi-Fi & Network; speakers, amplifiers,
streamers to Background Music; iPad / tablet to Keypads & Switches; access
control to Intercom; everything else (cameras, recorders...) to CCTV. Their
datasheets follow.
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
MUSIC_RE = r"speaker|amplifier|\bamp\b|subwoofer|streamer|audio|music|soundbar|\bsonos\b"
NEW = ("CCTV", "Wi-Fi & Network", "Background Music")


def _new(t):
    if re.search(CCTV_RE, t):
        return "CCTV"
    if re.search(WIFI_RE, t):
        return "Wi-Fi & Network"
    if re.search(r"\bipad\b|tablet|wall station|touch ?screen|touch ?panel", t):
        return "Keypads & Switches"
    if re.search(MUSIC_RE, t):
        return "Background Music"
    if re.search(r"access control|rfid|exit button|em lock|maglock", t):
        return "Intercom"
    return "CCTV"


def upgrade():
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, name, spec_summary FROM products WHERE category = :c"), {"c": AV}).fetchall()
    for pid, name, spec in rows:
        t = f"{name or ''} {spec or ''}".lower()
        new = _new(t)
        conn.execute(sa.text("UPDATE products SET category = :n WHERE id = :i"), {"n": new, "i": pid})
        conn.execute(sa.text("UPDATE datasheets SET category = :n WHERE product_id = :i AND category = :c"),
                     {"n": new, "i": pid, "c": AV})
    # datasheets on their own (no product): CCTV
    conn.execute(sa.text("UPDATE datasheets SET category = 'CCTV' WHERE category = :c"), {"c": AV})


def downgrade():
    conn = op.get_bind()
    for c in NEW:
        conn.execute(sa.text("UPDATE datasheets SET category = :a WHERE category = :c"), {"a": AV, "c": c})
        conn.execute(sa.text("UPDATE products SET category = :a WHERE category = :c"), {"a": AV, "c": c})
