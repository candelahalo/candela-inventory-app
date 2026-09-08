from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, case

from app.database import get_db
from app import models

router = APIRouter(prefix="/reports", tags=["Reports"])


@router.get("/stock-valuation")
def stock_valuation(db: Session = Depends(get_db)):
    """Total value of stock on hand, valued at cost price."""
    rows = (
        db.query(
            models.Product.id,
            models.Product.sku,
            models.Product.name,
            models.Product.cost_price,
            func.coalesce(
                func.sum(
                    case(
                        (models.StockMovement.movement_type == models.MovementType.out, -models.StockMovement.quantity),
                        else_=models.StockMovement.quantity,
                    )
                ),
                0,
            ).label("qty"),
        )
        .select_from(models.Product)
        .outerjoin(models.StockMovement, models.StockMovement.product_id == models.Product.id)
        .group_by(models.Product.id)
        .all()
    )

    items = [
        {
            "product_id": r.id,
            "sku": r.sku,
            "name": r.name,
            "quantity_on_hand": r.qty,
            "cost_price": r.cost_price,
            "value": round((r.qty or 0) * r.cost_price, 2),
        }
        for r in rows
    ]
    return {"items": items, "total_value": round(sum(i["value"] for i in items), 2)}


@router.get("/sales-summary")
def sales_summary(db: Session = Depends(get_db)):
    """Revenue and outstanding amounts across all invoices."""
    invoices = db.query(models.Invoice).all()
    total_invoiced = 0.0
    total_collected = 0.0
    for inv in invoices:
        total = sum(item.line_total for item in inv.items)
        total_invoiced += total
        total_collected += inv.amount_paid

    return {
        "invoice_count": len(invoices),
        "total_invoiced": round(total_invoiced, 2),
        "total_collected": round(total_collected, 2),
        "total_outstanding": round(total_invoiced - total_collected, 2),
    }


@router.get("/top-products")
def top_products(limit: int = 10, db: Session = Depends(get_db)):
    """Best-selling products by total quantity invoiced."""
    rows = (
        db.query(
            models.Product.id,
            models.Product.sku,
            models.Product.name,
            func.sum(models.InvoiceItem.quantity).label("total_qty"),
        )
        .join(models.InvoiceItem, models.InvoiceItem.product_id == models.Product.id)
        .group_by(models.Product.id)
        .order_by(func.sum(models.InvoiceItem.quantity).desc())
        .limit(limit)
        .all()
    )
    return [
        {"product_id": r.id, "sku": r.sku, "name": r.name, "total_quantity_sold": int(r.total_qty)}
        for r in rows
    ]
