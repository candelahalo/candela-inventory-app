import os
import re
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.utils import save_datasheet, save_datasheet_bytes, url_to_disk_path, log_activity
from pydantic import BaseModel
from app import auth

router = APIRouter(prefix="/datasheets", tags=["Datasheets"],
                   dependencies=[Depends(auth.get_current_user)])

# Preview/download are mounted on a separate, unauthenticated router:
# quotation PDFs sent to clients link straight to a product's datasheet,
# and a client has no login. Manufacturer spec sheets are public marketing
# material, so this is deliberate - but it does mean anyone with the link
# can open that PDF.
public_router = APIRouter(prefix="/datasheets", tags=["Datasheets (public)"])


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
    kind: str = Form("supplier"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current: models.User = Depends(auth.get_current_user),
):
    if kind not in ("supplier", "halo"):
        raise HTTPException(status_code=400, detail="kind must be supplier or halo")
    if product_id:
        product = db.query(models.Product).get(product_id)
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")

    file_path, original_filename = save_datasheet(file)
    if product_id:
        # The uploaded PDF is the datasheet to use: a supplier PDF, or a HALO
        # sheet made outside the app (used instead of the automatic one)
        product.datasheet_mode, product.no_datasheet = kind, False
    datasheet = models.Datasheet(
        title=title, brand=brand, category=category, product_id=product_id,
        file_path=file_path, original_filename=original_filename, kind=kind,
    )
    db.add(datasheet)
    db.flush()
    log_activity(db, current.username, "datasheet", datasheet.id, datasheet.title, "created")
    db.commit()
    db.refresh(datasheet)
    return datasheet


class LinkIn(BaseModel):
    url: str


@router.post("/from-link/{product_id}", response_model=schemas.DatasheetOut, status_code=201)
def datasheet_from_link(product_id: int, payload: LinkIn, db: Session = Depends(get_db),
                        current: models.User = Depends(auth.get_current_user)):
    """Download the brand's datasheet PDF from a pasted link and keep a copy,
    the same as uploading it."""
    product = db.query(models.Product).get(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    from app.pdf_fetch import fetch_pdf
    data, name = fetch_pdf(payload.url)
    file_path, original_filename = save_datasheet_bytes(data, name)
    product.datasheet_mode, product.no_datasheet = "supplier", False
    datasheet = models.Datasheet(
        title=product.name, brand=product.brand, category=product.category, product_id=product.id,
        file_path=file_path, original_filename=original_filename,
    )
    db.add(datasheet)
    db.flush()
    log_activity(db, current.username, "datasheet", datasheet.id, datasheet.title, "created",
                 "from link " + payload.url[:300])
    db.commit()
    db.refresh(datasheet)
    return datasheet


@public_router.get("/halo/{product_id}")
def halo_datasheet(product_id: int, db: Session = Depends(get_db)):
    """The product's HALO datasheet: an uploaded HALO sheet if there is one,
    otherwise made from its data each time it's opened. Public like the
    uploaded datasheets: quotation PDFs link here."""
    product = db.query(models.Product).get(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    own = (db.query(models.Datasheet)
           .filter(models.Datasheet.product_id == product_id, models.Datasheet.kind == "halo")
           .order_by(models.Datasheet.uploaded_at.desc()).first())
    if own and os.path.exists(url_to_disk_path(own.file_path)):
        safe = (own.original_filename or f"{product.sku}.pdf").replace('"', "")
        return FileResponse(url_to_disk_path(own.file_path), media_type="application/pdf",
                            headers={"Content-Disposition": f'inline; filename="{safe}"'})
    from app import halo_sheet
    pdf = halo_sheet.build(product)
    sku = product.sku if product.sku.upper().startswith("HALO") else f"HALO-{product.sku}"
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", sku).strip("-") + ".pdf"
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{name}"'})


@public_router.get("/{datasheet_id}/preview")
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


@public_router.get("/{datasheet_id}/download")
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
    current: models.User = Depends(auth.get_current_user),
):
    """Update a datasheet's labels (the PDF itself is not replaced)."""
    datasheet = db.query(models.Datasheet).get(datasheet_id)
    if not datasheet:
        raise HTTPException(status_code=404, detail="Datasheet not found")
    datasheet.title = title
    datasheet.brand = brand
    datasheet.category = category
    datasheet.product_id = product_id
    log_activity(db, current.username, "datasheet", datasheet.id, datasheet.title, "updated")
    db.commit()
    db.refresh(datasheet)
    return datasheet


@router.delete("/{datasheet_id}", status_code=204)
def delete_datasheet(datasheet_id: int, db: Session = Depends(get_db), current: models.User = Depends(auth.get_current_user)):
    datasheet = db.query(models.Datasheet).get(datasheet_id)
    if not datasheet:
        raise HTTPException(status_code=404, detail="Datasheet not found")
    file_on_disk = url_to_disk_path(datasheet.file_path)
    if os.path.exists(file_on_disk):
        os.remove(file_on_disk)
    log_activity(db, current.username, "datasheet", datasheet.id, datasheet.title, "deleted")
    product = datasheet.product
    db.delete(datasheet)
    db.flush()
    # Last supplier PDF gone: back to the HALO sheet made automatically
    if product and product.datasheet_mode == "supplier" and \
            not any((d.kind or "supplier") == "supplier" for d in product.datasheets):
        product.datasheet_mode = "halo"
    db.commit()
    return None
