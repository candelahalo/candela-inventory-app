from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas

router = APIRouter(prefix="/quotations", tags=["Quotations"])


def _next_quote_number(db: Session) -> str:
    count = db.query(models.Quotation).count() + 1
    return f"QT-{count:05d}"


@router.get("/", response_model=List[schemas.QuotationOut])
def list_quotations(db: Session = Depends(get_db)):
    return db.query(models.Quotation).order_by(models.Quotation.created_at.desc()).all()


@router.post("/", response_model=schemas.QuotationOut, status_code=201)
def create_quotation(payload: schemas.QuotationCreate, db: Session = Depends(get_db)):
    customer = db.query(models.Customer).get(payload.customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    if not payload.items:
        raise HTTPException(status_code=400, detail="Quotation must have at least one item")

    quotation = models.Quotation(
        quote_number=_next_quote_number(db),
        customer_id=payload.customer_id,
        notes=payload.notes,
        valid_until=payload.valid_until,
    )
    for item in payload.items:
        quotation.items.append(models.QuotationItem(**item.model_dump()))

    db.add(quotation)
    db.commit()
    db.refresh(quotation)
    return quotation


@router.get("/{quotation_id}", response_model=schemas.QuotationOut)
def get_quotation(quotation_id: int, db: Session = Depends(get_db)):
    quotation = db.query(models.Quotation).get(quotation_id)
    if not quotation:
        raise HTTPException(status_code=404, detail="Quotation not found")
    return quotation


@router.post("/{quotation_id}/status/{new_status}", response_model=schemas.QuotationOut)
def update_status(quotation_id: int, new_status: models.DocStatus, db: Session = Depends(get_db)):
    quotation = db.query(models.Quotation).get(quotation_id)
    if not quotation:
        raise HTTPException(status_code=404, detail="Quotation not found")
    quotation.status = new_status
    db.commit()
    db.refresh(quotation)
    return quotation


@router.post("/{quotation_id}/revise", response_model=schemas.QuotationOut, status_code=201)
def revise_quotation(quotation_id: int, payload: schemas.QuotationCreate, db: Session = Depends(get_db)):
    """Create a new version of an existing quotation (keeps history instead of overwriting)."""
    original = db.query(models.Quotation).get(quotation_id)
    if not original:
        raise HTTPException(status_code=404, detail="Original quotation not found")

    new_quote = models.Quotation(
        quote_number=f"{original.quote_number}-v{original.version + 1}",
        customer_id=payload.customer_id,
        notes=payload.notes,
        valid_until=payload.valid_until,
        version=original.version + 1,
    )
    for item in payload.items:
        new_quote.items.append(models.QuotationItem(**item.model_dump()))

    db.add(new_quote)
    db.commit()
    db.refresh(new_quote)
    return new_quote
