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

    from openpyxl.worksheet.page import PageMargins
    from openpyxl.cell.rich_text import CellRichText, TextBlock
    from openpyxl.cell.text import InlineFont

    wb = Workbook()

    INK = "201E1A"
    MUTED = "56503F"
    FAINT = "9A9382"
    AMBER = "C77D0A"
    LINE = "DED6C2"
    PAPER = "FBF9F4"
    FONT = "Calibri"

    center = Alignment(horizontal="center", vertical="center")
    center_wrap = Alignment(horizontal="center", vertical="center", wrap_text=True)
    left_wrap = Alignment(horizontal="left", vertical="top", wrap_text=True)
    thin = Side(style="thin", color=LINE)
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    thin_bottom = Border(bottom=Side(style="thin", color=INK))

    def add_logo(ws, cell="A1", height=34):
        logo_path = "app/static/candela-logo-dark.png"
        if os.path.exists(logo_path):
            with PILImage.open(logo_path) as im:
                w, h = im.size
                target_w = int(w * (height / h))
            img = XLImage(logo_path)
            img.height = height
            img.width = target_w
            ws.add_image(img, cell)

    # =========================================================
    # SHEET 1 — COVER
    # =========================================================
    cover = wb.active
    cover.title = "Cover"
    cover.sheet_view.showGridLines = False
    for col, w in {"A": 3, "B": 22, "C": 22, "D": 22, "E": 22, "F": 22, "G": 22}.items():
        cover.column_dimensions[col].width = w

    add_logo(cover, "B2", height=38)
    cover.row_dimensions[1].height = 8
    cover.row_dimensions[2].height = 30
    cover.row_dimensions[3].height = 30

    r = 6
    cover.merge_cells(f"B{r}:G{r}")
    cover[f"B{r}"] = "C O M M E R C I A L   P R O P O S A L"
    cover[f"B{r}"].font = Font(name=FONT, size=9, bold=True, color=AMBER)
    cover.row_dimensions[r].height = 16
    r += 1
    cover.merge_cells(f"B{r}:G{r}")
    cover[f"B{r}"] = "Quotation"
    cover[f"B{r}"].font = Font(name=FONT, size=30, bold=True, color=INK)
    cover.row_dimensions[r].height = 42
    r += 1
    cover.merge_cells(f"B{r}:G{r}")
    cover[f"B{r}"] = quotation.subject or (quotation.project.name if quotation.project else "Supply of Lighting & Automation Fixtures")
    cover[f"B{r}"].font = Font(name=FONT, size=12, color=MUTED)
    cover.row_dimensions[r].height = 20
    r += 2

    # Rule above the metadata block
    for col in "BCDEFG":
        cover[f"{col}{r}"].border = Border(top=Side(style="thin", color=LINE))
    cover.row_dimensions[r].height = 6
    r += 1

    meta = [
        ("QUOTATION NO.", quotation.quote_number, "DATE", quotation.created_at.strftime("%d %B %Y")),
        ("PREPARED FOR", quotation.attention_to or quotation.customer.name,
         "PROJECT" if quotation.project else "COMPANY",
         quotation.project.name if quotation.project else (quotation.customer.company or "—")),
    ]
    for left_label, left_val, right_label, right_val in meta:
        cover.merge_cells(f"B{r}:C{r}")
        cover[f"B{r}"] = left_label
        cover[f"B{r}"].font = Font(name=FONT, size=8, bold=True, color=FAINT)
        cover.merge_cells(f"E{r}:G{r}")
        cover[f"E{r}"] = right_label
        cover[f"E{r}"].font = Font(name=FONT, size=8, bold=True, color=FAINT)
        cover.row_dimensions[r].height = 13
        r += 1
        cover.merge_cells(f"B{r}:C{r}")
        cover[f"B{r}"] = left_val
        cover[f"B{r}"].font = Font(name=FONT, size=11, color=INK)
        cover.merge_cells(f"E{r}:G{r}")
        cover[f"E{r}"] = right_val
        cover[f"E{r}"].font = Font(name=FONT, size=11, color=INK)
        cover.row_dimensions[r].height = 18
        r += 2

    # Rule below the metadata block
    for col in "BCDEFG":
        cover[f"{col}{r}"].border = Border(top=Side(style="thin", color=LINE))
    cover.row_dimensions[r].height = 6
    r += 2

    cover.merge_cells(f"B{r}:G{r}")
    cover[f"B{r}"] = f"Dear {quotation.attention_to or quotation.customer.name},"
    cover[f"B{r}"].font = Font(name=FONT, size=10.5, color=INK)
    r += 2

    cover.merge_cells(f"B{r}:G{r+1}")
    cover[f"B{r}"] = (
        "Thank you for the opportunity to quote for your requirements. We are pleased to enclose our proposal, "
        "with the itemized schedule and commercial terms set out on the following sheets, together with our "
        "standard Terms & Conditions."
    )
    cover[f"B{r}"].font = Font(name=FONT, size=10.5, color=INK)
    cover[f"B{r}"].alignment = left_wrap
    cover.row_dimensions[r].height = 16
    cover.row_dimensions[r + 1].height = 16
    r += 3

    terms = [
        ("CURRENCY", f"United Arab Emirates Dirhams ({quotation.currency})"),
        ("SCOPE", quotation.scope),
        ("DELIVERY", quotation.delivery_time),
        ("VALIDITY", quotation.valid_until.strftime("%d %B %Y") if quotation.valid_until else "30 days from date of issue"),
        ("PAYMENT", quotation.payment_terms),
    ]
    for label, value in terms:
        cover.merge_cells(f"B{r}:C{r}")
        cover[f"B{r}"] = label
        cover[f"B{r}"].font = Font(name=FONT, size=9, bold=True, color=MUTED)
        cover[f"B{r}"].alignment = Alignment(horizontal="left", vertical="center")
        cover.merge_cells(f"D{r}:G{r}")
        cover[f"D{r}"] = value
        cover[f"D{r}"].font = Font(name=FONT, size=10.5, color=INK)
        cover[f"D{r}"].alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
        cover.row_dimensions[r].height = 18
        r += 1
    r += 2

    cover.merge_cells(f"B{r}:G{r}")
    cover[f"B{r}"] = "We trust this proposal meets your requirements and look forward to your confirmation. Orders and payments should be issued to our legal entity as stated below."
    cover[f"B{r}"].font = Font(name=FONT, size=10.5, color=INK)
    cover[f"B{r}"].alignment = left_wrap
    r += 4

    cover.merge_cells(f"B{r}:C{r}")
    cover[f"B{r}"] = "FOR CANDELA LIGHTING AND AUTOMATION LLC"
    cover[f"B{r}"].font = Font(name=FONT, size=8, bold=True, color=FAINT)
    cover.merge_cells(f"E{r}:G{r}")
    cover[f"E{r}"] = "ACCEPTED BY CLIENT"
    cover[f"E{r}"].font = Font(name=FONT, size=8, bold=True, color=FAINT)
    r += 3
    for col_range in ("B:C", "E:G"):
        start, end = col_range.split(":")
        cover.merge_cells(f"{start}{r}:{end}{r}")
        for c in [chr(x) for x in range(ord(start), ord(end) + 1)]:
            cover[f"{c}{r}"].border = thin_bottom
    r += 1
    cover.merge_cells(f"B{r}:C{r}")
    cover[f"B{r}"] = quotation.prepared_by_name or "Authorized Signatory"
    cover[f"B{r}"].font = Font(name=FONT, size=11, bold=True, color=INK)
    cover.merge_cells(f"E{r}:G{r}")
    cover[f"E{r}"] = "Name, signature & date"
    cover[f"E{r}"].font = Font(name=FONT, size=9.5, color=MUTED)
    r += 1
    if quotation.prepared_by_title:
        cover.merge_cells(f"B{r}:C{r}")
        cover[f"B{r}"] = quotation.prepared_by_title
        cover[f"B{r}"].font = Font(name=FONT, size=9.5, color=MUTED)

    cover.page_setup.orientation = "portrait"
    cover.page_setup.fitToWidth = 1
    cover.page_setup.fitToHeight = 1
    cover.sheet_properties.pageSetUpPr.fitToPage = True
    cover.page_margins = PageMargins(left=0.5, right=0.5, top=0.6, bottom=0.6)

    # =========================================================
    # SHEET 2 — ITEMIZED SCHEDULE
    # =========================================================
    ws = wb.create_sheet("Itemized Schedule")
    ws.sheet_view.showGridLines = False
    widths = {"A": 5, "B": 12, "C": 52, "D": 8, "E": 7, "F": 12, "G": 14}
    for col, w in widths.items():
        ws.column_dimensions[col].width = w

    add_logo(ws, "A1")
    ws.row_dimensions[1].height = 30
    ws.merge_cells("C1:G1")
    ws["C1"] = quotation.quote_number
    ws["C1"].font = Font(name="IBM Plex Mono", size=9, color=MUTED)
    ws["C1"].alignment = Alignment(horizontal="right", vertical="center")
    ws.row_dimensions[2].height = 6

    ws.merge_cells("A3:G3")
    ws["A3"] = "Itemized Schedule"
    ws["A3"].font = Font(name=FONT, size=17, bold=True, color=INK)
    ws.row_dimensions[3].height = 24
    ws.merge_cells("A4:G4")
    ws["A4"] = quotation.subject or (quotation.project.name if quotation.project else "")
    ws["A4"].font = Font(name=FONT, size=10, color=FAINT)
    r = 6

    header_row = r
    headers = ["#", "IMAGE", "DESCRIPTION", "UNIT", "QTY", "PRICE", "TOTAL"]
    for i, h in enumerate(headers):
        cell = ws.cell(row=header_row, column=i + 1, value=h)
        cell.fill = PatternFill(start_color=INK, end_color=INK, fill_type="solid")
        cell.font = Font(name=FONT, color="FFFFFF", bold=True, size=8.5)
        cell.alignment = center
        cell.border = border
    ws.row_dimensions[header_row].height = 20

    title_font = InlineFont(rFont=FONT, b=True, sz=10, color=INK)
    type_font = InlineFont(rFont=FONT, b=True, sz=8.5, color=AMBER)
    brand_font = InlineFont(rFont=FONT, b=False, sz=10, color=FAINT)
    spec_font = InlineFont(rFont=FONT, b=False, sz=8.5, color=MUTED)

    row = header_row + 1
    for idx, item in enumerate(quotation.items, start=1):
        product = item.product
        fill = PatternFill(start_color=PAPER, end_color=PAPER, fill_type="solid") if idx % 2 == 0 else None

        c = ws.cell(row=row, column=1, value=idx)
        c.alignment = center
        c.border = border
        c.font = Font(name=FONT, size=9.5, color=INK)
        if fill: c.fill = fill

        # Rich-text description block: type code (amber) / product name (bold) /
        # brand (faint) / spec lines (small muted) - mirrors the PDF layout.
        blocks = []
        if item.type_code:
            blocks.append(TextBlock(type_font, item.type_code + "\n"))
        blocks.append(TextBlock(title_font, product.name if product else ""))
        if product and product.brand:
            blocks.append(TextBlock(brand_font, f"  — {product.brand}"))
        if item.description:
            blocks.append(TextBlock(spec_font, "\n" + item.description))

        desc_cell = ws.cell(row=row, column=3)
        desc_cell.value = CellRichText(*blocks)
        desc_cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        desc_cell.border = border
        if fill: desc_cell.fill = fill

        for col, val in [(4, product.unit if product else "pcs"), (5, item.quantity),
                          (6, round(item.unit_price, 2)), (7, round(item.line_total, 2))]:
            c = ws.cell(row=row, column=col, value=val)
            c.alignment = center
            c.border = border
            c.font = Font(name=FONT, size=9.5, color=INK)
            if fill: c.fill = fill
            if col in (6, 7):
                c.number_format = '#,##0.00'

        b = ws.cell(row=row, column=2); b.border = border
        if fill: b.fill = fill

        # Size the row to fit the spec text so nothing gets clipped
        spec_lines = (item.description or "").count("\n") + 1 if item.description else 0
        ws.row_dimensions[row].height = max(62, 26 + spec_lines * 11)

        if product and product.image_path:
            disk_path = url_to_disk_path(product.image_path)
            if os.path.exists(disk_path):
                try:
                    xl_img = XLImage(disk_path)
                    xl_img.height = 52
                    xl_img.width = 52
                    ws.add_image(xl_img, f"B{row}")
                except Exception:
                    pass
        row += 1

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
    ws.cell(row=row, column=1, value=f"Standard {quotation.vat_percent}% VAT applies as per UAE Federal Tax Law.").font = Font(italic=True, size=8, color=MUTED)

    ws.page_setup.orientation = "portrait"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_margins = PageMargins(left=0.4, right=0.4, top=0.5, bottom=0.5)

    # =========================================================
    # SHEET 3 — TERMS & CONDITIONS
    # =========================================================
    tc = wb.create_sheet("Terms & Conditions")
    tc.sheet_view.showGridLines = False
    tc.column_dimensions["A"].width = 4
    tc.column_dimensions["B"].width = 92

    add_logo(tc, "B2")
    tc.row_dimensions[1].height = 8
    tc.row_dimensions[2].height = 30
    tc.row_dimensions[3].height = 30

    r = 6
    tc[f"B{r}"] = "Terms & Conditions"
    tc[f"B{r}"].font = Font(name=FONT, size=17, bold=True, color=INK)
    tc.row_dimensions[r].height = 24
    r += 2

    sections = [
        ("Offer", [
            "This offer includes only the items explicitly listed in the description. Accessories or components not listed are excluded.",
            "Unit rates apply strictly to the quantities offered. Any change in quantity, or removal of items, is subject to recalculation.",
            "Prices include delivery to site unless otherwise stated.",
            "Customs duties and applicable sales tax are calculated per regulations in force at the time of order confirmation. Any changes enacted between confirmation and delivery will be reflected on the final invoice.",
        ]),
        ("Payment", [
            "Where an Advance Payment Guarantee or security cheque is required, its validity shall not exceed the agreed delivery schedule, becoming void and returned upon delivery of materials.",
            "All bank guarantees are issued per our bank's standard format.",
        ]),
        ("Delivery", [
            "Once delivered, goods are no longer the responsibility of Candela Lighting and Automation LLC and cannot be returned or refunded.",
        ]),
        ("Warranty", [
            "Standard manufacturing warranty on all items is three years, unless a different term is agreed in writing.",
            "Items with a manufacturing defect that cannot be repaired will be replaced under warranty, provided they are returned in original condition and packaging within ten days of purchase or delivery.",
        ]),
    ]
    for title, bullets in sections:
        tc[f"B{r}"] = title
        tc[f"B{r}"].font = Font(name=FONT, size=11, bold=True, color=AMBER)
        tc.row_dimensions[r].height = 18
        r += 1
        for bullet in bullets:
            tc[f"B{r}"] = "•  " + bullet
            tc[f"B{r}"].font = Font(name=FONT, size=9.5, color=INK)
            tc[f"B{r}"].alignment = left_wrap
            tc.row_dimensions[r].height = 13 * (1 + len(bullet) // 105)
            r += 1
        r += 1

    tc.page_setup.orientation = "portrait"
    tc.page_setup.fitToWidth = 1
    tc.page_setup.fitToHeight = 1
    tc.sheet_properties.pageSetUpPr.fitToPage = True
    tc.page_margins = PageMargins(left=0.5, right=0.5, top=0.6, bottom=0.6)

    wb.active = 0
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    filename = f"{quotation.quote_number.replace('/', '-')}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
