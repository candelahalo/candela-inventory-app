"""
Creates draft supplier orders from a prepared list (scripts/data/orders_*.json),
together with the customer and project if they don't exist yet.

Lines that carry a product definition get that product created (by SKU, if
it isn't in the product list yet) and linked, so receiving the order books
the goods into stock.

Safe to re-run: orders from the same source that already exist are updated
(lines, shipping mode, planned delivery) as long as they are still drafts
with nothing received. On orders further along, lines are only linked to
their products where nothing has been received yet. Costs are left at 0 -
fill them in on the Orders page as each order is placed.

Usage (on the server):
    cd /opt/candela-inventory-app && venv/bin/python scripts/create_orders.py scripts/data/orders_lacoste_qtn_rt09_3079.json
"""
import json
import os
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import func  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app import models, workflow  # noqa: E402
from app.routers.orders import _next_po_number  # noqa: E402
from app.utils import log_activity  # noqa: E402


def _key(desc):
    """Line text without trailing notes in brackets, for matching."""
    return re.sub(r"\s*\(.*?\)\s*$", "", (desc or "")).strip().lower()


def _match_orders(existing, wanted):
    """Pair each order in the file with an order already made from the same
    source - by its lines, so a renamed supplier (e.g. the actual HALO
    maker filled in) is still recognised."""
    pairs, free = {}, list(existing)
    for idx, o in enumerate(wanted):
        keys = {_key(l[0]) for l in o["lines"]}
        best, score = None, 0
        for po in free:
            n = len(keys & {_key(i.description) for i in po.items})
            if po.supplier in (o["supplier"], o.get("was")):
                n += 0.5
            if n > score:
                best, score = po, n
        if best is not None:
            pairs[idx] = best
            free.remove(best)
    return pairs


def ensure_product(db, spec, made):
    """The product for an order line: found by SKU, or created."""
    if not spec:
        return None
    prod = db.query(models.Product).filter(models.Product.sku == spec["sku"]).first()
    if prod:
        if not prod.is_active:
            prod.is_active = True
        return prod
    prod = models.Product(sku=spec["sku"], name=spec["name"], brand=spec.get("brand"), supplier=spec.get("supplier"),
                          category=spec.get("category"), product_type=spec.get("product_type"),
                          unit=spec.get("unit") or "pcs", cost_price=0.0,
                          selling_price=float(spec.get("selling_price") or 0), reorder_level=0, is_active=True)
    db.add(prod)
    db.flush()
    log_activity(db, "system", "product", prod.id, f"{prod.sku} — {prod.name}", "created", "for supplier orders")
    made.append(prod.sku)
    return prod


def main(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    db = SessionLocal()
    try:
        tag = f"From {data['source']}"
        existing = _match_orders(
            db.query(models.PurchaseOrder).filter(models.PurchaseOrder.notes.like(tag + "%")).all(), data["orders"])
        planned = datetime.fromisoformat(data["delivery_planned"]) if data.get("delivery_planned") else None
        made = []

        c = data["customer"]
        customer = db.query(models.Customer).filter(func.lower(models.Customer.name) == c["name"].lower()).first()
        if not customer:
            customer = models.Customer(name=c["name"], address=c.get("address"), category=c.get("category"))
            db.add(customer)
            db.flush()
            log_activity(db, "system", "customer", customer.id, customer.name, "created", "for supplier orders")
            print(f"Customer added: {customer.name}")

        p = data["project"]
        project = db.query(models.Project).filter(func.lower(models.Project.name) == p["name"].lower()).first()
        if not project:
            project = models.Project(project_number=workflow.next_project_number(db), name=p["name"],
                                     customer_id=customer.id, division=p.get("division"), category=p.get("category"),
                                     site_address=p.get("site_address"), status=models.ProjectStatus.enquiry,
                                     notes=f"Client promise: {data.get('client_promise', '')}")
            db.add(project)
            db.flush()
            project.status_history.append(models.ProjectStatusHistory(
                status=models.ProjectStatus.enquiry, notes=f"Created for ordering {data['source']}"))
            log_activity(db, "system", "project", project.id, f"{project.project_number} — {project.name}", "created")
            print(f"Project added: {project.project_number} {project.name}")
        if data.get("client_confirmed"):
            project.notes = f"Client promise: {data.get('client_promise', '')}"
            if planned and not project.target_completion_date:
                project.target_completion_date = planned
            if workflow.advance_project(db, project, models.ProjectStatus.approved,
                                        f"order confirmed by client ({data['source']})", "system"):
                print(f"Project {project.project_number} moved to Approved")

        for idx, o in enumerate(data["orders"]):
            note = f"{tag}. {o.get('notes', '')}".strip()
            po = existing.get(idx)
            if po is not None:
                if po.status != "draft" or po.qty_received or po.qty_delivered:
                    # Already placed: only link lines to their products
                    linked = 0
                    by_desc = {_key(l[0]): l for l in o["lines"]}
                    for item in po.items:
                        line = by_desc.get(_key(item.description))
                        if item.product_id or (item.received_qty or 0) or not line or len(line) < 3:
                            continue
                        item.product_id = ensure_product(db, line[2], made).id
                        linked += 1
                    print(f"{po.po_number}  {po.supplier:<20} already {po.status} - {linked} line(s) linked to products")
                    continue
                costs = {_key(i.description): i.unit_cost for i in po.items if i.unit_cost}  # keep costs typed in
                po.items.clear()
                db.flush()
                if po.supplier in (o["supplier"], o.get("was")):
                    po.supplier = o["supplier"]  # keep a supplier someone has filled in
                po.ship_mode, po.notes, po.delivery_planned = o.get("ship_mode"), note, planned
                for line in o["lines"]:
                    prod = ensure_product(db, line[2] if len(line) > 2 else None, made)
                    po.items.append(models.PurchaseOrderItem(product_id=prod.id if prod else None,
                                                             description=line[0], quantity=line[1],
                                                             unit_cost=costs.get(_key(line[0]), 0.0),
                                                             received_qty=0, delivered_qty=0))
                log_activity(db, "system", "order", po.id, f"{po.po_number} — {po.supplier}", "updated", tag)
                print(f"{po.po_number}  {po.supplier:<20} {len(o['lines']):>2} lines, {sum(l[1] for l in o['lines'])} pcs (updated)")
                continue
            po = models.PurchaseOrder(po_number=_next_po_number(db), supplier=o["supplier"], status="draft",
                                      project_id=project.id, currency="AED", ship_mode=o.get("ship_mode"),
                                      notes=note, delivery_planned=planned)
            for line in o["lines"]:
                prod = ensure_product(db, line[2] if len(line) > 2 else None, made)
                po.items.append(models.PurchaseOrderItem(product_id=prod.id if prod else None,
                                                         description=line[0], quantity=line[1], unit_cost=0.0,
                                                         received_qty=0, delivered_qty=0))
            db.add(po)
            db.flush()
            log_activity(db, "system", "order", po.id, f"{po.po_number} — {po.supplier}", "created", tag)
            print(f"{po.po_number}  {po.supplier:<20} {len(po.items):>2} lines, {sum(l[1] for l in o['lines'])} pcs")
        db.commit()
        if made:
            print(f"{len(made)} products added: " + ", ".join(made))
        print("Done. Open Orders in the app to add costs and dates. Receiving an order now books it into stock.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
