from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.utils import save_product_image, log_activity
from app import auth

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
    existing = db.query(models.Product).filter(models.Product.sku == payload.sku).first()
    if existing:
        raise HTTPException(status_code=400, detail="SKU already exists")
    product = models.Product(**payload.model_dump())
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
    for key, value in payload.model_dump().items():
        setattr(product, key, value)
    log_activity(db, current.username, "product", product.id, f"{product.sku} — {product.name}", "updated")
    db.commit()
    db.refresh(product)
    return product


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
