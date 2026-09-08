"""
Seed the database with realistic dummy data across every section:
warehouses, products, customers, projects (at various pipeline stages),
stock movements, and quotations.

Usage (on the server, inside the venv):
    python3 scripts/seed_data.py

Safe to run on a fresh database. Re-running will create duplicate rows
(it does not check for existing data), so only run it once per environment.
"""
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import SessionLocal
from app import models

db = SessionLocal()

print("Seeding warehouses...")
main_wh = models.Warehouse(name="Main Warehouse", location="Al Quoz, Dubai")
site_wh = models.Warehouse(name="Site Store - Sharjah", location="Al Sajaa, Sharjah")
db.add_all([main_wh, site_wh])
db.flush()

print("Seeding products...")
products_data = [
    dict(sku="CND-DL-100", name="LED Downlight 12W, 3000K", category="Downlights", brand="Candela", unit="pcs", cost_price=18, selling_price=42, reorder_level=50),
    dict(sku="CND-DL-101", name="LED Downlight 18W, 4000K", category="Downlights", brand="Candela", unit="pcs", cost_price=24, selling_price=55, reorder_level=40),
    dict(sku="CND-TR-210", name="LED Track Light Head, 15W", category="Track Lighting", brand="Candela", unit="pcs", cost_price=48, selling_price=110, reorder_level=20),
    dict(sku="CND-PD-330", name="Pendant Light - Brushed Brass", category="Decorative", brand="Candela", unit="pcs", cost_price=210, selling_price=480, reorder_level=8),
    dict(sku="CND-STR-050", name="LED Strip Light 24V, 5m reel", category="Strip Lighting", brand="Candela", unit="reel", cost_price=35, selling_price=85, reorder_level=30),
    dict(sku="CND-HA-010", name="Smart Lighting Hub", category="Home Automation", brand="Candela Home", unit="pcs", cost_price=310, selling_price=590, reorder_level=5),
    dict(sku="CND-HA-020", name="Smart Dimmer Switch, 1-Gang", category="Home Automation", brand="Candela Home", unit="pcs", cost_price=65, selling_price=145, reorder_level=15),
    dict(sku="CND-HA-025", name="Smart Curtain Motor", category="Home Automation", brand="Candela Home", unit="pcs", cost_price=180, selling_price=390, reorder_level=6),
    dict(sku="CND-HA-030", name="Voice Control Panel, 7-inch", category="Home Automation", brand="Candela Home", unit="pcs", cost_price=420, selling_price=850, reorder_level=4),
    dict(sku="CND-OUT-400", name="Outdoor Wall Light, IP65", category="Outdoor", brand="Candela", unit="pcs", cost_price=55, selling_price=125, reorder_level=12),
]
products = [models.Product(**p) for p in products_data]
db.add_all(products)
db.flush()
by_sku = {p.sku: p for p in products}

print("Stocking the main warehouse...")
initial_stock = {
    "CND-DL-100": 400, "CND-DL-101": 280, "CND-TR-210": 90,
    "CND-PD-330": 22, "CND-STR-050": 150, "CND-HA-010": 18,
    "CND-HA-020": 60, "CND-HA-025": 14, "CND-HA-030": 3,  # intentionally below reorder level
    "CND-OUT-400": 45,
}
for sku, qty in initial_stock.items():
    db.add(models.StockMovement(
        product_id=by_sku[sku].id, warehouse_id=main_wh.id,
        movement_type=models.MovementType.in_, quantity=qty,
        reference="Opening stock", created_at=datetime.utcnow() - timedelta(days=30),
    ))
db.flush()

print("Seeding customers...")
customers_data = [
    dict(name="Rashid Al Maktoum", company="Private Villa - Emirates Hills", email="rashid.pm@example.com", phone="+971 50 111 2222", address="Emirates Hills, Dubai"),
    dict(name="Fatima Al Suwaidi", company="Al Suwaidi Residence", email="fatima.suwaidi@example.com", phone="+971 55 222 3333", address="Al Barari, Dubai"),
    dict(name="James Whitfield", company="Whitfield Family Villa", email="j.whitfield@example.com", phone="+971 52 333 4444", address="Jumeirah Golf Estates, Dubai"),
    dict(name="Sara Haddad", company="Haddad Interiors", email="sara@haddadinteriors.ae", phone="+971 4 555 6666", address="Business Bay, Dubai", trn="100234567800003"),
]
customers = [models.Customer(**c) for c in customers_data]
db.add_all(customers)
db.flush()

print("Seeding projects across the pipeline...")
projects_spec = [
    dict(name="Emirates Hills Villa - Full Lighting Package", customer=customers[0],
         site_address="Emirates Hills, Dubai", status=models.ProjectStatus.enquiry,
         start=None, target=None),
    dict(name="Al Barari Residence - Smart Home Retrofit", customer=customers[1],
         site_address="Al Barari, Dubai", status=models.ProjectStatus.quoted,
         start=None, target=None),
    dict(name="Jumeirah Golf Estates - Landscape & Interior Lighting", customer=customers[2],
         site_address="Jumeirah Golf Estates, Dubai", status=models.ProjectStatus.approved,
         start=datetime.utcnow() - timedelta(days=5), target=datetime.utcnow() + timedelta(days=25)),
    dict(name="Haddad Interiors - Showroom Lighting Supply", customer=customers[3],
         site_address="Business Bay, Dubai", status=models.ProjectStatus.ordered,
         start=datetime.utcnow() - timedelta(days=10), target=datetime.utcnow() + timedelta(days=10)),
    dict(name="Al Barari Residence - Villa 12 Home Automation", customer=customers[1],
         site_address="Al Barari, Dubai", status=models.ProjectStatus.installed,
         start=datetime.utcnow() - timedelta(days=40), target=datetime.utcnow() - timedelta(days=5)),
    dict(name="Emirates Hills Villa - Phase 1 (Completed)", customer=customers[0],
         site_address="Emirates Hills, Dubai", status=models.ProjectStatus.closed,
         start=datetime.utcnow() - timedelta(days=90), target=datetime.utcnow() - timedelta(days=30)),
]

STAGE_ORDER = [
    models.ProjectStatus.enquiry, models.ProjectStatus.quoted, models.ProjectStatus.approved,
    models.ProjectStatus.ordered, models.ProjectStatus.delivered, models.ProjectStatus.installed,
    models.ProjectStatus.commissioned, models.ProjectStatus.closed,
]

projects = []
counter = 1
for spec in projects_spec:
    project = models.Project(
        project_number=f"PRJ-{counter:05d}",
        name=spec["name"],
        customer_id=spec["customer"].id,
        site_address=spec["site_address"],
        status=spec["status"],
        start_date=spec["start"],
        target_completion_date=spec["target"],
    )
    db.add(project)
    db.flush()

    # Build a realistic timeline up to the current stage
    reach_idx = STAGE_ORDER.index(spec["status"])
    base_time = datetime.utcnow() - timedelta(days=45)
    for i in range(reach_idx + 1):
        project.status_history.append(models.ProjectStatusHistory(
            status=STAGE_ORDER[i],
            notes="Project created" if i == 0 else f"Moved to {STAGE_ORDER[i].value}",
            changed_at=base_time + timedelta(days=i * 6),
        ))
    projects.append(project)
    counter += 1

db.flush()

print("Seeding quotations...")
quote_lines = [
    (projects[0], customers[0], [("CND-DL-100", 40, 5), ("CND-TR-210", 12, 0), ("CND-PD-330", 4, 10)]),
    (projects[1], customers[1], [("CND-HA-010", 2, 0), ("CND-HA-020", 18, 5), ("CND-HA-025", 6, 0)]),
    (projects[2], customers[2], [("CND-OUT-400", 30, 0), ("CND-DL-101", 60, 8), ("CND-STR-050", 25, 0)]),
    (projects[3], customers[3], [("CND-PD-330", 10, 5), ("CND-DL-100", 80, 10)]),
]
qcounter = 1
for project, customer, lines in quote_lines:
    quote = models.Quotation(
        quote_number=f"QT-{qcounter:05d}",
        customer_id=customer.id,
        project_id=project.id,
        status=models.DocStatus.sent,
        valid_until=datetime.utcnow() + timedelta(days=30),
    )
    for sku, qty, disc in lines:
        p = by_sku[sku]
        quote.items.append(models.QuotationItem(
            product_id=p.id, quantity=qty, unit_price=p.selling_price, discount_pct=disc,
        ))
    db.add(quote)
    qcounter += 1

print("Recording a site stock-out against the installed project...")
db.add(models.StockMovement(
    product_id=by_sku["CND-HA-010"].id, warehouse_id=main_wh.id, project_id=projects[4].id,
    movement_type=models.MovementType.out, quantity=1, reference="Installed at site",
    created_at=datetime.utcnow() - timedelta(days=8),
))
db.add(models.StockMovement(
    product_id=by_sku["CND-HA-020"].id, warehouse_id=main_wh.id, project_id=projects[4].id,
    movement_type=models.MovementType.out, quantity=14, reference="Installed at site",
    created_at=datetime.utcnow() - timedelta(days=8),
))

db.commit()
print("\nDone. Seeded:")
print(f"  {len(products)} products across 2 warehouses")
print(f"  {len(customers)} customers")
print(f"  {len(projects)} projects spanning every pipeline stage")
print(f"  {qcounter - 1} quotations")
db.close()
