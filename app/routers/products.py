from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

from app.database import get_db
from app import series as series_opts
from app import models, schemas
from app.utils import save_product_image, log_activity
from app import auth
from app import product_removal
from app import fx
from app import naming


def _standardise(db, data, current_id=None):
    """Name in the shared pattern; SKU made from it when left empty."""
    data["name"] = naming.standard_name(data.get("name"), data.get("brand"), data.get("category"))
    if not (data.get("sku") or "").strip():
        sku = base = naming.standard_sku(data["name"], data.get("brand"), data.get("category"))
        i = 2
        while db.query(models.Product).filter(models.Product.sku == sku, models.Product.id != (current_id or 0)).first():
            sku = f"{base[:60]}-{i}"
            i += 1
        data["sku"] = sku
    else:
        data["sku"] = data["sku"].strip().upper()
    if "series" in data:
        data["series"] = " ".join((data.get("series") or "").split()).upper()[:120] or None
        data["variant"] = " ".join((data.get("variant") or "").split()).upper()[:40] or None
        if not data["series"]:
            data["variant"] = None
    if "options" in data:
        data["options"] = series_opts.clean(data.get("options"))
    return data

router = APIRouter(prefix="/products", tags=["Products"],
                   dependencies=[Depends(auth.get_current_user)])


@router.get("/", response_model=List[schemas.ProductOut])
def list_products(
    category: Optional[str] = None,
    active_only: bool = True,
    db: Session = Depends(get_db),
):
    q = db.query(models.Product)
    if category:
        q = q.filter(models.Product.category == category)
    if active_only:
        q = q.filter(models.Product.is_active == True)  # noqa: E712
    return q.order_by(models.Product.name).all()


@router.post("/", response_model=schemas.ProductOut, status_code=201)
def create_product(payload: schemas.ProductCreate, db: Session = Depends(get_db), current: models.User = Depends(auth.get_current_user)):
    data = _standardise(db, payload.model_dump())
    existing = db.query(models.Product).filter(models.Product.sku == data["sku"]).first()
    if existing:
        raise HTTPException(status_code=400, detail="SKU already exists")
    product = models.Product(**data)
    fx.apply_cost(product, fx.rates(db))
    db.add(product)
    db.flush()
    log_activity(db, current.username, "product", product.id, f"{product.sku} — {product.name}", "created")
    db.commit()
    db.refresh(product)
    return product


@router.get("/{product_id}", response_model=schemas.ProductOut)
def get_product(product_id: int, db: Session = Depends(get_db)):
    product = db.query(models.Product).get(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.put("/{product_id}", response_model=schemas.ProductOut)
def update_product(product_id: int, payload: schemas.ProductCreate, db: Session = Depends(get_db), current: models.User = Depends(auth.get_current_user)):
    product = db.query(models.Product).get(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    data = payload.model_dump()
    data["brand"] = data.get("brand")
    data = _standardise(db, data, current_id=product_id)
    clash = db.query(models.Product).filter(models.Product.sku == data["sku"], models.Product.id != product_id).first()
    if clash:
        raise HTTPException(status_code=400, detail="SKU already used by " + clash.name)
    for key in ("product_type", "description", "features", "series", "variant", "options"):
        if key not in payload.model_fields_set:
            data.pop(key)  # not sent (no longer / not on that form): keep what's stored
    for key, value in data.items():
        setattr(product, key, value)
    fx.apply_cost(product, fx.rates(db))
    log_activity(db, current.username, "product", product.id, f"{product.sku} — {product.name}", "updated")
    db.commit()
    db.refresh(product)
    return product


DATASHEET_MODES = ("halo", "supplier", "none")


@router.put("/{product_id}/datasheet-mode")
def set_datasheet_mode(product_id: int, mode: str, db: Session = Depends(get_db),
                       current: models.User = Depends(auth.get_current_user)):
    """Uploaded PDF (supplier) / HALO made automatically (halo) / Not needed (none)."""
    if mode not in DATASHEET_MODES:
        raise HTTPException(status_code=400, detail="Choose halo, supplier or none")
    product = db.query(models.Product).get(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    product.datasheet_mode = mode
    product.no_datasheet = mode == "none"
    log_activity(db, current.username, "product", product.id, f"{product.sku} — {product.name}", "updated",
                 {"halo": "datasheet: HALO (automatic)", "supplier": "datasheet: uploaded PDF",
                  "none": "datasheet: not needed"}[mode])
    db.commit()
    return {"datasheet_mode": product.datasheet_mode}


@router.post("/from-datasheet")
def read_datasheet(file: UploadFile = File(...)):
    """Read a datasheet PDF to fill the new-product form: model, brand,
    category, spec rows, the versions it lists and its main photo. Nothing is
    saved here - the form is saved as usual, then the PDF attached."""
    data = file.file.read(60 * 1024 * 1024 + 1)
    if len(data) > 60 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="That PDF is over 60 MB")
    if not data.lstrip()[:5].startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="That isn't a PDF file")
    from app.datasheet_read import read
    try:
        return read(data, file.filename or "")
    except Exception:
        raise HTTPException(status_code=400, detail="Couldn't read that PDF - fill the form by hand")


@router.post("/bulk-delete/check")
def bulk_delete_check(payload: schemas.IdsIn, db: Session = Depends(get_db),
                      current: models.User = Depends(auth.require_admin)):
    """What deleting these products would touch, shown before confirming."""
    ids = [p.id for p in db.query(models.Product).filter(models.Product.id.in_(payload.ids)).all()]
    return product_removal.impact(db, ids)


@router.post("/bulk-delete")
def bulk_delete(payload: schemas.IdsIn, db: Session = Depends(get_db),
                current: models.User = Depends(auth.require_admin)):
    """Deletes the ticked products for good (admin only). Quotation and order
    lines keep their text; stock records and datasheets go with them."""
    products = db.query(models.Product).filter(models.Product.id.in_(payload.ids)).all()
    if not products:
        raise HTTPException(status_code=400, detail="Nothing selected.")
    n = product_removal.remove_products(db, products, current.username, "deleted with others (bulk)")
    db.commit()
    return {"deleted": n}


@router.delete("/{product_id}", status_code=204)
def deactivate_product(product_id: int, db: Session = Depends(get_db), current: models.User = Depends(auth.get_current_user)):
    product = db.query(models.Product).get(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    product.is_active = False
    log_activity(db, current.username, "product", product.id, f"{product.sku} — {product.name}", "deleted")
    db.commit()
    return None


@router.post("/{product_id}/image", response_model=schemas.ProductOut)
def upload_product_image(product_id: int, file: UploadFile = File(...), db: Session = Depends(get_db), current: models.User = Depends(auth.get_current_user)):
    product = db.query(models.Product).get(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    product.image_path = save_product_image(file)
    log_activity(db, current.username, "product", product.id, f"{product.sku} — {product.name}", "updated", "Photo changed")
    db.commit()
    db.refresh(product)
    return product


@router.get("/{product_id}/usage")
def product_usage(product_id: int, db: Session = Depends(get_db)):
    """Stock by warehouse, what open jobs still need, and where it's been quoted."""
    from app import workflow
    product = db.query(models.Product).get(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    stock = []
    for wh in db.query(models.Warehouse).order_by(models.Warehouse.name).all():
        qty = workflow.on_hand(db, product_id, wh.id)
        if qty or any(m.warehouse_id == wh.id for m in product.stock_movements):
            stock.append({"warehouse": wh.name, "on_hand": qty})
    total = sum(s["on_hand"] for s in stock)

    reserved = []
    for p in db.query(models.Project).filter(models.Project.status != models.ProjectStatus.closed).all():
        gq = workflow.governing_quotation(p)
        if not gq or gq.status != models.DocStatus.accepted:
            continue
        if not any(i.product_id == product_id for i in gq.items):
            continue
        row = next((r for r in workflow.project_materials(db, p)["rows"] if r["product_id"] == product_id), None)
        if row and row["balance"]:
            reserved.append({"project_id": p.id, "project_number": p.project_number, "name": p.name, "qty": row["balance"]})
    reserved_total = sum(r["qty"] for r in reserved)

    quotes = []
    rows = (db.query(models.QuotationItem).filter(models.QuotationItem.product_id == product_id)
            .join(models.Quotation).order_by(models.Quotation.created_at.desc()).limit(15).all())
    for it in rows:
        q = it.quotation
        quotes.append({"id": q.id, "quote_number": q.quote_number, "status": q.status.value,
                       "customer": q.customer.name if q.customer else "", "quantity": it.quantity,
                       "unit_price": it.unit_price, "created_at": q.created_at.isoformat()})

    return {"stock": stock, "on_hand": total, "reserved": reserved, "reserved_total": reserved_total,
            "available": total - reserved_total, "reorder_level": product.reorder_level or 0,
            "quotations": quotes}
