from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas

router = APIRouter(prefix="/invoices", tags=["Invoices"])


def _next_invoice_number(db: Session) -> str:
    count = db.query(models.Invoice).count() + 1
    return f"INV-{count:05d}"


@router.get("/", response_model=List[schemas.InvoiceOut])
def list_invoices(db: Session = Depends(get_db)):
    return db.query(models.Invoice).order_by(models.Invoice.created_at.desc()).all()


@router.post("/", response_model=schemas.InvoiceOut, status_code=201)
def create_invoice(payload: schemas.InvoiceCreate, db: Session = Depends(get_db)):
    customer = db.query(models.Customer).get(payload.customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    if not payload.items:
        raise HTTPException(status_code=400, detail="Invoice must have at least one item")

    invoice = models.Invoice(
        invoice_number=_next_invoice_number(db),
        customer_id=payload.customer_id,
        quotation_id=payload.quotation_id,
        due_date=payload.due_date,
        notes=payload.notes,
    )
    for item in payload.items:
        invoice.items.append(models.InvoiceItem(**item.model_dump()))

    db.add(invoice)
    db.commit()
    db.refresh(invoice)

    if payload.quotation_id:
        quotation = db.query(models.Quotation).get(payload.quotation_id)
        if quotation:
            quotation.status = models.DocStatus.invoiced
            db.commit()

    return invoice


@router.post("/from-quotation/{quotation_id}", response_model=schemas.InvoiceOut, status_code=201)
def create_invoice_from_quotation(quotation_id: int, db: Session = Depends(get_db)):
    quotation = db.query(models.Quotation).get(quotation_id)
    if not quotation:
        raise HTTPException(status_code=404, detail="Quotation not found")
    if quotation.invoice:
        raise HTTPException(status_code=400, detail="Quotation already invoiced")

    invoice = models.Invoice(
        invoice_number=_next_invoice_number(db),
        customer_id=quotation.customer_id,
        quotation_id=quotation.id,
        notes=quotation.notes,
    )
    for item in quotation.items:
        invoice.items.append(
            models.InvoiceItem(
                product_id=item.product_id,
                description=item.description,
                quantity=item.quantity,
                unit_price=item.unit_price,
                discount_pct=item.discount_pct,
            )
        )

    quotation.status = models.DocStatus.invoiced
    db.add(invoice)
    db.commit()
    db.refresh(invoice)
    return invoice


@router.get("/{invoice_id}", response_model=schemas.InvoiceOut)
def get_invoice(invoice_id: int, db: Session = Depends(get_db)):
    invoice = db.query(models.Invoice).get(invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return invoice


@router.post("/{invoice_id}/record-payment", response_model=schemas.InvoiceOut)
def record_payment(invoice_id: int, payload: schemas.PaymentUpdate, db: Session = Depends(get_db)):
    invoice = db.query(models.Invoice).get(invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    invoice.amount_paid += payload.amount
    total = sum(item.line_total for item in invoice.items)
    if invoice.amount_paid >= total:
        invoice.status = models.InvoiceStatus.paid
    elif invoice.amount_paid > 0:
        invoice.status = models.InvoiceStatus.partially_paid

    db.commit()
    db.refresh(invoice)
    return invoice
