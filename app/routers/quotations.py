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
from PIL import Image as PILImage
import os

from app.database import get_db
from app import models, schemas
from app.utils import url_to_disk_path, get_user_name, log_activity

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
def create_quotation(payload: schemas.QuotationCreate, db: Session = Depends(get_db), user: str = Depends(get_user_name)):
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
    db.flush()
    log_activity(db, user, "quotation", quotation.id, quotation.quote_number, "created")
    db.commit()
    db.refresh(quotation)
    return quotation


@router.get("/{quotation_id}", response_model=schemas.QuotationOut)
def get_quotation(quotation_id: int, db: Session = Depends(get_db)):
    quotation = db.query(models.Quotation).get(quotation_id)
    if not quotation:
        raise HTTPException(status_code=404, detail="Quotation not found")
    return quotation


@router.put("/{quotation_id}", response_model=schemas.QuotationOut)
def update_quotation(quotation_id: int, payload: schemas.QuotationCreate, db: Session = Depends(get_db), user: str = Depends(get_user_name)):
    quotation = db.query(models.Quotation).get(quotation_id)
    if not quotation:
        raise HTTPException(status_code=404, detail="Quotation not found")
    customer = db.query(models.Customer).get(payload.customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    if not payload.items:
        raise HTTPException(status_code=400, detail="Quotation must have at least one item")

    data = payload.model_dump(exclude={"items"})
    for key, value in data.items():
        setattr(quotation, key, value)

    quotation.items.clear()
    db.flush()
    for item in payload.items:
        prod = db.query(models.Product).get(item.product_id)
        item_data = item.model_dump()
        if not item_data.get("description") and prod and prod.spec_summary:
            item_data["description"] = prod.spec_summary
        quotation.items.append(models.QuotationItem(**item_data))

    log_activity(db, user, "quotation", quotation.id, quotation.quote_number, "updated")
    db.commit()
    db.refresh(quotation)
    return quotation


@router.delete("/{quotation_id}", status_code=204)
def delete_quotation(quotation_id: int, db: Session = Depends(get_db), user: str = Depends(get_user_name)):
    quotation = db.query(models.Quotation).get(quotation_id)
    if not quotation:
        raise HTTPException(status_code=404, detail="Quotation not found")
    log_activity(db, user, "quotation", quotation.id, quotation.quote_number, "deleted")
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

    from openpyxl.cell.rich_text import CellRichText, TextBlock
    from openpyxl.cell.text import InlineFont
    from openpyxl.worksheet.page import PageMargins

    wb = Workbook()
    ws = wb.active
    ws.title = "Quotation"

    INK = "201E1A"
    MUTED = "56503F"
    AMBER = "C77D0A"
    LINE = "DED6C2"

    center = Alignment(horizontal="center", vertical="center")
    center_wrap = Alignment(horizontal="center", vertical="center", wrap_text=True)
    thin = Side(style="thin", color=LINE)
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    COLS = ["A", "B", "C", "D", "E", "F", "G"]  # #, Image, Description, Unit, Qty, Price, Total
    widths = {"A": 5, "B": 12, "C": 52, "D": 8, "E": 7, "F": 12, "G": 14}
    for col, w in widths.items():
        ws.column_dimensions[col].width = w

    # ---------- Letterhead ----------
    logo_path = "app/static/candela-logo-dark.png"
    if os.path.exists(logo_path):
        with PILImage.open(logo_path) as im:
            w, h = im.size
            target_h = 34
            target_w = int(w * (target_h / h))
        logo_img = XLImage(logo_path)
        logo_img.height = target_h
        logo_img.width = target_w
        ws.add_image(logo_img, "A1")
    ws.row_dimensions[1].height = 30
    ws.row_dimensions[2].height = 6

    ws.merge_cells("A3:C3")
    ws["A3"] = "QUOTATION"
    ws["A3"].font = Font(name="Calibri", size=18, bold=True, color=INK)

    ws.merge_cells("D3:G3")
    ws["D3"] = quotation.subject or (quotation.project.name if quotation.project else "")
    ws["D3"].font = Font(size=10, italic=True, color=MUTED)
    ws["D3"].alignment = Alignment(horizontal="right", vertical="center")

    info_rows = [
        ("Quotation No.", quotation.quote_number),
        ("Date", quotation.created_at.strftime("%d %B %Y")),
        ("Prepared For", quotation.attention_to or quotation.customer.name),
        ("Project" if quotation.project else "Company", quotation.project.name if quotation.project else (quotation.customer.company or "—")),
    ]
    r = 5
    for label, value in info_rows:
        ws.merge_cells(f"A{r}:B{r}")
        ws[f"A{r}"] = label
        ws[f"A{r}"].font = Font(size=9, bold=True, color=MUTED)
        ws[f"A{r}"].alignment = Alignment(horizontal="left", vertical="center")
        ws.merge_cells(f"C{r}:G{r}")
        ws[f"C{r}"] = value
        ws[f"C{r}"].font = Font(size=10, color=INK)
        ws[f"C{r}"].alignment = Alignment(horizontal="left", vertical="center")
        r += 1

    r += 1  # blank spacer row

    # ---------- Item table header ----------
    header_row = r
    headers = ["#", "Image", "Description", "Unit", "Qty", "Price", "Total"]
    for i, h in enumerate(headers):
        cell = ws.cell(row=header_row, column=i + 1, value=h)
        cell.fill = PatternFill(start_color=INK, end_color=INK, fill_type="solid")
        cell.font = Font(color="FFFFFF", bold=True, size=10)
        cell.alignment = center
        cell.border = border

    bold_title = InlineFont(b=True, sz=10)
    normal_spec = InlineFont(b=False, sz=9, color=MUTED)

    row = header_row + 1
    for idx, item in enumerate(quotation.items, start=1):
        product = item.product
        title = f"{(item.type_code + ' — ') if item.type_code else ''}{product.name if product else ''}"
        if product and product.brand:
            title += f" ({product.brand})"

        ws.cell(row=row, column=1, value=idx).alignment = center
        ws.cell(row=row, column=1).border = border

        desc_cell = ws.cell(row=row, column=3)
        if item.description:
            desc_cell.value = CellRichText(
                TextBlock(bold_title, title), "\n", TextBlock(normal_spec, item.description)
            )
        else:
            desc_cell.value = title
            desc_cell.font = Font(bold=True, size=10)
        desc_cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
        desc_cell.border = border

        for col, val in [(4, product.unit if product else "pcs"), (5, item.quantity),
                          (6, round(item.unit_price, 2)), (7, round(item.line_total, 2))]:
            c = ws.cell(row=row, column=col, value=val)
            c.alignment = center
            c.border = border
            if col in (6, 7):
                c.number_format = '#,##0.00'

        ws.cell(row=row, column=2).border = border
        ws.row_dimensions[row].height = 62

        if product and product.image_path:
            disk_path = url_to_disk_path(product.image_path)
            if os.path.exists(disk_path):
                try:
                    xl_img = XLImage(disk_path)
                    xl_img.height = 56
                    xl_img.width = 56
                    ws.add_image(xl_img, f"B{row}")
                except Exception:
                    pass
        row += 1

    # ---------- Totals ----------
    totals_col_label, totals_col_val = 5, 7
    totals = [("Gross Total", quotation.gross_total, False)]
    if quotation.freight_charges:
        totals.append(("Freight & Customs", quotation.freight_charges, False))
    totals.append(("Subtotal (VAT excl.)", quotation.grand_total, False))
    totals.append((f"VAT ({quotation.vat_percent}%)", quotation.vat_amount, False))
    totals.append(("Total Due", quotation.total_with_vat, True))

    row += 1
    for label, value, is_grand in totals:
        ws.merge_cells(start_row=row, start_column=totals_col_label, end_row=row, end_column=6)
        lbl_cell = ws.cell(row=row, column=totals_col_label, value=label)
        val_cell = ws.cell(row=row, column=totals_col_val, value=value)
        f = Font(bold=True, size=12 if is_grand else 10, color=INK if is_grand else MUTED)
        lbl_cell.font = f
        val_cell.font = f
        lbl_cell.alignment = Alignment(horizontal="right", vertical="center")
        val_cell.alignment = center
        val_cell.number_format = f'#,##0.00 "{quotation.currency}"'
        if is_grand:
            top = Side(style="thin", color=INK)
            lbl_cell.border = Border(top=top)
            val_cell.border = Border(top=top)
        row += 1

    row += 1
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=7)
    note_cell = ws.cell(row=row, column=1, value=f"Standard {quotation.vat_percent}% VAT applies as per UAE Federal Tax Law.")
    note_cell.font = Font(italic=True, size=8, color=MUTED)

    # Page setup, so "Save as PDF" from Excel prints cleanly on one page width
    ws.page_setup.orientation = "portrait"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_margins = PageMargins(left=0.4, right=0.4, top=0.5, bottom=0.5)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    filename = f"{quotation.quote_number.replace('/', '-')}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
