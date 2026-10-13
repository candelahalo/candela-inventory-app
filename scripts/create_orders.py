"""
Creates draft supplier orders from a prepared list (scripts/data/orders_*.json),
together with the customer and project if they don't exist yet.

Safe to re-run: if orders from the same source already exist, nothing is
created. Costs are left at 0 and dates empty - fill them in on the Orders
page as each order is placed.

Usage (on the server):
    cd /opt/candela-inventory-app && venv/bin/python scripts/create_orders.py scripts/data/orders_lacoste_qtn_rt09_3079.json
"""
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import func  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app import models, workflow  # noqa: E402
from app.routers.orders import _next_po_number  # noqa: E402
from app.utils import log_activity  # noqa: E402


def main(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    db = SessionLocal()
    try:
        tag = f"From {data['source']}"
        existing = db.query(models.PurchaseOrder).filter(models.PurchaseOrder.notes.like(tag + "%")).all()
        if existing:
            print("Already created: " + ", ".join(o.po_number for o in existing) + " - nothing changed.")
            return

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

        for o in data["orders"]:
            po = models.PurchaseOrder(po_number=_next_po_number(db), supplier=o["supplier"], status="draft",
                                      project_id=project.id, currency="AED", ship_mode=o.get("ship_mode"),
                                      notes=f"{tag}. {o.get('notes', '')}".strip())
            for desc, qty in o["lines"]:
                po.items.append(models.PurchaseOrderItem(description=desc, quantity=qty, unit_cost=0.0,
                                                         received_qty=0, delivered_qty=0))
            db.add(po)
            db.flush()
            log_activity(db, "system", "order", po.id, f"{po.po_number} — {po.supplier}", "created", tag)
            print(f"{po.po_number}  {po.supplier:<20} {len(po.items):>2} lines, {sum(q for _, q in o['lines'])} pcs")
        db.commit()
        print("Done. Open Orders in the app to add costs and dates.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
