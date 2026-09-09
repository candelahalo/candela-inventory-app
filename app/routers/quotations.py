import io
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from weasyprint import HTML
from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter
from PIL import Image as PILImage
import os

from app.database import get_db
from app import models, schemas
from app.utils import url_to_disk_path

router = APIRouter(prefix="/quotations", tags=["Quotations"])
templates = Jinja2Templates(directory="app/templates")


def _next_quote_number(db: Session) -> str:
    count = db.query(models.Quotation).count() + 1
    return f"QTN/CND/{count:04d}"


@router.get("/", response_model=List[schemas.QuotationOut])
def list_quotations(project_id: Optional[int] = None, db: Session = Depends(get_db)):
    q = db.query(models.Quotation)
    if project_id:
        q = q.filter(models.Quotation.project_id == project_id)
    return q.order_by(models.Quotation.created_at.desc()).all()


@router.post("/", response_model=schemas.QuotationOut, status_code=201)
def create_quotation(payload: schemas.QuotationCreate, db: Session = Depends(get_db)):
    customer = db.query(models.Customer).get(payload.customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    if not payload.items:
        raise HTTPException(status_code=400, detail="Quotation must have at least one item")
    if payload.project_id:
        project = db.query(models.Project).get(payload.project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

    data = payload.model_dump(exclude={"items"})
    quotation = models.Quotation(quote_number=_next_quote_number(db), **data)
    for item in payload.items:
        prod = db.query(models.Product).get(item.product_id)
        item_data = item.model_dump()
        if not item_data.get("description") and prod and prod.spec_summary:
            item_data["description"] = prod.spec_summary
        quotation.items.append(models.QuotationItem(**item_data))

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


@router.delete("/{quotation_id}", status_code=204)
def delete_quotation(quotation_id: int, db: Session = Depends(get_db)):
    quotation = db.query(models.Quotation).get(quotation_id)
    if not quotation:
        raise HTTPException(status_code=404, detail="Quotation not found")
    db.delete(quotation)
    db.commit()
    return None


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

    data = payload.model_dump(exclude={"items", "project_id"})
    new_quote = models.Quotation(
        quote_number=f"{original.quote_number}-v{original.version + 1}",
        project_id=payload.project_id or original.project_id,
        version=original.version + 1,
        **data,
    )
    for item in payload.items:
        new_quote.items.append(models.QuotationItem(**item.model_dump()))

    db.add(new_quote)
    db.commit()
    db.refresh(new_quote)
    return new_quote


@router.get("/{quotation_id}/pdf")
def quotation_pdf(quotation_id: int, db: Session = Depends(get_db)):
    quotation = db.query(models.Quotation).get(quotation_id)
    if not quotation:
        raise HTTPException(status_code=404, detail="Quotation not found")

    html_str = templates.get_template("quotation_pdf.html").render(
        {"q": quotation, "request": None}
    )
    pdf_bytes = HTML(string=html_str, base_url=".").write_pdf()
    filename = f"{quotation.quote_number.replace('/', '-')}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{quotation_id}/excel")
def quotation_excel(quotation_id: int, db: Session = Depends(get_db)):
    quotation = db.query(models.Quotation).get(quotation_id)
    if not quotation:
        raise HTTPException(status_code=404, detail="Quotation not found")

    wb = Workbook()
    ws = wb.active
    ws.title = "Quotation"

    header_fill = PatternFill(start_color="17161B", end_color="17161B", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True, size=11)
    title_font = Font(bold=True, size=16)
    bold = Font(bold=True)
    thin = Side(style="thin", color="D9D3C4")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    ws["A1"] = "CANDELA LIGHTING AND AUTOMATION LLC"
    ws["A1"].font = title_font
    ws["A2"] = f"Quotation No: {quotation.quote_number}"
    ws["A3"] = f"Date: {quotation.created_at.strftime('%d %B %Y')}"
    ws["A4"] = f"To: {quotation.attention_to or (quotation.customer.name if quotation.customer else '')}"
    ws["A5"] = f"Subject: {quotation.subject or ''}"

    headers = ["SL NO", "TYPE", "BRAND", "DESCRIPTION", "UNIT", "QTY", "UNIT PRICE", "DISC %", "TOTAL"]
    header_row = 7
    for col, h in enumerate(headers, start=1):
        cell = ws.cell(row=header_row, column=col, value=h)
        cell.fill = header_fill
        cell.font = header_font
        cell.border = border
        cell.alignment = Alignment(horizontal="center", vertical="center")

    row = header_row + 1
    for idx, item in enumerate(quotation.items, start=1):
        product = item.product
        center = Alignment(horizontal="center", vertical="center")
        left_mid = Alignment(horizontal="left", vertical="center")

        c = ws.cell(row=row, column=1, value=idx); c.border = border; c.alignment = center
        c = ws.cell(row=row, column=2, value=item.type_code or ""); c.border = border; c.alignment = center
        c = ws.cell(row=row, column=3, value=product.brand if product else ""); c.border = border; c.alignment = left_mid
        desc_cell = ws.cell(row=row, column=4, value=item.description or (product.name if product else ""))
        desc_cell.border = border
        desc_cell.alignment = Alignment(wrap_text=True, vertical="center", horizontal="left")
        c = ws.cell(row=row, column=5, value=product.unit if product else "pcs"); c.border = border; c.alignment = center
        c = ws.cell(row=row, column=6, value=item.quantity); c.border = border; c.alignment = center
        c = ws.cell(row=row, column=7, value=item.unit_price); c.border = border; c.alignment = Alignment(horizontal="right", vertical="center")
        c = ws.cell(row=row, column=8, value=item.discount_pct); c.border = border; c.alignment = center
        c = ws.cell(row=row, column=9, value=item.line_total); c.border = border; c.alignment = Alignment(horizontal="right", vertical="center")
        ws.row_dimensions[row].height = 60

        # Embed product photo scaled to a small consistent thumbnail, preserving aspect ratio
        if product and product.image_path:
            disk_path = url_to_disk_path(product.image_path)
            if os.path.exists(disk_path):
                try:
                    with PILImage.open(disk_path) as im:
                        w, h = im.size
                        target_h = 70
                        target_w = int(w * (target_h / h))
                    xl_img = XLImage(disk_path)
                    xl_img.height = target_h
                    xl_img.width = target_w
                    ws.add_image(xl_img, f"J{row}")
                except Exception:
                    pass
        row += 1

    ws.cell(row=row + 1, column=8, value="Gross Total").font = bold
    ws.cell(row=row + 1, column=9, value=quotation.gross_total).font = bold
    ws.cell(row=row + 2, column=8, value="Freight & Customs")
    ws.cell(row=row + 2, column=9, value=quotation.freight_charges)
    ws.cell(row=row + 3, column=8, value=f"VAT ({quotation.vat_percent}%)")
    ws.cell(row=row + 3, column=9, value=quotation.vat_amount)
    ws.cell(row=row + 4, column=8, value=f"Total ({quotation.currency})").font = bold
    ws.cell(row=row + 4, column=9, value=quotation.total_with_vat).font = bold

    widths = [6, 8, 14, 46, 8, 6, 11, 8, 12, 14]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    filename = f"{quotation.quote_number.replace('/', '-')}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
