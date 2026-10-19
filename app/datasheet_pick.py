"""Which datasheet goes out with a product, by its choice on the product page:

    supplier  the latest uploaded PDF - the supplier's or our own HALO one (the
              default; none uploaded yet: missing)
    halo      the HALO sheet made automatically from the product's data
    none      nothing (e.g. accessories)
"""
from app import models


def latest_by_kind(db, product_ids):
    """{product_id: {"supplier": sheet, "halo": sheet}} - newest of each kind."""
    out = {}  # also "any": the newest of either kind
    if not product_ids:
        return out
    sheets = (db.query(models.Datasheet)
              .filter(models.Datasheet.product_id.in_(list(product_ids)))
              .order_by(models.Datasheet.uploaded_at.desc()).all())
    for s in sheets:
        mine = out.setdefault(s.product_id, {})
        mine.setdefault(s.kind or "supplier", s)
        mine.setdefault("any", s)
    return out


def pick(product, latest):
    """("file", sheet) | ("auto", None) | ("missing", None) | ("none", None)"""
    mode = getattr(product, "datasheet_mode", None) or "supplier"
    mine = latest.get(product.id, {})
    if mode == "none":
        return "none", None
    if mode == "halo":
        return "auto", None
    return ("file", mine["any"]) if "any" in mine else ("missing", None)
