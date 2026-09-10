import os
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.utils import save_datasheet, url_to_disk_path, get_user_name, log_activity

router = APIRouter(prefix="/datasheets", tags=["Datasheets"])


@router.get("/", response_model=List[schemas.DatasheetOut])
def list_datasheets(
    brand: Optional[str] = None,
    category: Optional[str] = None,
    product_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    q = db.query(models.Datasheet)
    if brand:
        q = q.filter(models.Datasheet.brand == brand)
    if category:
        q = q.filter(models.Datasheet.category == category)
    if product_id:
        q = q.filter(models.Datasheet.product_id == product_id)
    return q.order_by(models.Datasheet.uploaded_at.desc()).all()


@router.post("/", response_model=schemas.DatasheetOut, status_code=201)
def upload_datasheet(
    title: str = Form(...),
    brand: Optional[str] = Form(None),
    category: Optional[str] = Form(None),
    product_id: Optional[int] = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: str = Depends(get_user_name),
):
    if product_id:
        product = db.query(models.Product).get(product_id)
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")

    file_path, original_filename = save_datasheet(file)
    datasheet = models.Datasheet(
        title=title, brand=brand, category=category, product_id=product_id,
        file_path=file_path, original_filename=original_filename,
    )
    db.add(datasheet)
    db.flush()
    log_activity(db, user, "datasheet", datasheet.id, datasheet.title, "created")
    db.commit()
    db.refresh(datasheet)
    return datasheet


@router.get("/{datasheet_id}/preview")
def preview_datasheet(datasheet_id: int, db: Session = Depends(get_db)):
    """Serve the PDF inline so it opens in the browser's built-in viewer."""
    datasheet = db.query(models.Datasheet).get(datasheet_id)
    if not datasheet:
        raise HTTPException(status_code=404, detail="Datasheet not found")
    disk_path = url_to_disk_path(datasheet.file_path)
    if not os.path.exists(disk_path):
        raise HTTPException(status_code=404, detail="File is missing from the server")
    safe_name = (datasheet.original_filename or f"{datasheet.title}.pdf").replace('"', "")
    return FileResponse(
        disk_path,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{safe_name}"'},
    )


@router.get("/{datasheet_id}/download")
def download_datasheet(datasheet_id: int, db: Session = Depends(get_db)):
    """Serve the PDF as an attachment, using its original filename."""
    datasheet = db.query(models.Datasheet).get(datasheet_id)
    if not datasheet:
        raise HTTPException(status_code=404, detail="Datasheet not found")
    disk_path = url_to_disk_path(datasheet.file_path)
    if not os.path.exists(disk_path):
        raise HTTPException(status_code=404, detail="File is missing from the server")
    safe_name = (datasheet.original_filename or f"{datasheet.title}.pdf").replace('"', "")
    return FileResponse(
        disk_path,
        media_type="application/pdf",
        filename=safe_name,
    )


@router.put("/{datasheet_id}", response_model=schemas.DatasheetOut)
def update_datasheet(
    datasheet_id: int,
    title: str = Form(...),
    brand: Optional[str] = Form(None),
    category: Optional[str] = Form(None),
    product_id: Optional[int] = Form(None),
    db: Session = Depends(get_db),
    user: str = Depends(get_user_name),
):
    """Update a datasheet's labels (the PDF itself is not replaced)."""
    datasheet = db.query(models.Datasheet).get(datasheet_id)
    if not datasheet:
        raise HTTPException(status_code=404, detail="Datasheet not found")
    datasheet.title = title
    datasheet.brand = brand
    datasheet.category = category
    datasheet.product_id = product_id
    log_activity(db, user, "datasheet", datasheet.id, datasheet.title, "updated")
    db.commit()
    db.refresh(datasheet)
    return datasheet


@router.delete("/{datasheet_id}", status_code=204)
def delete_datasheet(datasheet_id: int, db: Session = Depends(get_db), user: str = Depends(get_user_name)):
    datasheet = db.query(models.Datasheet).get(datasheet_id)
    if not datasheet:
        raise HTTPException(status_code=404, detail="Datasheet not found")
    file_on_disk = url_to_disk_path(datasheet.file_path)
    if os.path.exists(file_on_disk):
        os.remove(file_on_disk)
    log_activity(db, user, "datasheet", datasheet.id, datasheet.title, "deleted")
    db.delete(datasheet)
    db.commit()
    return None
