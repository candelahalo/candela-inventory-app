"""
Supplier orders (purchase orders): what Candela has ordered from HALO-UK and
other suppliers, when it's due, and what has arrived.

Receiving goods books them into stock (a stock-in movement per product
line, referenced to the PO), so the Stock page and the project's materials
update by themselves.
"""
import re
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import auth, models, schemas, workflow
from app.database import get_db
from app.utils import log_activity

router = APIRouter(prefix="/orders", tags=["Supplier orders"],
                   dependencies=[Depends(auth.get_current_user)])


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
    po.supplier_ref = (payload.supplier_ref or "").strip() or None
    po.project_id = payload.project_id
    po.order_date = payload.order_date
    po.expected_date = payload.expected_date
    po.currency = (payload.currency or "AED").strip()[:8] or "AED"
    po.notes = payload.notes
    if payload.status in ("ordered", "shipped") and not po.order_date:
        po.order_date = datetime.utcnow()


@router.get("/", response_model=List[schemas.PurchaseOrderOut])
def list_orders(project_id: Optional[int] = None, db: Session = Depends(get_db)):
    q = db.query(models.PurchaseOrder)
    if project_id:
        q = q.filter(models.PurchaseOrder.project_id == project_id)
    return q.order_by(models.PurchaseOrder.created_at.desc(), models.PurchaseOrder.id.desc()).all()


@router.get("/suppliers")
def suppliers(db: Session = Depends(get_db)):
    """Supplier names used before, for the type-ahead."""
    rows = db.query(models.PurchaseOrder.supplier).distinct().all()
    names = sorted({r[0] for r in rows if r[0]}, key=str.lower)
    brands = {b for (b,) in db.query(models.Product.brand).distinct().all() if b}
    return names + sorted(b for b in brands if b.lower() not in {n.lower() for n in names})


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
        if not it.product_id:
            first = (it.description or "").strip().split("\n")
            lines.append({"product_id": None,
                          "description": ((it.type_code + " — ") if it.type_code else "") + " / ".join(x for x in first[:3] if x),
                          "quantity": it.quantity, "unit_cost": it.unit_cost or 0.0})
    return {"quotation": quote.quote_number, "lines": lines}


@router.post("/", response_model=schemas.PurchaseOrderOut, status_code=201)
def create_order(payload: schemas.PurchaseOrderIn, db: Session = Depends(get_db),
                 current: models.User = Depends(auth.get_current_user)):
    _check_refs(db, payload)
    po = models.PurchaseOrder(po_number=_next_po_number(db), status=payload.status)
    _apply_header(po, payload)
    for it in payload.items:
        po.items.append(models.PurchaseOrderItem(
            product_id=it.product_id, description=it.description, quantity=it.quantity,
            unit_cost=it.unit_cost or 0.0, received_qty=0))
    db.add(po)
    db.flush()
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
    if payload.status == "cancelled" and po.qty_received:
        raise HTTPException(status_code=400, detail="Goods have already been received on this order, so it can't be cancelled.")
    existing = {i.id: i for i in po.items}
    keep_ids = {it.id for it in payload.items if it.id in existing}
    # A line that has had goods received can't disappear or drop below that
    for i in po.items:
        if i.id not in keep_ids and (i.received_qty or 0) > 0:
            raise HTTPException(status_code=400, detail="A line that has had goods received can't be removed.")
    for it in payload.items:
        if it.id in existing and it.quantity < (existing[it.id].received_qty or 0):
            raise HTTPException(status_code=400, detail=f"A line can't be set below the {existing[it.id].received_qty} already received.")

    _apply_header(po, payload)
    if po.status != "received":
        po.status = payload.status
    for i in list(po.items):
        if i.id not in keep_ids:
            po.items.remove(i)
    for it in payload.items:
        if it.id in existing:
            line = existing[it.id]
            if (line.received_qty or 0) == 0:
                line.product_id = it.product_id
            line.description, line.quantity, line.unit_cost = it.description, it.quantity, it.unit_cost or 0.0
        else:
            po.items.append(models.PurchaseOrderItem(
                product_id=it.product_id, description=it.description, quantity=it.quantity,
                unit_cost=it.unit_cost or 0.0, received_qty=0))
    db.flush()
    # More ordered on a fully received PO re-opens it
    if po.status == "received" and po.qty_received < po.qty_ordered:
        po.status, po.received_date = "shipped", None
    log_activity(db, current.username, "order", po.id, _label(po), "updated")
    db.commit()
    db.refresh(po)
    return po


@router.post("/{order_id}/status/{status}", response_model=schemas.PurchaseOrderOut)
def set_status(order_id: int, status: str, db: Session = Depends(get_db),
               current: models.User = Depends(auth.get_current_user)):
    po = _get(db, order_id)
    if status not in ("draft", "ordered", "shipped", "cancelled"):
        raise HTTPException(status_code=400, detail="Use Receive goods to mark an order received.")
    if status == "cancelled" and po.qty_received:
        raise HTTPException(status_code=400, detail="Goods have already been received on this order, so it can't be cancelled.")
    if po.status == "received":
        raise HTTPException(status_code=400, detail="This order has been fully received.")
    old = po.status
    po.status = status
    if status in ("ordered", "shipped") and not po.order_date:
        po.order_date = datetime.utcnow()
    log_activity(db, current.username, "order", po.id, _label(po), "status_changed", f"{old} → {status}")
    db.commit()
    db.refresh(po)
    return po


@router.post("/{order_id}/receive", response_model=schemas.PurchaseOrderOut)
def receive(order_id: int, payload: schemas.ReceiveIn, db: Session = Depends(get_db),
            current: models.User = Depends(auth.get_current_user)):
    """Book arrived goods into stock. Product lines become stock-in
    movements in the chosen warehouse; other lines are just ticked off."""
    po = _get(db, order_id)
    if po.status == "cancelled":
        raise HTTPException(status_code=400, detail="This order is cancelled.")
    warehouse = db.query(models.Warehouse).get(payload.warehouse_id)
    if not warehouse:
        raise HTTPException(status_code=404, detail="Warehouse not found")
    lines = {i.id: i for i in po.items}
    done = []
    for rl in payload.lines:
        if rl.quantity == 0:
            continue
        line = lines.get(rl.item_id)
        if not line:
            raise HTTPException(status_code=400, detail="That line isn't on this order.")
        remaining = line.quantity - (line.received_qty or 0)
        if rl.quantity < 0 or rl.quantity > remaining:
            raise HTTPException(status_code=400, detail=f"Only {remaining} still to receive on one of the lines.")
        line.received_qty = (line.received_qty or 0) + rl.quantity
        if line.product_id:
            db.add(models.StockMovement(
                product_id=line.product_id, warehouse_id=warehouse.id,
                movement_type=models.MovementType.in_, quantity=rl.quantity,
                reference=f"{po.po_number} · {po.supplier}"[:255], notes=payload.notes))
        done.append(rl.quantity)
    if not done:
        raise HTTPException(status_code=400, detail="Enter a quantity received on at least one line.")
    db.flush()
    if po.qty_received >= po.qty_ordered:
        po.status, po.received_date = "received", datetime.utcnow()
    elif po.status == "draft":
        po.status = "ordered"
    if not po.order_date:
        po.order_date = datetime.utcnow()
    log_activity(db, current.username, "order", po.id, _label(po), "received",
                 f"{sum(done)} received into {warehouse.name}"
                 + (" · order complete" if po.status == "received" else ""))
    db.commit()
    db.refresh(po)
    return po


@router.delete("/{order_id}", status_code=204)
def delete_order(order_id: int, db: Session = Depends(get_db),
                 current: models.User = Depends(auth.get_current_user)):
    po = _get(db, order_id)
    if po.qty_received:
        raise HTTPException(status_code=400, detail="Goods have been received on this order, so it's kept for the record.")
    log_activity(db, current.username, "order", po.id, _label(po), "deleted")
    db.delete(po)
    db.commit()
    return None
