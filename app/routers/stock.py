from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, case

from app.database import get_db
from app import models, schemas

router = APIRouter(prefix="/stock", tags=["Stock"])


@router.post("/warehouses", response_model=schemas.WarehouseOut, status_code=201)
def create_warehouse(payload: schemas.WarehouseCreate, db: Session = Depends(get_db)):
    wh = models.Warehouse(**payload.model_dump())
    db.add(wh)
    db.commit()
    db.refresh(wh)
    return wh


@router.get("/warehouses", response_model=List[schemas.WarehouseOut])
def list_warehouses(db: Session = Depends(get_db)):
    return db.query(models.Warehouse).all()


@router.put("/warehouses/{warehouse_id}", response_model=schemas.WarehouseOut)
def update_warehouse(warehouse_id: int, payload: schemas.WarehouseCreate, db: Session = Depends(get_db)):
    wh = db.query(models.Warehouse).get(warehouse_id)
    if not wh:
        raise HTTPException(status_code=404, detail="Warehouse not found")
    for key, value in payload.model_dump().items():
        setattr(wh, key, value)
    db.commit()
    db.refresh(wh)
    return wh


@router.delete("/warehouses/{warehouse_id}", status_code=204)
def delete_warehouse(warehouse_id: int, db: Session = Depends(get_db)):
    wh = db.query(models.Warehouse).get(warehouse_id)
    if not wh:
        raise HTTPException(status_code=404, detail="Warehouse not found")
    in_use = db.query(models.StockMovement).filter(models.StockMovement.warehouse_id == warehouse_id).first()
    if in_use:
        raise HTTPException(status_code=400, detail="Cannot delete a warehouse with recorded stock movements")
    db.delete(wh)
    db.commit()
    return None


@router.delete("/movements/{movement_id}", status_code=204)
def delete_movement(movement_id: int, db: Session = Depends(get_db)):
    movement = db.query(models.StockMovement).get(movement_id)
    if not movement:
        raise HTTPException(status_code=404, detail="Movement not found")
    db.delete(movement)
    db.commit()
    return None


@router.post("/movements", response_model=schemas.StockMovementOut, status_code=201)
def create_movement(payload: schemas.StockMovementCreate, db: Session = Depends(get_db)):
    product = db.query(models.Product).get(payload.product_id)
    warehouse = db.query(models.Warehouse).get(payload.warehouse_id)
    if not product or not warehouse:
        raise HTTPException(status_code=404, detail="Product or warehouse not found")
    if payload.project_id:
        project = db.query(models.Project).get(payload.project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

    movement = models.StockMovement(**payload.model_dump())
    db.add(movement)
    db.commit()
    db.refresh(movement)
    return movement


@router.get("/movements", response_model=List[schemas.StockMovementOut])
def list_movements(project_id: Optional[int] = None, product_id: Optional[int] = None, db: Session = Depends(get_db)):
    q = db.query(models.StockMovement)
    if project_id:
        q = q.filter(models.StockMovement.project_id == project_id)
    if product_id:
        q = q.filter(models.StockMovement.product_id == product_id)
    return q.order_by(models.StockMovement.created_at.desc()).all()


@router.get("/levels", response_model=List[schemas.StockLevel])
def stock_levels(db: Session = Depends(get_db)):
    """
    Computed on-hand quantity per product per warehouse:
    sum(in) + sum(adjustment) - sum(out)
    """
    rows = (
        db.query(
            models.Product.id.label("product_id"),
            models.Product.sku,
            models.Product.name,
            models.Product.reorder_level,
            models.Warehouse.id.label("warehouse_id"),
            models.Warehouse.name.label("warehouse_name"),
            func.coalesce(
                func.sum(
                    case(
                        (models.StockMovement.movement_type == models.MovementType.out, -models.StockMovement.quantity),
                        else_=models.StockMovement.quantity,
                    )
                ),
                0,
            ).label("quantity_on_hand"),
        )
        .select_from(models.Product)
        .join(models.StockMovement, models.StockMovement.product_id == models.Product.id)
        .join(models.Warehouse, models.Warehouse.id == models.StockMovement.warehouse_id)
        .group_by(models.Product.id, models.Warehouse.id)
        .all()
    )

    return [
        schemas.StockLevel(
            product_id=r.product_id,
            sku=r.sku,
            name=r.name,
            warehouse_id=r.warehouse_id,
            warehouse_name=r.warehouse_name,
            quantity_on_hand=r.quantity_on_hand,
            reorder_level=r.reorder_level,
            below_reorder=r.quantity_on_hand < r.reorder_level,
        )
        for r in rows
    ]


@router.get("/low-stock", response_model=List[schemas.StockLevel])
def low_stock(db: Session = Depends(get_db)):
    return [level for level in stock_levels(db) if level.below_reorder]
