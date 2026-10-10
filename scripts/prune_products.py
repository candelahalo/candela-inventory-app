"""
Deletes every product except the 10 original CND- catalogue items, along with
everything attached to the deleted products: their datasheets (records and
PDF files), photos, quotation lines and stock movements. A quotation left
with no lines is deleted too.

Run without --yes to see what would be deleted; nothing is changed.

Usage (on the server):
    cd /opt/candela-inventory-app && venv/bin/python scripts/prune_products.py          # preview
    cd /opt/candela-inventory-app && venv/bin/python scripts/prune_products.py --yes    # delete
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import SessionLocal  # noqa: E402
from app import models  # noqa: E402
from app.utils import log_activity, url_to_disk_path  # noqa: E402

KEEP = {
    "CND-DL-100", "CND-DL-101", "CND-TR-210", "CND-PD-330", "CND-STR-050",
    "CND-HA-010", "CND-HA-020", "CND-HA-025", "CND-HA-030", "CND-OUT-400",
}


def remove_file(url_path):
    if not url_path:
        return
    path = url_to_disk_path(url_path)
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


def main():
    apply = "--yes" in sys.argv
    db = SessionLocal()
    try:
        products = db.query(models.Product).all()
        keep = [p for p in products if p.sku in KEEP]
        drop = [p for p in products if p.sku not in KEEP]
        drop_ids = {p.id for p in drop}

        sheets = db.query(models.Datasheet).filter(models.Datasheet.product_id.in_(drop_ids)).all() if drop_ids else []
        moves = db.query(models.StockMovement).filter(models.StockMovement.product_id.in_(drop_ids)).all() if drop_ids else []
        lines = db.query(models.QuotationItem).filter(models.QuotationItem.product_id.in_(drop_ids)).all() if drop_ids else []
        touched_quotes = {l.quotation_id for l in lines}
        emptied = [q for q in db.query(models.Quotation).filter(models.Quotation.id.in_(touched_quotes)).all()
                   if all(i.product_id in drop_ids for i in q.items)] if touched_quotes else []

        print(f"Keeping {len(keep)} products: {', '.join(sorted(p.sku for p in keep))}")
        missing = KEEP - {p.sku for p in keep}
        if missing:
            print(f"  (not found, nothing to keep for: {', '.join(sorted(missing))})")
        print(f"Deleting {len(drop)} products, {len(sheets)} datasheets, {len(moves)} stock movements, "
              f"{len(lines)} quotation lines, {len(emptied)} quotations left empty "
              f"({', '.join(q.quote_number for q in emptied) or 'none'}).")

        if not apply:
            print("\nPreview only - nothing changed. Run again with --yes to delete.")
            return

        files = [s.file_path for s in sheets] + [p.image_path for p in drop]
        for q in emptied:
            log_activity(db, "system", "quotation", q.id, q.quote_number, "deleted", "dummy data clean-up")
            db.delete(q)  # its lines go with it
        db.flush()
        for l in lines:
            if db.query(models.QuotationItem).get(l.id):
                db.delete(l)
        for m in moves:
            db.delete(m)
        for s in sheets:
            db.delete(s)
        for p in drop:
            log_activity(db, "system", "product", p.id, f"{p.sku} — {p.name}", "deleted", "dummy data clean-up")
            db.delete(p)
        db.commit()

        # Files only after the database change has gone through
        for f in files:
            remove_file(f)
        print("\nDone.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
