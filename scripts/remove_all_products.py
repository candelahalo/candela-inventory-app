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
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import SessionLocal  # noqa: E402
from app import models  # noqa: E402
from app.utils import log_activity  # noqa: E402
from app.product_removal import remove_products  # noqa: E402


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

        remove_products(db, products, "system", "removed with all products")
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
