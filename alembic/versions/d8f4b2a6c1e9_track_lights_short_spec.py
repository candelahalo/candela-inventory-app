"""230V and 48V track lights: short spec summary - only code, watt, lumen,
CCT, CRI, beam, IP, finish, dimming, voltage, rated life, dimension and warranty,
in that order
(the datasheet PDF keeps the rest). Quotations already made keep their text.

Revision ID: d8f4b2a6c1e9
Revises: c7e3a9f1d5b8
Create Date: 2026-10-20 11:00:00

"""
import re

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd8f4b2a6c1e9'
down_revision = 'c7e3a9f1d5b8'
branch_labels = None
depends_on = None

CATEGORIES = ("230V Track Light", "48V Track Light")
KEEP = ["Code", "Wattage", "Luminous Flux", "CCT", "CRI", "Beam Angle", "IP Rating", "Finish", "Control",
        "Voltage", "Rated life", "Dimension", "Warranty"]
# label (lower case) -> standard label, as the datasheet reader names them
LABELS = [
    (r"^code\b", "Code"),
    (r"^(power(?! supply)|wattage|watt\b|system power|rated power|consumption|power consumption)", "Wattage"),
    (r"(luminous flux|lumen|light output|flux)", "Luminous Flux"),
    (r"(colou?r temp|cct)", "CCT"),
    (r"^(cri\b|ra\b|colour rendering|color rendering)", "CRI"),
    (r"(ip rating|protection|ingress|^ip\b)", "IP Rating"),
    (r"(beam|optic)", "Beam Angle"),
    (r"^(finish|colou?rs?|body colou?r)", "Finish"),
    (r"(dimming|control)", "Control"),
    (r"(voltage|supply)", "Voltage"),
    (r"^(duration|lifetime|life ?time|rated life)", "Rated life"),
    (r"(dimension|size|overall|diameter|cut[- ]?out|cutout|hole)", "Dimension"),
    (r"warranty|guarantee", "Warranty"),
]


def _std(label):
    l = label.strip().lower()
    for pat, std in LABELS:
        if re.search(pat, l):
            return std
    return None


def short_spec(spec):
    kept = []
    for line in (spec or "").splitlines():
        line = line.strip()
        if not line:
            continue
        if ":" in line:
            label, value = line.split(":", 1)
            std = _std(label)
            if std and value.strip():
                kept.append((std, f"{std}: {value.strip()}"))
        else:
            std = _std(line)  # "CRI >90"
            if std:
                kept.append((std, line))
    order = {k: i for i, k in enumerate(KEEP)}
    seen, out = set(), []
    for std, line in sorted(kept, key=lambda x: order[x[0]]):
        if std not in seen:
            seen.add(std)
            out.append(line)
    return "\n".join(out)


def upgrade():
    bind = op.get_bind()
    products = sa.table('products', sa.column('id', sa.Integer), sa.column('category', sa.String),
                        sa.column('spec_summary', sa.Text))
    rows = bind.execute(sa.select(products.c.id, products.c.spec_summary)
                        .where(products.c.category.in_(CATEGORIES))).fetchall()
    for pid, spec in rows:
        new = short_spec(spec)
        if spec and new and new != spec:
            bind.execute(products.update().where(products.c.id == pid).values(spec_summary=new))


def downgrade():
    pass  # the removed lines are not kept (restore a backup if they're needed)
