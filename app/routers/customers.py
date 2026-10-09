from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.utils import log_activity
from app import auth

router = APIRouter(prefix="/customers", tags=["Customers"],
                   dependencies=[Depends(auth.get_current_user)])


@router.get("/", response_model=List[schemas.CustomerOut])
def list_customers(db: Session = Depends(get_db)):
    return db.query(models.Customer).order_by(models.Customer.name).all()


@router.post("/", response_model=schemas.CustomerOut, status_code=201)
def create_customer(payload: schemas.CustomerCreate, db: Session = Depends(get_db), current: models.User = Depends(auth.get_current_user)):
    customer = models.Customer(**payload.model_dump())
    db.add(customer)
    db.flush()
    log_activity(db, current.username, "customer", customer.id, customer.name, "created")
    db.commit()
    db.refresh(customer)
    return customer


@router.get("/{customer_id}", response_model=schemas.CustomerOut)
def get_customer(customer_id: int, db: Session = Depends(get_db)):
    customer = db.query(models.Customer).get(customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    return customer


@router.put("/{customer_id}", response_model=schemas.CustomerOut)
def update_customer(customer_id: int, payload: schemas.CustomerCreate, db: Session = Depends(get_db), current: models.User = Depends(auth.get_current_user)):
    customer = db.query(models.Customer).get(customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    for key, value in payload.model_dump().items():
        setattr(customer, key, value)
    log_activity(db, current.username, "customer", customer.id, customer.name, "updated")
    db.commit()
    db.refresh(customer)
    return customer


@router.delete("/{customer_id}", status_code=204)
def delete_customer(customer_id: int, db: Session = Depends(get_db), current: models.User = Depends(auth.get_current_user)):
    customer = db.query(models.Customer).get(customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    in_use = (
        db.query(models.Quotation).filter(models.Quotation.customer_id == customer_id).first()
        or db.query(models.Project).filter(models.Project.customer_id == customer_id).first()
    )
    if in_use:
        raise HTTPException(status_code=400, detail="Cannot delete a customer with existing quotations or projects")
    log_activity(db, current.username, "customer", customer.id, customer.name, "deleted")
    db.delete(customer)
    db.commit()
    return None


@router.get("/{customer_id}/summary")
def customer_summary(customer_id: int, db: Session = Depends(get_db)):
    """Everything Candela has done with this client, for the customer page."""
    customer = db.query(models.Customer).get(customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    projects = sorted(customer.projects, key=lambda p: p.created_at, reverse=True)
    quotes = sorted(customer.quotations, key=lambda q: q.created_at, reverse=True)
    pnum = {p.id: p.project_number for p in db.query(models.Project).all()}
    return {
        "customer": schemas.CustomerOut.model_validate(customer).model_dump(mode="json"),
        "projects": [{"id": p.id, "project_number": p.project_number, "name": p.name,
                      "status": p.status.value, "created_at": p.created_at.isoformat()} for p in projects],
        "quotations": [{"id": q.id, "quote_number": q.quote_number, "status": q.status.value,
                        "project": pnum.get(q.project_id), "project_id": q.project_id,
                        "total": q.total_with_vat, "created_at": q.created_at.isoformat()} for q in quotes],
        "totals": {
            "quoted": round(sum(q.total_with_vat for q in quotes), 2),
            "accepted": round(sum(q.total_with_vat for q in quotes if q.status == models.DocStatus.accepted), 2),
            "open_projects": sum(1 for p in projects if p.status != models.ProjectStatus.closed),
        },
    }
