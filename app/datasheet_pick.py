"""Which datasheet goes out with a product, by its choice on the product page:

    halo      an uploaded HALO sheet if there is one, else the one made automatically
    supplier  the latest uploaded supplier PDF (none yet: missing)
    none      nothing (e.g. accessories)
"""
from app import models


def latest_by_kind(db, product_ids):
    """{product_id: {"supplier": sheet, "halo": sheet}} - newest of each kind."""
    out = {}
    if not product_ids:
        return out
    sheets = (db.query(models.Datasheet)
              .filter(models.Datasheet.product_id.in_(list(product_ids)))
              .order_by(models.Datasheet.uploaded_at.desc()).all())
    for s in sheets:
        out.setdefault(s.product_id, {}).setdefault(s.kind or "supplier", s)
    return out


def pick(product, latest):
    """("file", sheet) | ("auto", None) | ("missing", None) | ("none", None)"""
    mode = getattr(product, "datasheet_mode", None) or "halo"
    mine = latest.get(product.id, {})
    if mode == "none":
        return "none", None
    if mode == "supplier":
        return ("file", mine["supplier"]) if "supplier" in mine else ("missing", None)
    return ("file", mine["halo"]) if "halo" in mine else ("auto", None)
