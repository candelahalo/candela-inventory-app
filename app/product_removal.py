"""
Removing products for good, without breaking anything that used them.

  - quotation lines and supplier-order lines stay, as text: the product's
    name, spec, unit and photo are copied onto the line first, so quotation
    PDFs look the same
  - stock movements of those products are deleted (stock levels go to zero)
  - their datasheets (records and PDF files) are deleted
Product photos stay on disk, since quotation lines may still show them.
"""
import os
import re

from app import models
from app.utils import log_activity, url_to_disk_path

PHOTO = re.compile(r"/static/uploads/products/[0-9a-f]{32}\.jpg")


def impact(db, ids):
    """What removing these products would touch, for a confirmation."""
    return {
        "products": len(ids),
        "quotation_lines": db.query(models.QuotationItem).filter(models.QuotationItem.product_id.in_(ids)).count(),
        "order_lines": db.query(models.PurchaseOrderItem).filter(models.PurchaseOrderItem.product_id.in_(ids)).count(),
        "stock_movements": db.query(models.StockMovement).filter(models.StockMovement.product_id.in_(ids)).count(),
        "datasheets": db.query(models.Datasheet).filter(models.Datasheet.product_id.in_(ids)).count(),
    }


def remove_products(db, products, username, detail=None):
    """Removes the given products as described above. The caller commits."""
    ids = [p.id for p in products]
    if not ids:
        return 0
    by_id = {p.id: p for p in products}
    for line in db.query(models.QuotationItem).filter(models.QuotationItem.product_id.in_(ids)).all():
        p = by_id[line.product_id]
        desc = (line.description or p.spec_summary or "").strip()
        if p.name and not desc.lower().startswith(p.name.lower()):
            desc = f"{p.name}\n{desc}".strip()
        line.description = desc or None
        line.unit = line.unit or p.unit
        if not line.image_path and p.image_path and PHOTO.fullmatch(p.image_path):
            line.image_path = p.image_path
        line.product_id = None
    for line in db.query(models.PurchaseOrderItem).filter(models.PurchaseOrderItem.product_id.in_(ids)).all():
        p = by_id[line.product_id]
        line.description = line.description or f"{p.sku} — {p.name}"
        line.product_id = None
    for m in db.query(models.StockMovement).filter(models.StockMovement.product_id.in_(ids)).all():
        db.delete(m)
    for s in db.query(models.Datasheet).filter(models.Datasheet.product_id.in_(ids)).all():
        try:
            os.remove(url_to_disk_path(s.file_path))
        except (FileNotFoundError, TypeError):
            pass
        db.delete(s)
    db.flush()
    for p in products:
        log_activity(db, username, "product", p.id, f"{p.sku} — {p.name}", "deleted", detail)
        db.delete(p)
    db.flush()
    return len(ids)
