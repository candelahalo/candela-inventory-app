"""a separate "Drivers" category: drivers / power supplies / transformers
filed under Accessories move there

Revision ID: f3b8d6a2c4e7
Revises: e1a7c3f5b9d2
Create Date: 2026-10-16 12:30:00

"""
import re

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f3b8d6a2c4e7'
down_revision = 'e1a7c3f5b9d2'
branch_labels = None
depends_on = None

DRIVER = re.compile(r"\bdriver|power supply|\bpsu\b|transformer", re.I)


def upgrade():
    conn = op.get_bind()
    rows = conn.execute(sa.text(
        "SELECT id, name, sku FROM products WHERE category = 'Accessories' OR category IS NULL")).fetchall()
    for pid, name, sku in rows:
        if DRIVER.search(" ".join(filter(None, [name, sku.replace("-DRV-", " driver ") if sku else None]))):
            conn.execute(sa.text("UPDATE products SET category = 'Drivers' WHERE id = :i"), {"i": pid})
    rows = conn.execute(sa.text(
        "SELECT id, title FROM datasheets WHERE category = 'Accessories' OR category IS NULL")).fetchall()
    for did, title in rows:
        if DRIVER.search(title or ""):
            conn.execute(sa.text("UPDATE datasheets SET category = 'Drivers' WHERE id = :i"), {"i": did})


def downgrade():
    op.execute("UPDATE products SET category = 'Accessories' WHERE category = 'Drivers'")
    op.execute("UPDATE datasheets SET category = 'Accessories' WHERE category = 'Drivers'")
