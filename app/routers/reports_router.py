from datetime import datetime
from typing import Optional

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


CATEGORY_LABELS = {"retail": "Retail", "residential": "Residential"}


def _gather(kind: str, db: Session, admin: bool, category: Optional[str] = None):
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
        q = db.query(models.Project)
        if category:
            q = q.filter(models.Project.category == category)
        projects = q.order_by(models.Project.created_at.desc()).all()
        customers = {c.id: c for c in db.query(models.Customer).all()}
        columns = [
            {"key": "project_number", "label": "Project #"},
            {"key": "name", "label": "Project"},
            {"key": "customer", "label": "Customer"},
            {"key": "category", "label": "Category"},
            {"key": "status", "label": "Stage"},
            {"key": "site_address", "label": "Site"},
            {"key": "start_date", "label": "Started", "kind": "date"},
            {"key": "target_completion_date", "label": "Target", "kind": "date"},
        ]
        rows = [{
            "project_number": p.project_number, "name": p.name,
            "customer": customers[p.customer_id].name if p.customer_id in customers else "",
            "category": CATEGORY_LABELS.get(p.category, ""),
            "status": p.status.value, "site_address": p.site_address,
            "start_date": p.start_date, "target_completion_date": p.target_completion_date,
        } for p in projects]
        title = f"Projects - {CATEGORY_LABELS[category]}" if category else "Projects"
        return title, columns, rows

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

    if kind == "datasheets":
        sheets = db.query(models.Datasheet).order_by(models.Datasheet.uploaded_at.desc()).all()
        products = {p.id: p for p in db.query(models.Product).all()}
        columns = [
            {"key": "title", "label": "Title"},
            {"key": "brand", "label": "Brand"},
            {"key": "category", "label": "Category"},
            {"key": "product", "label": "Linked product"},
            {"key": "original_filename", "label": "File"},
            {"key": "uploaded_at", "label": "Uploaded", "kind": "date"},
        ]
        rows = [{
            "title": d.title, "brand": d.brand, "category": d.category,
            "product": (f"{products[d.product_id].sku} - {products[d.product_id].name}"
                        if d.product_id in products else ""),
            "original_filename": d.original_filename, "uploaded_at": d.uploaded_at,
        } for d in sheets]
        return "Datasheets", columns, rows

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


def _check_fmt(fmt):
    if fmt not in ("pdf", "xlsx"):
        raise HTTPException(status_code=404, detail="Format must be pdf or xlsx")


def _record(fmt, title, subtitle, details, sections, base, preview):
    if fmt == "pdf":
        return reports.build_record_pdf(title, subtitle=subtitle, details=details, sections=sections,
                                        filename=f"{base}.pdf", inline=preview)
    return reports.build_record_excel(title, subtitle=subtitle, details=details, sections=sections,
                                      filename=f"{base}.xlsx")


def _today():
    return datetime.utcnow().strftime("%d %b %Y")


# ---------- One project ----------
@router.get("/project/{project_id}.{fmt}")
def project_report(project_id: int, fmt: str, token: str = Query(...), preview: bool = False,
                   db: Session = Depends(get_db)):
    _check_fmt(fmt)
    user = auth.get_download_user_from_token(token, db)
    admin = user.role == "admin"
    p = db.query(models.Project).get(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")

    details = [
        ("Project #", p.project_number),
        ("Customer", p.customer.name if p.customer else ""),
        ("Company", p.customer.company if p.customer else ""),
        ("Category", CATEGORY_LABELS.get(p.category, "Not set")),
        ("Stage", p.status.value.capitalize()),
        ("Site address", p.site_address),
        ("Started", reports._fmt(p.start_date, "date")),
        ("Target completion", reports._fmt(p.target_completion_date, "date")),
        ("Notes", p.notes),
    ]

    q_cols = [
        {"key": "quote_number", "label": "Quote #"},
        {"key": "status", "label": "Status"},
        {"key": "total", "label": "Total (incl. VAT)", "kind": "money"},
        {"key": "created_at", "label": "Date", "kind": "date"},
    ]
    if admin:
        q_cols.insert(3, {"key": "margin", "label": "Profit", "kind": "money"})
    quotes = sorted(p.quotations, key=lambda q: q.created_at or datetime.min, reverse=True)
    q_rows = [{"quote_number": q.quote_number, "status": q.status.value, "total": q.total_with_vat,
               "margin": q.total_margin, "created_at": q.created_at} for q in quotes]

    products = {x.id: x for x in db.query(models.Product).all()}
    warehouses = {w.id: w for w in db.query(models.Warehouse).all()}
    m_cols = [
        {"key": "created_at", "label": "Date", "kind": "date"},
        {"key": "product", "label": "Product"},
        {"key": "warehouse", "label": "Warehouse"},
        {"key": "movement_type", "label": "Type"},
        {"key": "quantity", "label": "Qty", "kind": "number"},
        {"key": "reference", "label": "Reference"},
    ]
    moves = sorted(p.stock_movements, key=lambda m: m.created_at or datetime.min, reverse=True)
    m_rows = [{
        "created_at": m.created_at,
        "product": (f"{products[m.product_id].sku} - {products[m.product_id].name}" if m.product_id in products else ""),
        "warehouse": warehouses[m.warehouse_id].name if m.warehouse_id in warehouses else "",
        "movement_type": m.movement_type.value, "quantity": m.quantity, "reference": m.reference,
    } for m in moves]

    t_cols = [
        {"key": "changed_at", "label": "Date & time", "kind": "datetime"},
        {"key": "status", "label": "Stage"},
        {"key": "notes", "label": "Notes"},
    ]
    t_rows = [{"changed_at": h.changed_at, "status": h.status.value.capitalize(), "notes": h.notes}
              for h in p.status_history]

    sections = [
        {"title": "Linked quotations", "columns": q_cols, "rows": q_rows, "empty": "No quotations linked to this project yet."},
        {"title": "Stock movements for this site", "columns": m_cols, "rows": m_rows, "empty": "No stock recorded against this project yet."},
        {"title": "Timeline", "columns": t_cols, "rows": t_rows, "empty": "No status changes yet."},
    ]
    base = f"candela-{(p.project_number or 'project').lower()}-{datetime.utcnow().strftime('%Y-%m-%d')}"
    return _record(fmt, f"{p.project_number} - {p.name}", f"Project summary · generated {_today()}",
                   details, sections, base, preview)


# ---------- One product ----------
@router.get("/product/{product_id}.{fmt}")
def product_report(product_id: int, fmt: str, token: str = Query(...), preview: bool = False,
                   db: Session = Depends(get_db)):
    _check_fmt(fmt)
    user = auth.get_download_user_from_token(token, db)
    admin = user.role == "admin"
    p = db.query(models.Product).get(product_id)
    if not p:
        raise HTTPException(status_code=404, detail="Product not found")

    details = [
        ("SKU", p.sku),
        ("Category", p.category),
        ("Brand", p.brand),
        ("Unit", p.unit),
        ("Selling price", reports._fmt(p.selling_price, "money")),
    ]
    if admin:  # cost is admin-only, same rule as everywhere else
        details.append(("Cost", reports._fmt(p.cost_price, "money")))
    details += [
        ("Reorder level", p.reorder_level),
        ("Specification", p.spec_summary),
    ]

    levels = [l for l in stock_levels(db) if l.product_id == p.id]
    s_cols = [
        {"key": "warehouse_name", "label": "Warehouse"},
        {"key": "quantity_on_hand", "label": "On hand", "kind": "number"},
        {"key": "status", "label": "Status"},
    ]
    s_rows = [{"warehouse_name": l.warehouse_name, "quantity_on_hand": l.quantity_on_hand,
               "status": "LOW STOCK" if l.below_reorder else "OK"} for l in levels]

    d_cols = [
        {"key": "title", "label": "Datasheet"},
        {"key": "brand", "label": "Brand"},
        {"key": "original_filename", "label": "File"},
        {"key": "uploaded_at", "label": "Uploaded", "kind": "date"},
    ]
    d_rows = [{"title": d.title, "brand": d.brand, "original_filename": d.original_filename,
               "uploaded_at": d.uploaded_at} for d in p.datasheets]

    warehouses = {w.id: w for w in db.query(models.Warehouse).all()}
    projects = {x.id: x for x in db.query(models.Project).all()}
    m_cols = [
        {"key": "created_at", "label": "Date", "kind": "date"},
        {"key": "warehouse", "label": "Warehouse"},
        {"key": "movement_type", "label": "Type"},
        {"key": "quantity", "label": "Qty", "kind": "number"},
        {"key": "project", "label": "Project"},
        {"key": "reference", "label": "Reference"},
    ]
    moves = (db.query(models.StockMovement).filter(models.StockMovement.product_id == p.id)
             .order_by(models.StockMovement.created_at.desc()).limit(200).all())
    m_rows = [{
        "created_at": m.created_at,
        "warehouse": warehouses[m.warehouse_id].name if m.warehouse_id in warehouses else "",
        "movement_type": m.movement_type.value, "quantity": m.quantity,
        "project": projects[m.project_id].project_number if m.project_id in projects else "",
        "reference": m.reference,
    } for m in moves]

    sections = [
        {"title": "Stock on hand", "columns": s_cols, "rows": s_rows, "empty": "No stock recorded for this product yet."},
        {"title": "Datasheets", "columns": d_cols, "rows": d_rows, "empty": "No datasheets attached."},
        {"title": "Recent stock movements", "columns": m_cols, "rows": m_rows, "empty": "No stock movements yet."},
    ]
    base = f"candela-{p.sku.lower()}-{datetime.utcnow().strftime('%Y-%m-%d')}"
    return _record(fmt, f"{p.sku} - {p.name}", f"Product sheet · generated {_today()}",
                   details, sections, base, preview)


# ---------- Dashboard summary ----------
@router.get("/dashboard.{fmt}")
def dashboard_report(fmt: str, token: str = Query(...), preview: bool = False, db: Session = Depends(get_db)):
    _check_fmt(fmt)
    auth.get_download_user_from_token(token, db)

    projects = db.query(models.Project).all()
    levels = stock_levels(db)
    low = [l for l in levels if l.below_reorder]
    open_quotes = [q for q in db.query(models.Quotation).all() if q.status.value in ("draft", "sent")]

    details = [
        ("Projects", len(projects)),
        ("Retail projects", sum(1 for p in projects if p.category == "retail")),
        ("Residential projects", sum(1 for p in projects if p.category == "residential")),
        ("Quotations", db.query(models.Quotation).count()),
        ("Open quotations (draft / sent)", f"{len(open_quotes)} · {reports._fmt(sum(q.total_with_vat for q in open_quotes), 'money')} incl. VAT"),
        ("Active products", db.query(models.Product).filter(models.Product.is_active == True).count()),  # noqa: E712
        ("Low stock lines", len(low)),
    ]

    stages = [s for s in models.ProjectStatus]
    p_cols = [
        {"key": "stage", "label": "Stage"},
        {"key": "retail", "label": "Retail", "kind": "number"},
        {"key": "residential", "label": "Residential", "kind": "number"},
        {"key": "unset", "label": "Not set", "kind": "number"},
        {"key": "total", "label": "Total", "kind": "number"},
    ]
    p_rows = []
    for st in stages:
        here = [p for p in projects if p.status == st]
        p_rows.append({
            "stage": st.value.capitalize(),
            "retail": sum(1 for p in here if p.category == "retail"),
            "residential": sum(1 for p in here if p.category == "residential"),
            "unset": sum(1 for p in here if not p.category),
            "total": len(here),
        })

    l_cols = [
        {"key": "sku", "label": "SKU"},
        {"key": "name", "label": "Product"},
        {"key": "warehouse_name", "label": "Warehouse"},
        {"key": "quantity_on_hand", "label": "On hand", "kind": "number"},
        {"key": "reorder_level", "label": "Reorder level", "kind": "number"},
    ]
    l_rows = [{"sku": l.sku, "name": l.name, "warehouse_name": l.warehouse_name,
               "quantity_on_hand": l.quantity_on_hand, "reorder_level": l.reorder_level} for l in low]

    sections = [
        {"title": "Pipeline by stage", "columns": p_cols, "rows": p_rows},
        {"title": "Low stock", "columns": l_cols, "rows": l_rows, "empty": "Nothing is below its reorder level."},
    ]
    base = f"candela-dashboard-{datetime.utcnow().strftime('%Y-%m-%d')}"
    return _record(fmt, "Dashboard Summary", f"Generated {_today()}", details, sections, base, preview)


# ---------- Every list page ----------
@router.get("/{kind}.{fmt}")
def download_report(kind: str, fmt: str, token: str = Query(...), preview: bool = False,
                    category: Optional[str] = None, db: Session = Depends(get_db)):
    _check_fmt(fmt)
    if category is not None and category not in CATEGORY_LABELS:
        raise HTTPException(status_code=400, detail="Category must be retail or residential")

    user = auth.get_download_user_from_token(token, db)
    admin = user.role == "admin"

    title, columns, rows = _gather(kind, db, admin, category)
    subtitle = f"{len(rows)} record{'' if len(rows) == 1 else 's'} · generated {datetime.utcnow().strftime('%d %b %Y')}"
    stamp = datetime.utcnow().strftime("%Y-%m-%d")
    base = f"candela-{kind}-{category}-{stamp}" if category else f"candela-{kind}-{stamp}"

    if fmt == "pdf":
        return reports.build_pdf(title, rows, columns, subtitle=subtitle,
                                 landscape=len(columns) > 6, filename=f"{base}.pdf", inline=preview)
    return reports.build_excel(title, rows, columns, subtitle=subtitle, filename=f"{base}.xlsx")
