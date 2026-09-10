from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, auth, reports
from app.routers.stock import stock_levels

# Reports open through plain browser navigation, so they authenticate with
# the same short-lived download token used for quotations and backups.
router = APIRouter(prefix="/reports", tags=["Reports"])


def _dt(value):
    return value


def _gather(kind: str, db: Session, admin: bool):
    """Returns (title, columns, rows) for a report kind."""

    if kind == "products":
        products = db.query(models.Product).filter(models.Product.is_active == True).order_by(models.Product.sku).all()  # noqa: E712
        columns = [
            {"key": "sku", "label": "SKU"},
            {"key": "name", "label": "Product"},
            {"key": "category", "label": "Category"},
            {"key": "brand", "label": "Brand"},
            {"key": "unit", "label": "Unit"},
            {"key": "selling_price", "label": "Selling price", "kind": "money"},
            {"key": "reorder_level", "label": "Reorder level", "kind": "number"},
        ]
        # Cost is commercially sensitive - admin only, same rule as margins
        if admin:
            columns.insert(5, {"key": "cost_price", "label": "Cost", "kind": "money"})
        rows = [{c["key"]: getattr(p, c["key"]) for c in columns} for p in products]
        return "Product Catalog", columns, rows

    if kind == "stock":
        levels = stock_levels(db)
        columns = [
            {"key": "sku", "label": "SKU"},
            {"key": "name", "label": "Product"},
            {"key": "warehouse_name", "label": "Warehouse"},
            {"key": "quantity_on_hand", "label": "On hand", "kind": "number"},
            {"key": "reorder_level", "label": "Reorder level", "kind": "number"},
            {"key": "status", "label": "Status"},
        ]
        rows = [{
            "sku": l.sku, "name": l.name, "warehouse_name": l.warehouse_name,
            "quantity_on_hand": l.quantity_on_hand, "reorder_level": l.reorder_level,
            "status": "LOW STOCK" if l.below_reorder else "OK",
        } for l in levels]
        return "Stock On Hand", columns, rows

    if kind == "movements":
        movements = (db.query(models.StockMovement)
                     .order_by(models.StockMovement.created_at.desc()).limit(500).all())
        products = {p.id: p for p in db.query(models.Product).all()}
        warehouses = {w.id: w for w in db.query(models.Warehouse).all()}
        projects = {p.id: p for p in db.query(models.Project).all()}
        columns = [
            {"key": "created_at", "label": "Date", "kind": "date"},
            {"key": "sku", "label": "SKU"},
            {"key": "product", "label": "Product"},
            {"key": "warehouse", "label": "Warehouse"},
            {"key": "movement_type", "label": "Type"},
            {"key": "quantity", "label": "Qty", "kind": "number"},
            {"key": "project", "label": "Project"},
            {"key": "reference", "label": "Reference"},
        ]
        rows = []
        for m in movements:
            p = products.get(m.product_id)
            rows.append({
                "created_at": m.created_at,
                "sku": p.sku if p else "",
                "product": p.name if p else "",
                "warehouse": warehouses[m.warehouse_id].name if m.warehouse_id in warehouses else "",
                "movement_type": m.movement_type.value,
                "quantity": m.quantity,
                "project": projects[m.project_id].project_number if m.project_id in projects else "",
                "reference": m.reference or "",
            })
        return "Stock Movements", columns, rows

    if kind == "customers":
        customers = db.query(models.Customer).order_by(models.Customer.name).all()
        columns = [
            {"key": "name", "label": "Name"},
            {"key": "company", "label": "Company"},
            {"key": "email", "label": "Email"},
            {"key": "phone", "label": "Phone"},
            {"key": "trn", "label": "TRN"},
        ]
        rows = [{c["key"]: getattr(c_, c["key"]) for c in columns} for c_ in customers]
        return "Customers", columns, rows

    if kind == "projects":
        projects = db.query(models.Project).order_by(models.Project.created_at.desc()).all()
        customers = {c.id: c for c in db.query(models.Customer).all()}
        columns = [
            {"key": "project_number", "label": "Project #"},
            {"key": "name", "label": "Project"},
            {"key": "customer", "label": "Customer"},
            {"key": "status", "label": "Stage"},
            {"key": "site_address", "label": "Site"},
            {"key": "start_date", "label": "Started", "kind": "date"},
            {"key": "target_completion_date", "label": "Target", "kind": "date"},
        ]
        rows = [{
            "project_number": p.project_number, "name": p.name,
            "customer": customers[p.customer_id].name if p.customer_id in customers else "",
            "status": p.status.value, "site_address": p.site_address,
            "start_date": p.start_date, "target_completion_date": p.target_completion_date,
        } for p in projects]
        return "Projects", columns, rows

    if kind == "quotations":
        quotes = db.query(models.Quotation).order_by(models.Quotation.created_at.desc()).all()
        customers = {c.id: c for c in db.query(models.Customer).all()}
        projects = {p.id: p for p in db.query(models.Project).all()}
        columns = [
            {"key": "quote_number", "label": "Quote #"},
            {"key": "customer", "label": "Customer"},
            {"key": "project", "label": "Project"},
            {"key": "status", "label": "Status"},
            {"key": "total", "label": "Total (incl. VAT)", "kind": "money"},
            {"key": "created_at", "label": "Date", "kind": "date"},
        ]
        if admin:
            columns.insert(5, {"key": "margin", "label": "Profit", "kind": "money"})
        rows = []
        for q in quotes:
            r = {
                "quote_number": q.quote_number,
                "customer": customers[q.customer_id].name if q.customer_id in customers else "",
                "project": projects[q.project_id].project_number if q.project_id in projects else "",
                "status": q.status.value,
                "total": q.total_with_vat,
                "created_at": q.created_at,
            }
            if admin:
                r["margin"] = q.total_margin
            rows.append(r)
        return "Quotations", columns, rows

    if kind == "activity":
        if not admin:
            raise HTTPException(status_code=403, detail="The activity log is admin only.")
        entries = (db.query(models.ActivityLog)
                   .order_by(models.ActivityLog.created_at.desc()).limit(1000).all())
        columns = [
            {"key": "created_at", "label": "Date & time", "kind": "datetime"},
            {"key": "performed_by", "label": "User"},
            {"key": "entity_type", "label": "Area"},
            {"key": "action", "label": "Action"},
            {"key": "entity_label", "label": "Item"},
            {"key": "details", "label": "Details"},
        ]
        rows = [{c["key"]: getattr(e, c["key"]) for c in columns} for e in entries]
        return "Activity Log", columns, rows

    raise HTTPException(status_code=404, detail="Unknown report")


@router.get("/{kind}.{fmt}")
def download_report(kind: str, fmt: str, token: str = Query(...), db: Session = Depends(get_db)):
    if fmt not in ("pdf", "xlsx"):
        raise HTTPException(status_code=404, detail="Format must be pdf or xlsx")

    user = auth.get_download_user_from_token(token, db)
    admin = user.role == "admin"

    title, columns, rows = _gather(kind, db, admin)
    subtitle = f"{len(rows)} record{'' if len(rows) == 1 else 's'} · generated {datetime.utcnow().strftime('%d %b %Y')}"
    stamp = datetime.utcnow().strftime("%Y-%m-%d")
    base = f"candela-{kind}-{stamp}"

    if fmt == "pdf":
        return reports.build_pdf(title, rows, columns, subtitle=subtitle,
                                 landscape=len(columns) > 6, filename=f"{base}.pdf")
    return reports.build_excel(title, rows, columns, subtitle=subtitle, filename=f"{base}.xlsx")
