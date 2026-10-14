"""
Removes every product, so the list can be rebuilt from quotations in the new
format (Import PDF on the Quotations page adds products as it goes).

What happens to things that used a product:
  - quotation lines and supplier-order lines stay, as text: the product's
    name, spec, unit and photo are copied onto the line first, so quotation
    PDFs look the same
  - stock movements of those products are deleted (stock levels go to zero)
  - their datasheets (records and PDF files) are deleted
Product photos are kept on disk, since quotation lines may still show them.

Run without --yes to see what would happen; nothing is changed.

Usage (on the server):
    cd /opt/candela-inventory-app && venv/bin/python scripts/remove_all_products.py          # preview
    cd /opt/candela-inventory-app && venv/bin/python scripts/remove_all_products.py --yes    # remove
"""
import os
import re
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import SessionLocal  # noqa: E402
from app import models  # noqa: E402
from app.utils import log_activity, url_to_disk_path  # noqa: E402

PHOTO = re.compile(r"/static/uploads/products/[0-9a-f]{32}\.jpg")


def main():
    apply = "--yes" in sys.argv
    db = SessionLocal()
    try:
        products = db.query(models.Product).all()
        ids = [p.id for p in products]
        if not ids:
            print("There are no products. Nothing to do.")
            return
        q_lines = db.query(models.QuotationItem).filter(models.QuotationItem.product_id.in_(ids)).all()
        po_lines = db.query(models.PurchaseOrderItem).filter(models.PurchaseOrderItem.product_id.in_(ids)).all()
        moves = db.query(models.StockMovement).filter(models.StockMovement.product_id.in_(ids)).all()
        sheets = db.query(models.Datasheet).filter(models.Datasheet.product_id.in_(ids)).all()

        print(f"{len(products)} products will be removed.")
        print(f"  {len(q_lines)} quotation lines keep their text, unit and photo (no longer linked to a product)")
        print(f"  {len(po_lines)} supplier-order lines keep their text")
        print(f"  {len(moves)} stock movements deleted (stock levels go to zero)")
        print(f"  {len(sheets)} datasheets deleted")
        if not apply:
            print("\nNothing changed. Run again with --yes to remove.")
            return

        by_id = {p.id: p for p in products}
        for line in q_lines:
            p = by_id[line.product_id]
            desc = (line.description or p.spec_summary or "").strip()
            if p.name and not desc.lower().startswith(p.name.lower()):
                desc = f"{p.name}\n{desc}".strip()
            line.description = desc or None
            line.unit = line.unit or p.unit
            if not line.image_path and p.image_path and PHOTO.fullmatch(p.image_path):
                line.image_path = p.image_path
            line.product_id = None
        for line in po_lines:
            p = by_id[line.product_id]
            line.description = line.description or f"{p.sku} — {p.name}"
            line.product_id = None
        for m in moves:
            db.delete(m)
        for s in sheets:
            try:
                os.remove(url_to_disk_path(s.file_path))
            except (FileNotFoundError, TypeError):
                pass
            db.delete(s)
        db.flush()
        for p in products:
            db.delete(p)
        log_activity(db, "system", "product", None, "All products", "deleted",
                     f"{len(products)} products removed; quotation and order lines kept as text")
        db.commit()
        print(f"\nDone: {len(products)} products removed.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
