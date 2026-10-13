"""
Supplier orders (purchase orders): everything from placing an order with a
supplier to handing the goods over to the client.

    ordered -> ready at supplier -> shipped -> arrived -> customs cleared
            -> received into stock -> delivered to client

The stage follows the dates filled in, so nobody has to remember to move it.
Receiving books product lines into stock; delivering issues them from stock
to the project (which moves the project to Delivered once everything on its
quotation has gone to site).
"""
import re
from collections import OrderedDict
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import auth, models, schemas, workflow
from app.database import get_db
from app.utils import log_activity

router = APIRouter(prefix="/orders", tags=["Supplier orders"],
                   dependencies=[Depends(auth.get_current_user)])

HEADER_FIELDS = [
    "supplier_ref", "project_id", "order_date", "expected_date", "notes",
    "payment_terms", "advance_paid_date", "balance_paid_date", "ready_expected", "ready_date",
    "ship_mode", "incoterm", "forwarder", "tracking_no", "dispatch_date", "arrived_date",
    "customs_agent", "customs_ref", "cleared_date", "delivery_planned", "delivered_date",
    "delivery_note", "delivered_to",
]


def _label(po):
    return f"{po.po_number} — {po.supplier}"


def _next_po_number(db: Session) -> str:
    """Next PO number after the highest ever issued (never reused)."""
    highest = 0
    for (num,) in db.query(models.PurchaseOrder.po_number).all():
        m = re.match(r"PO-(\d+)", num or "")
        if m:
            highest = max(highest, int(m.group(1)))
    return f"PO-{highest + 1:05d}"


def _get(db, order_id) -> models.PurchaseOrder:
    po = db.query(models.PurchaseOrder).get(order_id)
    if not po:
        raise HTTPException(status_code=404, detail="Order not found")
    return po


def _restage(po):
    """Keep the stored stage in step with the dates and quantities."""
    po.status = po.derive_status()
    if po.status in ("received", "delivered") and not po.received_date and po.qty_received >= po.qty_ordered:
        po.received_date = datetime.utcnow()


def _check_refs(db, payload):
    if not payload.supplier.strip():
        raise HTTPException(status_code=400, detail="Enter the supplier.")
    if not payload.items:
        raise HTTPException(status_code=400, detail="Add at least one line.")
    if payload.project_id and not db.query(models.Project).get(payload.project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    for it in payload.items:
        if it.quantity <= 0:
            raise HTTPException(status_code=400, detail="Every line needs a quantity above zero.")
        if it.product_id and not db.query(models.Product).get(it.product_id):
            raise HTTPException(status_code=400, detail="A line's product no longer exists.")
        if not it.product_id and not (it.description or "").strip():
            raise HTTPException(status_code=400, detail="A line without a product needs a description.")


def _apply_header(po, payload):
    po.supplier = payload.supplier.strip()
    for f in HEADER_FIELDS:
        v = getattr(payload, f)
        if isinstance(v, str):
            v = v.strip() or None
        setattr(po, f, v)
    po.currency = (payload.currency or "AED").strip()[:8] or "AED"
    if payload.cancelled:
        po.status = "cancelled"
    elif po.status == "cancelled":
        po.status = "draft"  # re-opened; _restage works out the real stage


@router.get("/", response_model=List[schemas.PurchaseOrderOut])
def list_orders(project_id: Optional[int] = None, quotation_id: Optional[int] = None, db: Session = Depends(get_db)):
    q = db.query(models.PurchaseOrder)
    if project_id:
        q = q.filter(models.PurchaseOrder.project_id == project_id)
    if quotation_id:
        q = q.filter(models.PurchaseOrder.quotation_id == quotation_id)
    return q.order_by(models.PurchaseOrder.created_at.desc(), models.PurchaseOrder.id.desc()).all()


@router.get("/suppliers")
def suppliers(db: Session = Depends(get_db)):
    """Supplier names used before (and product brands), for the type-ahead."""
    names = sorted({r[0] for r in db.query(models.PurchaseOrder.supplier).distinct().all() if r[0]}, key=str.lower)
    seen = {n.lower() for n in names}
    brands = sorted({b for (b,) in db.query(models.Product.brand).distinct().all() if b and b.lower() not in seen})
    return names + brands


@router.get("/from-project/{project_id}")
def lines_from_project(project_id: int, db: Session = Depends(get_db)):
    """Lines to order for a project: what its quotation needs and stock
    can't cover, plus its custom lines (things never kept in stock)."""
    project = db.query(models.Project).get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    quote = workflow.governing_quotation(project)
    if not quote:
        return {"quotation": None, "lines": []}
    mats = workflow.project_materials(db, project)
    costs = {}
    for it in quote.items:
        if it.product_id and it.unit_cost:
            costs.setdefault(it.product_id, it.unit_cost)
    lines = []
    for r in mats["rows"]:
        if r["shortfall"] > 0:
            prod = db.query(models.Product).get(r["product_id"])
            lines.append({"product_id": r["product_id"], "description": f"{r['sku']} — {r['name']}",
                          "quantity": r["shortfall"],
                          "unit_cost": costs.get(r["product_id"], prod.cost_price if prod else 0.0)})
    for it in quote.items:
        if not getattr(it, "product_id", None):
            lines.append({"product_id": None, "description": _line_text(it), "quantity": it.quantity,
                          "unit_cost": it.unit_cost or 0.0})
    return {"quotation": quote.quote_number, "lines": lines}


# ---------- splitting a client quotation into supplier orders ----------

def _line_text(it):
    """Short order-line text from a quotation line: type code, product, key spec."""
    desc = [l.strip() for l in (it.description or "").split("\n") if l.strip()]
    keep = [l for l in desc if not l.lower().startswith(("brand:", "location:", "warranty:"))]
    head = f"{it.product.sku} — {it.product.name}" if getattr(it, "product", None) else ""
    parts = [p for p in [it.type_code, head] + keep[:4] if p]
    return " · ".join(parts)[:500]


# Candela's own brands: made by different suppliers (local or China), so the
# brand says nothing about who to order from.
OWN_BRANDS = ("HALO", "RUHA")
OWN_BRAND_SUPPLIER = "HALO - supplier to confirm (local / China)"


def _supplier_of(it):
    prod = getattr(it, "product", None)
    if prod is not None and prod.supplier:
        return prod.supplier.strip()
    brand = prod.brand if prod is not None and prod.brand else None
    if not brand:
        for l in (it.description or "").split("\n"):
            m = re.match(r"\s*Brand\s*:\s*(.+)", l, re.I)
            if m:
                brand = m.group(1).strip()
                break
    if not brand:
        return "Supplier to confirm"
    if re.sub(r"[^A-Z]", " ", brand.upper()).split()[0] in OWN_BRANDS:
        return OWN_BRAND_SUPPLIER
    return brand.strip()


@router.post("/from-quotation/{quotation_id}", response_model=List[schemas.PurchaseOrderOut], status_code=201)
def orders_from_quotation(quotation_id: int, db: Session = Depends(get_db),
                          current: models.User = Depends(auth.get_current_user)):
    """One draft order per supplier with every line of the quotation, so the
    whole job can be ordered in one go. Quantities include spares as quoted;
    costs come from the quotation's cost snapshot."""
    quote = db.query(models.Quotation).get(quotation_id)
    if not quote:
        raise HTTPException(status_code=404, detail="Quotation not found")
    groups = OrderedDict()
    for it in quote.items:
        groups.setdefault(_supplier_of(it), []).append(it)
    created = []
    for supplier, lines in groups.items():
        po = models.PurchaseOrder(po_number=_next_po_number(db), supplier=supplier, status="draft",
                                  project_id=quote.project_id, quotation_id=quote.id, currency="AED",
                                  notes=f"From quotation {quote.quote_number}")
        for it in lines:
            po.items.append(models.PurchaseOrderItem(
                product_id=getattr(it, "product_id", None), description=_line_text(it), quantity=it.quantity,
                unit_cost=it.unit_cost or 0.0, received_qty=0, delivered_qty=0))
        db.add(po)
        db.flush()
        log_activity(db, current.username, "order", po.id, _label(po), "created",
                     f"from {quote.quote_number} · {len(lines)} line{'s' if len(lines) != 1 else ''}")
        created.append(po)
    db.commit()
    for po in created:
        db.refresh(po)
    return created


# ---------- create / edit ----------

@router.post("/", response_model=schemas.PurchaseOrderOut, status_code=201)
def create_order(payload: schemas.PurchaseOrderIn, db: Session = Depends(get_db),
                 current: models.User = Depends(auth.get_current_user)):
    _check_refs(db, payload)
    po = models.PurchaseOrder(po_number=_next_po_number(db), status="draft")
    _apply_header(po, payload)
    for it in payload.items:
        po.items.append(models.PurchaseOrderItem(
            product_id=it.product_id, description=it.description, quantity=it.quantity,
            unit_cost=it.unit_cost or 0.0, received_qty=0, delivered_qty=0))
    db.add(po)
    db.flush()
    _restage(po)
    log_activity(db, current.username, "order", po.id, _label(po), "created",
                 f"{len(po.items)} line{'s' if len(po.items) != 1 else ''}")
    db.commit()
    db.refresh(po)
    return po


@router.get("/{order_id}", response_model=schemas.PurchaseOrderOut)
def get_order(order_id: int, db: Session = Depends(get_db)):
    return _get(db, order_id)


@router.put("/{order_id}", response_model=schemas.PurchaseOrderOut)
def update_order(order_id: int, payload: schemas.PurchaseOrderIn, db: Session = Depends(get_db),
                 current: models.User = Depends(auth.get_current_user)):
    po = _get(db, order_id)
    _check_refs(db, payload)
    if payload.cancelled and po.qty_received:
        raise HTTPException(status_code=400, detail="Goods have already been received on this order, so it can't be cancelled.")
    existing = {i.id: i for i in po.items}
    keep_ids = {it.id for it in payload.items if it.id in existing}
    for i in po.items:
        if i.id not in keep_ids and ((i.received_qty or 0) > 0 or (i.delivered_qty or 0) > 0):
            raise HTTPException(status_code=400, detail="A line that has had goods received can't be removed.")
    for it in payload.items:
        if it.id in existing:
            floor = max(existing[it.id].received_qty or 0, existing[it.id].delivered_qty or 0)
            if it.quantity < floor:
                raise HTTPException(status_code=400, detail=f"A line can't be set below the {floor} already received.")

    old_stage = po.status
    _apply_header(po, payload)
    for i in list(po.items):
        if i.id not in keep_ids:
            po.items.remove(i)
    for it in payload.items:
        if it.id in existing:
            line = existing[it.id]
            if not (line.received_qty or line.delivered_qty):
                line.product_id = it.product_id
            line.description, line.quantity, line.unit_cost = it.description, it.quantity, it.unit_cost or 0.0
        else:
            po.items.append(models.PurchaseOrderItem(
                product_id=it.product_id, description=it.description, quantity=it.quantity,
                unit_cost=it.unit_cost or 0.0, received_qty=0, delivered_qty=0))
    db.flush()
    _restage(po)
    detail = None if po.status == old_stage else f"now {po.status}"
    log_activity(db, current.username, "order", po.id, _label(po), "updated", detail)
    db.commit()
    db.refresh(po)
    return po


@router.post("/{order_id}/status/{action}", response_model=schemas.PurchaseOrderOut)
def quick_status(order_id: int, action: str, db: Session = Depends(get_db),
                 current: models.User = Depends(auth.get_current_user)):
    """One-click steps: place (sets today's order date), cancel, reopen."""
    po = _get(db, order_id)
    old = po.status
    if action == "ordered":
        po.order_date = po.order_date or datetime.utcnow()
    elif action == "cancelled":
        if po.qty_received:
            raise HTTPException(status_code=400, detail="Goods have already been received on this order, so it can't be cancelled.")
        po.status = "cancelled"
    elif action == "reopen":
        if po.status == "cancelled":
            po.status = "draft"
    else:
        raise HTTPException(status_code=400, detail="Unknown action")
    if po.status != "cancelled":
        _restage(po)
    log_activity(db, current.username, "order", po.id, _label(po), "status_changed",
                 f"{old} → {po.status}" if old != po.status else po.status)
    db.commit()
    db.refresh(po)
    return po


# ---------- goods in / goods out ----------

def _apply_lines(po, lines, field, cap_field=None):
    items = {i.id: i for i in po.items}
    done = []
    for rl in lines:
        if rl.quantity == 0:
            continue
        line = items.get(rl.item_id)
        if not line:
            raise HTTPException(status_code=400, detail="That line isn't on this order.")
        limit = (getattr(line, cap_field) or 0) if cap_field else line.quantity
        remaining = limit - (getattr(line, field) or 0)
        if rl.quantity < 0 or rl.quantity > remaining:
            raise HTTPException(status_code=400, detail=f"Only {max(0, remaining)} left on one of the lines.")
        done.append((line, rl.quantity))
    if not done:
        raise HTTPException(status_code=400, detail="Enter a quantity on at least one line.")
    return done


@router.post("/{order_id}/receive", response_model=schemas.PurchaseOrderOut)
def receive(order_id: int, payload: schemas.ReceiveIn, db: Session = Depends(get_db),
            current: models.User = Depends(auth.get_current_user)):
    """Goods arrived at our warehouse. Product lines are booked into stock;
    other lines are just ticked off."""
    po = _get(db, order_id)
    if po.status == "cancelled":
        raise HTTPException(status_code=400, detail="This order is cancelled.")
    done = _apply_lines(po, payload.lines, "received_qty")
    warehouse = db.query(models.Warehouse).get(payload.warehouse_id) if payload.warehouse_id else None
    if any(line.product_id for line, _ in done) and not warehouse:
        raise HTTPException(status_code=400, detail="Choose the warehouse the goods went into.")
    for line, qty in done:
        line.received_qty = (line.received_qty or 0) + qty
        if line.product_id:
            db.add(models.StockMovement(
                product_id=line.product_id, warehouse_id=warehouse.id,
                movement_type=models.MovementType.in_, quantity=qty,
                reference=f"{po.po_number} · {po.supplier}"[:255], notes=payload.notes))
    db.flush()
    po.order_date = po.order_date or datetime.utcnow()
    if po.qty_received >= po.qty_ordered:
        po.received_date = datetime.utcnow()
    _restage(po)
    total = sum(q for _, q in done)
    log_activity(db, current.username, "order", po.id, _label(po), "received",
                 f"{total} received" + (f" into {warehouse.name}" if warehouse else "")
                 + (" · all received" if po.qty_received >= po.qty_ordered else ""))
    db.commit()
    db.refresh(po)
    return po


@router.post("/{order_id}/deliver", response_model=schemas.PurchaseOrderOut)
def deliver(order_id: int, payload: schemas.DeliverIn, db: Session = Depends(get_db),
            current: models.User = Depends(auth.get_current_user)):
    """Goods handed over to the client / site. Product lines are issued from
    stock to the order's project; other lines are just ticked off. For an
    order the supplier sends straight to site, nothing has to be received
    first."""
    po = _get(db, order_id)
    if po.status == "cancelled":
        raise HTTPException(status_code=400, detail="This order is cancelled.")
    direct = po.ship_mode == "direct"
    done = _apply_lines(po, payload.lines, "delivered_qty", None if direct else "received_qty")
    stock_lines = [(l, q) for l, q in done if l.product_id and not direct]
    warehouse = db.query(models.Warehouse).get(payload.warehouse_id) if payload.warehouse_id else None
    if stock_lines and not warehouse:
        raise HTTPException(status_code=400, detail="Choose the warehouse the goods go out from.")
    for line, qty in stock_lines:
        available = workflow.on_hand(db, line.product_id, warehouse.id)
        if qty > available:
            prod = db.query(models.Product).get(line.product_id)
            raise HTTPException(status_code=400, detail=f"Only {available} of {prod.sku if prod else 'that product'} in {warehouse.name}.")
    ref = " · ".join(filter(None, [po.po_number, payload.delivery_note and f"DN {payload.delivery_note}"]))
    for line, qty in done:
        line.delivered_qty = (line.delivered_qty or 0) + qty
    for line, qty in stock_lines:
        db.add(models.StockMovement(
            product_id=line.product_id, warehouse_id=warehouse.id, project_id=po.project_id,
            movement_type=models.MovementType.out, quantity=qty, reference=ref[:255],
            notes=f"Delivered to {payload.delivered_to}" if payload.delivered_to else None))
    if payload.delivery_note:
        po.delivery_note = payload.delivery_note.strip()[:120]
    if payload.delivered_to:
        po.delivered_to = payload.delivered_to.strip()[:255]
    db.flush()
    if po.qty_delivered >= po.qty_ordered:
        po.delivered_date = payload.date or datetime.utcnow()
    _restage(po)
    if po.project is not None and stock_lines:
        workflow.check_delivery_complete(db, po.project, current.username)
    total = sum(q for _, q in done)
    log_activity(db, current.username, "order", po.id, _label(po), "delivered",
                 f"{total} delivered to client" + (f" · DN {payload.delivery_note}" if payload.delivery_note else "")
                 + (" · all delivered" if po.status == "delivered" else ""))
    db.commit()
    db.refresh(po)
    return po


@router.delete("/{order_id}", status_code=204)
def delete_order(order_id: int, db: Session = Depends(get_db),
                 current: models.User = Depends(auth.get_current_user)):
    po = _get(db, order_id)
    if po.qty_received or po.qty_delivered:
        raise HTTPException(status_code=400, detail="Goods have been received on this order, so it's kept for the record.")
    log_activity(db, current.username, "order", po.id, _label(po), "deleted")
    db.delete(po)
    db.commit()
    return None
