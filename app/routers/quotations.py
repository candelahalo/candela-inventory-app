import io
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func
from weasyprint import HTML
from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from PIL import Image as PILImage
import os

from app.database import get_db
from app import models, schemas
from app.utils import url_to_disk_path, log_activity
from app import auth
from app.settings import BASE_URL

router = APIRouter(prefix="/quotations", tags=["Quotations"],
                   dependencies=[Depends(auth.get_current_user)])

# PDF and Excel open via plain browser navigation (window.open / an <a> href),
# which cannot set an Authorization header. They authenticate with the same
# 60-second download token the backup download uses, so the real session token
# never travels in a URL.
download_router = APIRouter(prefix="/quotations", tags=["Quotations (download)"])
templates = Jinja2Templates(directory="app/templates")

# Cost/margin fields are stripped from API responses for non-admin users.
MARGIN_FIELDS = {"total_cost", "total_margin", "total_margin_pct"}
MARGIN_ITEM_FIELDS = {"unit_cost", "line_cost", "line_margin", "line_margin_pct"}


def _strip_margin(payload, admin: bool):
    """Remove cost/margin figures unless the caller is an admin."""
    if admin:
        return payload
    items = payload if isinstance(payload, list) else [payload]
    for q in items:
        for f in MARGIN_FIELDS:
            q.pop(f, None)
        for item in q.get("items", []):
            for f in MARGIN_ITEM_FIELDS:
                item.pop(f, None)
    return payload


def _next_quote_number(db: Session) -> str:
    count = db.query(models.Quotation).count() + 1
    return f"QTN/CND/{count:04d}"


@router.get("/")
def list_quotations(project_id: Optional[int] = None, db: Session = Depends(get_db), current: models.User = Depends(auth.get_current_user)):
    q = db.query(models.Quotation)
    if project_id:
        q = q.filter(models.Quotation.project_id == project_id)
    rows = q.order_by(models.Quotation.created_at.desc()).all()
    payload = [schemas.QuotationOut.model_validate(r).model_dump(mode="json") for r in rows]
    return _strip_margin(payload, current.role == "admin")


def _resolve_customer(payload, db: Session, user: str) -> models.Customer:
    """Find the customer by id, or by name - creating them if the name is new.

    Lets a quotation be raised for a walk-in client without having to add
    them on the Customers page first.
    """
    if payload.customer_id:
        customer = db.query(models.Customer).get(payload.customer_id)
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")
        return customer

    name = (payload.customer_name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Choose a customer or type a new name.")

    # Match case-insensitively so "ACME" doesn't create a twin of "Acme"
    existing = db.query(models.Customer).filter(func.lower(models.Customer.name) == name.lower()).first()
    if existing:
        return existing

    customer = models.Customer(name=name)
    db.add(customer)
    db.flush()
    log_activity(db, user, "customer", customer.id, customer.name,
                 "created", "added while raising a quotation")
    return customer


def _resolve_project(payload, customer: models.Customer, db: Session, user: str):
    """Find the project by id, or by name - creating it against this
    customer if the name is new. Returns None when no project is given,
    since a quotation doesn't have to belong to one."""
    if payload.project_id:
        project = db.query(models.Project).get(payload.project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        return project

    name = (getattr(payload, "project_name", None) or "").strip()
    if not name:
        return None

    existing = (
        db.query(models.Project)
        .filter(func.lower(models.Project.name) == name.lower())
        .first()
    )
    if existing:
        return existing

    count = db.query(models.Project).count() + 1
    project = models.Project(
        project_number=f"PRJ-{count:05d}",
        name=name,
        customer_id=customer.id,
        status=models.ProjectStatus.enquiry,
    )
    db.add(project)
    db.flush()
    project.status_history.append(
        models.ProjectStatusHistory(status=models.ProjectStatus.enquiry,
                                    notes="Created while raising a quotation")
    )
    log_activity(db, user, "project", project.id, f"{project.project_number} — {project.name}",
                 "created", "added while raising a quotation")
    return project


@router.post("/", response_model=schemas.QuotationOut, status_code=201)
def create_quotation(payload: schemas.QuotationCreate, db: Session = Depends(get_db), current: models.User = Depends(auth.get_current_user)):
    customer = _resolve_customer(payload, db, current.username)
    if not payload.items:
        raise HTTPException(status_code=400, detail="Quotation must have at least one item")
    project = _resolve_project(payload, customer, db, current.username)

    data = payload.model_dump(exclude={"items", "customer_name", "customer_id",
                                       "project_name", "project_id"})
    quotation = models.Quotation(quote_number=_next_quote_number(db),
                                 customer_id=customer.id,
                                 project_id=project.id if project else None,
                                 **data)
    for item in payload.items:
        prod = db.query(models.Product).get(item.product_id)
        item_data = item.model_dump()
        if not item_data.get("description") and prod and prod.spec_summary:
            item_data["description"] = prod.spec_summary
        # Snapshot the cost at quoting time so margin stays accurate even if
        # the product's cost price changes later.
        if item_data.get("unit_cost") is None:
            item_data["unit_cost"] = prod.cost_price if prod else 0.0
        quotation.items.append(models.QuotationItem(**item_data))

    db.add(quotation)
    db.flush()
    log_activity(db, current.username, "quotation", quotation.id, quotation.quote_number, "created")
    db.commit()
    db.refresh(quotation)
    return quotation


@router.get("/{quotation_id}")
def get_quotation(quotation_id: int, db: Session = Depends(get_db), current: models.User = Depends(auth.get_current_user)):
    quotation = db.query(models.Quotation).get(quotation_id)
    if not quotation:
        raise HTTPException(status_code=404, detail="Quotation not found")
    payload = schemas.QuotationOut.model_validate(quotation).model_dump(mode="json")
    return _strip_margin(payload, current.role == "admin")


@router.put("/{quotation_id}", response_model=schemas.QuotationOut)
def update_quotation(quotation_id: int, payload: schemas.QuotationCreate, db: Session = Depends(get_db), current: models.User = Depends(auth.get_current_user)):
    quotation = db.query(models.Quotation).get(quotation_id)
    if not quotation:
        raise HTTPException(status_code=404, detail="Quotation not found")
    customer = _resolve_customer(payload, db, current.username)
    if not payload.items:
        raise HTTPException(status_code=400, detail="Quotation must have at least one item")
    project = _resolve_project(payload, customer, db, current.username)

    data = payload.model_dump(exclude={"items", "customer_name", "customer_id",
                                       "project_name", "project_id"})
    for key, value in data.items():
        setattr(quotation, key, value)
    quotation.customer_id = customer.id
    quotation.project_id = project.id if project else None

    quotation.items.clear()
    db.flush()
    for item in payload.items:
        prod = db.query(models.Product).get(item.product_id)
        item_data = item.model_dump()
        if not item_data.get("description") and prod and prod.spec_summary:
            item_data["description"] = prod.spec_summary
        # Snapshot the cost at quoting time so margin stays accurate even if
        # the product's cost price changes later.
        if item_data.get("unit_cost") is None:
            item_data["unit_cost"] = prod.cost_price if prod else 0.0
        quotation.items.append(models.QuotationItem(**item_data))

    log_activity(db, current.username, "quotation", quotation.id, quotation.quote_number, "updated")
    db.commit()
    db.refresh(quotation)
    return quotation


@router.delete("/{quotation_id}", status_code=204)
def delete_quotation(quotation_id: int, db: Session = Depends(get_db), current: models.User = Depends(auth.get_current_user)):
    quotation = db.query(models.Quotation).get(quotation_id)
    if not quotation:
        raise HTTPException(status_code=404, detail="Quotation not found")
    log_activity(db, current.username, "quotation", quotation.id, quotation.quote_number, "deleted")
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


@download_router.get("/{quotation_id}/pdf")
def quotation_pdf(quotation_id: int, token: str = Query(...), db: Session = Depends(get_db)):
    auth.get_download_user_from_token(token, db)
    quotation = db.query(models.Quotation).get(quotation_id)
    if not quotation:
        raise HTTPException(status_code=404, detail="Quotation not found")

    # Map product -> its most recent datasheet, so the product name in the
    # document can link straight to the spec sheet.
    product_ids = [i.product_id for i in quotation.items if i.product_id]
    datasheet_links = {}
    if product_ids:
        sheets = (
            db.query(models.Datasheet)
            .filter(models.Datasheet.product_id.in_(product_ids))
            .order_by(models.Datasheet.uploaded_at.desc())
            .all()
        )
        for s in sheets:
            datasheet_links.setdefault(s.product_id, f"{BASE_URL}/datasheets/{s.id}/preview")

    html_str = templates.get_template("quotation_pdf.html").render(
        {"q": quotation, "request": None, "datasheet_links": datasheet_links}
    )
    pdf_bytes = HTML(string=html_str, base_url=".").write_pdf()
    filename = f"{quotation.quote_number.replace('/', '-')}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@download_router.get("/{quotation_id}/excel")
def quotation_excel(quotation_id: int, token: str = Query(...), db: Session = Depends(get_db)):
    auth.get_download_user_from_token(token, db)
    quotation = db.query(models.Quotation).get(quotation_id)
    if not quotation:
        raise HTTPException(status_code=404, detail="Quotation not found")

    # Map product -> its most recent datasheet for clickable links in the sheet
    product_ids = [i.product_id for i in quotation.items if i.product_id]
    datasheet_links = {}
    if product_ids:
        sheets = (
            db.query(models.Datasheet)
            .filter(models.Datasheet.product_id.in_(product_ids))
            .order_by(models.Datasheet.uploaded_at.desc())
            .all()
        )
        for s in sheets:
            datasheet_links.setdefault(s.product_id, f"{BASE_URL}/datasheets/{s.id}/preview")

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
    FONT = "IBM Plex Sans"
    FONT_MONO = "IBM Plex Mono"

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
    # Sized to fit A4 portrait printable width at 100% scale
    for col, w in {"A": 2, "B": 15, "C": 15, "D": 15, "E": 15, "F": 15, "G": 15}.items():
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

    cover.merge_cells(f"B{r}:G{r+2}")
    cover[f"B{r}"] = (
        "Thank you for the opportunity to quote for your requirements. We are pleased to enclose our proposal, "
        "with the itemized schedule and commercial terms set out on the following sheets, together with our "
        "standard Terms & Conditions."
    )
    cover[f"B{r}"].font = Font(name=FONT, size=10.5, color=INK)
    cover[f"B{r}"].alignment = left_wrap
    for i in range(3):
        cover.row_dimensions[r + i].height = 15
    r += 4

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

    cover.merge_cells(f"B{r}:G{r+1}")
    cover[f"B{r}"] = "We trust this proposal meets your requirements and look forward to your confirmation. Orders and payments should be issued to our legal entity as stated below."
    cover[f"B{r}"].font = Font(name=FONT, size=10.5, color=INK)
    cover[f"B{r}"].alignment = left_wrap
    cover.row_dimensions[r].height = 15
    cover.row_dimensions[r + 1].height = 15
    r += 4

    cover.merge_cells(f"B{r}:D{r}")
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
    cover.merge_cells(f"B{r}:D{r}")
    cover[f"B{r}"] = quotation.prepared_by_name or "Authorized Signatory"
    cover[f"B{r}"].font = Font(name=FONT, size=11, bold=True, color=INK)
    cover.merge_cells(f"E{r}:G{r}")
    cover[f"E{r}"] = "Name, signature & date"
    cover[f"E{r}"].font = Font(name=FONT, size=9.5, color=MUTED)
    r += 1
    if quotation.prepared_by_title:
        cover.merge_cells(f"B{r}:D{r}")
        cover[f"B{r}"] = quotation.prepared_by_title
        cover[f"B{r}"].font = Font(name=FONT, size=9.5, color=MUTED)

    cover.page_setup.orientation = "portrait"
    cover.page_setup.paperSize = cover.PAPERSIZE_A4
    cover.page_setup.fitToWidth = 1
    cover.page_setup.fitToHeight = 1
    cover.sheet_properties.pageSetUpPr.fitToPage = True
    cover.print_options.horizontalCentered = True
    cover.page_margins = PageMargins(left=0.6, right=0.6, top=0.7, bottom=0.7)
    cover.oddFooter.center.text = "We Light Your Dreams…"
    cover.oddFooter.center.size = 8
    cover.oddFooter.center.color = "9A9382"

    # =========================================================
    # SHEET 2 — ITEMIZED SCHEDULE
    # =========================================================
    ws = wb.create_sheet("Itemized Schedule")
    ws.sheet_view.showGridLines = False
    # Sized to fit A4 portrait printable width (~185mm with 0.5in margins) at
    # 100% scale, so nothing gets shrunk down when printed.
    widths = {"A": 4, "B": 10, "C": 36, "D": 7, "E": 6, "F": 10, "G": 6, "H": 12}
    for col, w in widths.items():
        ws.column_dimensions[col].width = w

    add_logo(ws, "A1")
    ws.row_dimensions[1].height = 30
    ws.merge_cells("C1:H1")
    ws["C1"] = quotation.quote_number
    ws["C1"].font = Font(name=FONT_MONO, size=9, color=FAINT)
    ws["C1"].alignment = Alignment(horizontal="right", vertical="center")
    ws.row_dimensions[2].height = 6

    ws.merge_cells("A3:H3")
    ws["A3"] = "Itemized Schedule"
    ws["A3"].font = Font(name=FONT, size=17, bold=True, color=INK)
    ws.row_dimensions[3].height = 24
    ws.merge_cells("A4:H4")
    ws["A4"] = quotation.subject or (quotation.project.name if quotation.project else "")
    ws["A4"].font = Font(name=FONT, size=10, color=FAINT)
    r = 6

    header_row = r
    headers = ["#", "IMAGE", "DESCRIPTION", "UNIT", "QTY", "PRICE", "DISC", "TOTAL"]
    for i, h in enumerate(headers):
        cell = ws.cell(row=header_row, column=i + 1, value=h)
        cell.fill = PatternFill(start_color=INK, end_color=INK, fill_type="solid")
        cell.font = Font(name=FONT, color="FFFFFF", bold=True, size=8.5)
        cell.alignment = center
        cell.border = border
    ws.row_dimensions[header_row].height = 20

    title_font = InlineFont(rFont=FONT, b=True, sz=10, color=INK)
    type_font = InlineFont(rFont=FONT, b=True, sz=8.5, color=AMBER)
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
        ds_url = datasheet_links.get(item.product_id)
        if item.description:
            blocks.append(TextBlock(spec_font, "\n" + item.description))

        desc_cell = ws.cell(row=row, column=3)
        desc_cell.value = CellRichText(*blocks)
        desc_cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        desc_cell.border = border
        if ds_url:
            desc_cell.hyperlink = ds_url
        if fill: desc_cell.fill = fill

        for col, val in [(4, product.unit if product else "pcs"), (5, item.quantity),
                          (6, round(item.unit_price, 2))]:
            c = ws.cell(row=row, column=col, value=val)
            c.alignment = center
            c.border = border
            c.font = Font(name=FONT, size=9.5, color=INK)
            if fill: c.fill = fill
            if col == 6:
                c.number_format = '#,##0.00'

        # Discount shown in its own column, and folded into the line-total
        # formula so the sheet still recalculates when edited.
        disc_cell = ws.cell(row=row, column=7, value=(item.discount_pct or 0) / 100)
        disc_cell.number_format = '0%'
        disc_cell.alignment = center
        disc_cell.border = border
        disc_cell.font = Font(name=FONT, size=9.5, color=INK)
        if fill: disc_cell.fill = fill

        # Line total is a live formula (qty × price, less any discount) so the
        # sheet recalculates if someone edits quantities, rates or the discount.
        total_cell = ws.cell(row=row, column=8)
        total_cell.value = f"=E{row}*F{row}*(1-G{row})"
        total_cell.alignment = center
        total_cell.border = border
        total_cell.font = Font(name=FONT, size=9.5, color=INK)
        total_cell.number_format = '#,##0.00'
        if fill: total_cell.fill = fill

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

    first_item_row = header_row + 1
    last_item_row = row - 1

    freight_row = None
    transport_row = None
    subtotal_row = None
    gross_row = None

    row += 1
    totals_spec = []
    totals_spec.append(("Gross Total", f"=SUM(H{first_item_row}:H{last_item_row})", False))
    if quotation.freight_charges:
        totals_spec.append(("Freight & Customs", quotation.freight_charges, False))
    totals_spec.append(("Transportation", None, False))
    totals_spec.append(("Subtotal (VAT excl.)", None, False))
    totals_spec.append((f"VAT ({quotation.vat_percent}%)", None, False))
    totals_spec.append(("Total Due", None, True))

    for label, value, is_grand in totals_spec:
        ws.merge_cells(start_row=row, start_column=5, end_row=row, end_column=7)
        lbl_cell = ws.cell(row=row, column=5, value=label)
        val_cell = ws.cell(row=row, column=8)

        if label == "Gross Total":
            gross_row = row
            val_cell.value = value
            val_cell.number_format = f'#,##0.00 "{quotation.currency}"'
        elif label == "Freight & Customs":
            freight_row = row
            val_cell.value = value
            val_cell.number_format = f'#,##0.00 "{quotation.currency}"'
        elif label == "Transportation":
            transport_row = row
            if quotation.transportation_is_text:
                # Free text like "Included" - shown as-is and excluded from the sum
                val_cell.value = quotation.transportation_charges
            else:
                val_cell.value = quotation.transportation_amount
                val_cell.number_format = f'#,##0.00 "{quotation.currency}"'
        elif label.startswith("Subtotal"):
            subtotal_row = row
            parts = [f"H{gross_row}"]
            if freight_row:
                parts.append(f"H{freight_row}")
            if transport_row and not quotation.transportation_is_text:
                parts.append(f"H{transport_row}")
            val_cell.value = "=" + "+".join(parts)
            val_cell.number_format = f'#,##0.00 "{quotation.currency}"'
        elif label.startswith("VAT"):
            vat_row = row
            val_cell.value = f"=H{subtotal_row}*{quotation.vat_percent / 100}"
            val_cell.number_format = f'#,##0.00 "{quotation.currency}"'
        else:
            val_cell.value = f"=H{subtotal_row}+H{vat_row}"
            val_cell.number_format = f'#,##0.00 "{quotation.currency}"'

        f = Font(name=FONT, bold=True, size=12 if is_grand else 10, color=INK if is_grand else MUTED)
        lbl_cell.font = f
        val_cell.font = f
        lbl_cell.alignment = Alignment(horizontal="right", vertical="center")
        val_cell.alignment = center
        if is_grand:
            top = Side(style="thin", color=INK)
            lbl_cell.border = Border(top=top)
            val_cell.border = Border(top=top)
        ws.row_dimensions[row].height = 20 if is_grand else 16
        row += 1

    row += 1
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=8)
    ws.cell(row=row, column=1, value=f"Standard {quotation.vat_percent}% VAT applies as per UAE Federal Tax Law.").font = Font(italic=True, size=8, color=MUTED)

    ws.page_setup.orientation = "portrait"
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_options.horizontalCentered = True
    ws.page_margins = PageMargins(left=0.5, right=0.5, top=0.7, bottom=0.7)
    # Repeat the table header on every printed page of a long schedule
    ws.print_title_rows = f"{header_row}:{header_row}"
    ws.oddHeader.right.text = quotation.quote_number
    ws.oddHeader.right.size = 8
    ws.oddHeader.right.color = "9A9382"
    ws.oddFooter.center.text = "Page &P of &N"
    ws.oddFooter.center.size = 8
    ws.oddFooter.center.color = "9A9382"

    # =========================================================
    # SHEET 3 — TERMS & CONDITIONS
    # =========================================================
    tc = wb.create_sheet("Terms & Conditions")
    tc.sheet_view.showGridLines = False
    tc.column_dimensions["A"].width = 3
    tc.column_dimensions["B"].width = 88

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
    tc.page_setup.paperSize = tc.PAPERSIZE_A4
    tc.page_setup.fitToWidth = 1
    tc.page_setup.fitToHeight = 1
    tc.sheet_properties.pageSetUpPr.fitToPage = True
    tc.print_options.horizontalCentered = True
    tc.page_margins = PageMargins(left=0.6, right=0.6, top=0.7, bottom=0.7)
    tc.oddHeader.right.text = quotation.quote_number
    tc.oddHeader.right.size = 8
    tc.oddHeader.right.color = "9A9382"

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
