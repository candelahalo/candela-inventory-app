import io
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
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
from app.utils import url_to_disk_path, log_activity, save_product_image
from app.pdf_import import parse_quotation_pdf, product_defs
from app import auth
from app import workflow
from app import submittal
from app.settings import BASE_URL
from datetime import datetime, timedelta
import re

router = APIRouter(prefix="/quotations", tags=["Quotations"],
                   dependencies=[Depends(auth.get_current_user)])

# PDF and Excel open via plain browser navigation (window.open / an <a> href),
# which cannot set an Authorization header. They authenticate with the same
# 60-second download token the backup download uses, so the real session token
# never travels in a URL.
download_router = APIRouter(prefix="/quotations", tags=["Quotations (download)"])
templates = Jinja2Templates(directory="app/templates")

# Profit/margin is ADMIN ONLY. It is tied to the user's role, not to which
# screens they can open, and is removed from every API response here on the
# server - so it cannot be seen even by inspecting the browser.
# Cost and selling prices are fine for everyone.
MARGIN_FIELDS = {"total_margin", "total_margin_pct"}
MARGIN_ITEM_FIELDS = {"line_margin", "line_margin_pct"}


def _out(quotation, current) -> dict:
    """A quotation as JSON, with profit/margin removed for non-admins."""
    payload = schemas.QuotationOut.model_validate(quotation).model_dump(mode="json")
    return _strip_margin(payload, current.role == "admin")


def _strip_margin(payload, admin: bool):
    """Remove profit/margin figures unless the caller is an admin."""
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


QUOTE_PREFIX = "QTN/CND/"
VALIDITY_DAYS = 30
LOCKED_MSG = ("This quotation has been accepted, so it is locked. "
              "Use Revise to make a new version, or set its status back to Sent first.")


def _next_quote_number(db: Session) -> str:
    """Next number after the highest one ever issued - a deleted quotation's
    number is never reused, and deletions can't cause a duplicate-number
    error the way counting rows did."""
    highest = 0
    for (num,) in db.query(models.Quotation.quote_number).all():
        m = re.match(re.escape(QUOTE_PREFIX) + r"(\d+)", num or "")
        if m:
            highest = max(highest, int(m.group(1)))
    return f"{QUOTE_PREFIX}{highest + 1:04d}"


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

    project = models.Project(
        project_number=workflow.next_project_number(db),
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


def _fill_division_category(quotation, project, customer):
    """A quotation left without a division / category takes them from its
    project, then (category only) from its customer. A project that has
    none yet takes them from the quotation, so the two stay in step."""
    if project is not None:
        quotation.division = quotation.division or project.division
        quotation.category = quotation.category or project.category
        project.division = project.division or quotation.division
        project.category = project.category or quotation.category
    if customer is not None:
        quotation.category = quotation.category or customer.category


def _add_items(quotation, payload, db: Session):
    for item in payload.items:
        prod = db.query(models.Product).get(item.product_id) if item.product_id else None
        if item.product_id and not prod:
            raise HTTPException(status_code=400, detail="A line's product no longer exists - pick another or make it a custom line.")
        item_data = item.model_dump()
        if not item_data.get("description") and prod and prod.spec_summary:
            item_data["description"] = quote_spec(prod.spec_summary)
        # Snapshot the cost at quoting time so margin stays accurate even if
        # the product's cost price changes later.
        if item_data.get("unit_cost") is None:
            item_data["unit_cost"] = prod.cost_price if prod else 0.0
        quotation.items.append(models.QuotationItem(**item_data))


MAX_IMPORT_BYTES = 25 * 1024 * 1024


# Fields of the full automation proposal: edited on the project page, never by the quote form
PROPOSAL_FIELDS = ("consultant", "main_contractor", "inclusions", "exclusions", "milestones",
                   "proposal_prices", "proposal_photos", "proposal_photo_size", "proposal_cover", "proposal_remarks", "proposal_datasheets", "proposal_pages",
                   "proposal_layout", "proposal_hero")


def one_line(text, name=""):
    from app.models import one_line as _ol
    return _ol(text, name)


@router.get("/automation-divisions")
def automation_divisions(current: models.User = Depends(auth.get_current_user)):
    """The standard home automation divisions (systems) a quote can take."""
    from app.automation_template import listing
    return listing()


@router.post("/automation-divisions")
def automation_division_lines(payload: dict, db: Session = Depends(get_db),
                              current: models.User = Depends(auth.get_current_user)):
    """Lines for the ticked divisions: each item is a product (added to Products
    the first time, no brand, in its Automation category); drawings,
    installation and fees are typed lines. Quantity 1 - the Rooms table or
    staff set the real numbers."""
    from app.automation_template import DIVISIONS, SHORT
    from app.naming import standard_name, standard_sku
    keys = set(payload.get("keys") or [])
    lines, created = [], []
    for key, title, items in DIVISIONS:
        if key not in keys:
            continue
        section = title.upper()
        for text, category in items:
            if category is None:
                lines.append({"section": section, "product_id": None, "description": text, "unit": "lot",
                              "quantity": 1, "unit_price": 0, "unit_cost": 0, "discount_pct": 0})
                continue
            short = SHORT.get(text, text)  # a short name; the item text is its one-line description
            name = standard_name(short, None, category)
            prod = db.query(models.Product).filter(func.upper(models.Product.name) == name.upper()).first()
            if prod is None:
                base = standard_sku(short, None, category) or "AUTO"
                sku, n = base, 2
                while db.query(models.Product).filter(models.Product.sku == sku).first():
                    sku, n = f"{base[:60]}-{n}", n + 1
                prod = models.Product(sku=sku, name=name, brand=None, category=category, unit="pcs",
                                      cost_price=0.0, selling_price=0.0, reorder_level=0, is_active=True,
                                      spec_summary=text)
                db.add(prod)
                db.flush()
                log_activity(db, current.username, "product", prod.id, f"{prod.sku} — {prod.name}", "created",
                             f"automation division: {title}")
                created.append({"id": prod.id, "sku": prod.sku, "name": prod.name, "category": prod.category})
            elif not prod.is_active:
                prod.is_active = True
            lines.append({"section": section, "product_id": prod.id, "description": one_line(prod.spec_summary, prod.name) or one_line(text, prod.name),
                          "unit": prod.unit or "pcs", "quantity": 1, "unit_price": prod.selling_price or 0,
                          "unit_cost": prod.cost_price or 0, "discount_pct": 0})
    db.commit()
    return {"lines": lines, "created": created}


@router.get("/proposal-terms")
def get_proposal_terms(db: Session = Depends(get_db), current: models.User = Depends(auth.get_current_user)):
    """The standard automation proposal terms (Settings)."""
    from app import proposal_terms
    return proposal_terms.get(db)


@router.put("/proposal-terms")
def put_proposal_terms(payload: schemas.ProposalTerms, db: Session = Depends(get_db),
                       current: models.User = Depends(auth.get_current_user)):
    if current.role != "admin":
        raise HTTPException(status_code=403, detail="Only an admin can change the standard terms.")
    from app import proposal_terms
    proposal_terms.save(db, payload.model_dump(exclude_unset=True))
    log_activity(db, current.username, "settings", None, "Proposal terms", "updated")
    db.commit()
    return proposal_terms.get(db)


@router.get("/{quotation_id}/proposal-settings")
def get_proposal_settings(quotation_id: int, db: Session = Depends(get_db),
                          current: models.User = Depends(auth.get_current_user)):
    """The proposal fields of a quotation, plus the line photos and the standard terms to fall back on."""
    from app import proposal_terms
    from app.proposal import default_photos
    q = db.query(models.Quotation).get(quotation_id)
    if not q:
        raise HTTPException(status_code=404, detail="Quotation not found")
    from app.proposal import build_context
    ctx = build_context(q, proposal_terms.get(db))
    return {**{k: getattr(q, k) for k in PROPOSAL_FIELDS},
            "systems": [{"name": x["name"], "title": x["title"], "auto": "\n".join(x["notes"] + x["auto_remarks"])}
                        for x in ctx["systems"]],
            "proposal_photo_size": q.proposal_photo_size or "M",
            "default_photos": default_photos(q), "standard": proposal_terms.get(db),
            "has_matrix": bool((q.room_matrix or {}).get("floors"))}


@router.put("/{quotation_id}/proposal-settings")
def put_proposal_settings(quotation_id: int, payload: schemas.ProposalSettings, db: Session = Depends(get_db),
                          current: models.User = Depends(auth.get_current_user)):
    """Saved even on an accepted quotation: these change only the presentation, not the prices."""
    q = db.query(models.Quotation).get(quotation_id)
    if not q:
        raise HTTPException(status_code=404, detail="Quotation not found")
    for k, v in payload.model_dump().items():
        if isinstance(v, str):
            v = v.strip() or None
        setattr(q, k, v)
    log_activity(db, current.username, "quotation", q.id, q.quote_number, "updated", "automation proposal")
    db.commit()
    return {"ok": True}


@router.post("/proposal-image")
def proposal_image(file: UploadFile = File(...), current: models.User = Depends(auth.get_current_user)):
    """A photo or diagram for the proposal's photos page; kept in its own shape (not squared)."""
    from app.utils import save_proposal_image
    return {"path": save_proposal_image(file)}


@router.post("/read-rooms")
async def read_rooms(file: UploadFile = File(...), current: models.User = Depends(auth.get_current_user)):
    """Room names and the floor from an architect's layout PDF, for the room matrix."""
    data = await file.read(MAX_IMPORT_BYTES + 1)
    if len(data) > MAX_IMPORT_BYTES:
        raise HTTPException(status_code=400, detail="That PDF is over 25 MB.")
    if not data.startswith(b"%PDF-"):
        raise HTTPException(status_code=400, detail="That file isn't a PDF.")
    from starlette.concurrency import run_in_threadpool
    from app.room_read import read
    try:
        res = await run_in_threadpool(read, data, file.filename or "")
    except Exception:
        raise HTTPException(status_code=400, detail="Couldn't read that PDF.")
    if not res["rooms"]:
        raise HTTPException(status_code=400, detail="No room names found in that PDF - is it a scanned image? Add the rooms by hand.")
    return res


@router.post("/import-pdf")
async def import_pdf(file: UploadFile = File(...), db: Session = Depends(get_db),
                     current: models.User = Depends(auth.get_current_user)):
    """
    Reads an existing Candela quotation PDF and returns the fields for a new
    quotation form - customer, project, terms, every line with its photo.
    The quotation itself isn't saved: the form opens filled in for someone
    to check and save. Every line is linked to a product - one already in
    the list (recognised by its spec) or a new one added now, with the
    spec in the quotation's own format, its photo and quoted price.
    Identical items (the same fitting in two locations) share one product.
    """
    data = await file.read(MAX_IMPORT_BYTES + 1)
    if len(data) > MAX_IMPORT_BYTES:
        raise HTTPException(status_code=400, detail="That PDF is over 25 MB.")
    if not data.startswith(b"%PDF-"):
        raise HTTPException(status_code=400, detail="That file isn't a PDF.")
    products = db.query(models.Product).filter(models.Product.is_active == True).all()  # noqa: E712
    try:
        result = parse_quotation_pdf(data, products, save_product_image)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        raise HTTPException(status_code=400, detail="Couldn't read that PDF. Is it a Candela quotation (not a scan)?")

    # Every line to a product: recognised by its spec fingerprint, or created
    created, by_key = [], {}
    for it in product_defs(result["items"], result.get("division")):
        d = it.pop("_product")
        for k in ("_lead", "_desc", "_brandcol"):
            it.pop(k, None)
        prod = by_key.get(d["key"])
        if prod is None and it.get("product_id"):
            prod = db.query(models.Product).get(it["product_id"])
        if prod is None:
            prod = db.query(models.Product).filter(models.Product.match_key == d["key"][:500]).first()
        if prod is None:
            # Same naming pattern as every other product
            from app.naming import standard_name, standard_sku
            name = standard_name(d["name"], d["brand"], d["category"])
            base = standard_sku(d["name"], d["brand"], d["category"]) or d["sku"] or "ITEM"
            sku, n = base, 2
            while db.query(models.Product).filter(models.Product.sku == sku).first():
                sku, n = f"{base[:60]}-{n}", n + 1
            prod = models.Product(
                sku=sku, name=name, brand=d["brand"], category=d["category"], product_type=d["product_type"],
                unit=it.get("unit") or "pcs", cost_price=0.0, selling_price=it.get("unit_price") or 0.0,
                reorder_level=0, is_active=True, spec_summary=d["spec"], image_path=it.get("image_path"),
                match_key=d["key"][:500])
            db.add(prod)
            db.flush()
            log_activity(db, current.username, "product", prod.id, f"{prod.sku} — {prod.name}", "created",
                         f"from quotation PDF {result.get('original_number') or file.filename or ''}".strip())
            created.append({"id": prod.id, "sku": prod.sku, "name": prod.name, "category": prod.category})
        else:
            if not prod.is_active:
                prod.is_active = True
            if not prod.image_path and it.get("image_path"):
                prod.image_path = it["image_path"]
            if not prod.match_key:
                prod.match_key = d["key"][:500]
        by_key[d["key"]] = prod
        it["product_id"] = prod.id
        it["product_label"] = f"{prod.sku} — {prod.name}"
    result["created_products"] = created
    result["matched_lines"] = len(result["items"])

    # Point at an existing customer / project when the names match
    if result.get("customer_name"):
        c = db.query(models.Customer).filter(func.lower(models.Customer.name) == result["customer_name"].lower()).first()
        result["customer_id"] = c.id if c else None
    if result.get("project_name"):
        p = db.query(models.Project).filter(func.lower(models.Project.name) == result["project_name"].lower()).first()
        result["project_id"] = p.id if p else None
    log_activity(db, current.username, "quotation", None, file.filename or "PDF", "imported",
                 f"read {len(result['items'])} lines from {result.get('original_number') or 'a PDF'} (not saved yet)")
    db.commit()
    return result


# Spec lines left out of a quote line's description (kept on the product and its datasheet)
QUOTE_HIDE = re.compile(r"^\s*(model|safety class|mounting( type)?|tilt( angle)?|rotation( angle)?|housing|operating temp\w*)\s*:", re.I)


def quote_spec(spec):
    return "\n".join(l for l in (spec or "").split("\n") if not QUOTE_HIDE.match(l))


@router.post("/", status_code=201)
def create_quotation(payload: schemas.QuotationCreate, db: Session = Depends(get_db), current: models.User = Depends(auth.get_current_user)):
    customer = _resolve_customer(payload, db, current.username)
    if not payload.items:
        raise HTTPException(status_code=400, detail="Quotation must have at least one item")
    project = _resolve_project(payload, customer, db, current.username)

    data = payload.model_dump(exclude={"items", "customer_name", "customer_id",
                                       "project_name", "project_id", "quote_number", "quote_date", *PROPOSAL_FIELDS})
    if not data.get("valid_until"):
        data["valid_until"] = datetime.utcnow() + timedelta(days=VALIDITY_DAYS)
    number = (payload.quote_number or "").strip()[:64] or None
    if number and db.query(models.Quotation).filter(models.Quotation.quote_number == number).first():
        raise HTTPException(status_code=400, detail=f"There's already a quotation numbered {number}.")
    quotation = models.Quotation(quote_number=number or _next_quote_number(db),
                                 customer_id=customer.id,
                                 **data)
    if payload.quote_date:
        quotation.created_at = payload.quote_date
    quotation.project = project
    _fill_division_category(quotation, project, customer)
    _add_items(quotation, payload, db)

    db.add(quotation)
    db.flush()
    log_activity(db, current.username, "quotation", quotation.id, quotation.quote_number, "created",
                 f"for {customer.name}" + (f" · {project.project_number}" if project else ""))
    workflow.on_quotation_saved(db, quotation, current.username, created=True)
    db.commit()
    db.refresh(quotation)
    return _out(quotation, current)


@router.get("/{quotation_id}")
def get_quotation(quotation_id: int, db: Session = Depends(get_db), current: models.User = Depends(auth.get_current_user)):
    quotation = db.query(models.Quotation).get(quotation_id)
    if not quotation:
        raise HTTPException(status_code=404, detail="Quotation not found")
    payload = schemas.QuotationOut.model_validate(quotation).model_dump(mode="json")
    return _strip_margin(payload, current.role == "admin")


@router.put("/{quotation_id}")
def update_quotation(quotation_id: int, payload: schemas.QuotationCreate, db: Session = Depends(get_db), current: models.User = Depends(auth.get_current_user)):
    quotation = db.query(models.Quotation).get(quotation_id)
    if not quotation:
        raise HTTPException(status_code=404, detail="Quotation not found")
    if quotation.status == models.DocStatus.accepted:
        raise HTTPException(status_code=400, detail=LOCKED_MSG)
    customer = _resolve_customer(payload, db, current.username)
    if not payload.items:
        raise HTTPException(status_code=400, detail="Quotation must have at least one item")
    project = _resolve_project(payload, customer, db, current.username)
    old_project_id = quotation.project_id

    data = payload.model_dump(exclude={"items", "customer_name", "customer_id",
                                       "project_name", "project_id", "quote_number", "quote_date", *PROPOSAL_FIELDS})
    for key, value in data.items():
        setattr(quotation, key, value)
    if payload.quote_date:
        quotation.created_at = payload.quote_date
    quotation.customer_id = customer.id
    quotation.project = project
    _fill_division_category(quotation, project, customer)

    quotation.items.clear()
    db.flush()
    _add_items(quotation, payload, db)

    log_activity(db, current.username, "quotation", quotation.id, quotation.quote_number, "updated")
    if project and project.id != old_project_id:
        workflow.on_quotation_saved(db, quotation, current.username, created=True)
    db.commit()
    db.refresh(quotation)
    return _out(quotation, current)


@router.post("/draft/{fmt}")
def draft_document(fmt: str, payload: schemas.QuotationCreate, editing_id: Optional[int] = None,
                   db: Session = Depends(get_db), current: models.User = Depends(auth.get_current_user)):
    """
    Preview / PDF / Excel of a quotation exactly as it is in the edit form,
    including changes that haven't been saved yet.

    It runs the same steps as Save (so the document is identical to what
    Save would produce), renders the file, then rolls the whole transaction
    back - nothing is stored, not even a new customer or project typed into
    the form.
    """
    if fmt not in ("pdf", "excel"):
        raise HTTPException(status_code=404, detail="Format must be pdf or excel")
    if not payload.items:
        raise HTTPException(status_code=400, detail="Add at least one line item")
    try:
        customer = _resolve_customer(payload, db, current.username)
        project = _resolve_project(payload, customer, db, current.username)
        data = payload.model_dump(exclude={"items", "customer_name", "customer_id",
                                           "project_name", "project_id", "quote_number", "quote_date", *PROPOSAL_FIELDS})
        if editing_id:
            quotation = db.query(models.Quotation).get(editing_id)
            if not quotation:
                raise HTTPException(status_code=404, detail="Quotation not found")
            for key, value in data.items():
                setattr(quotation, key, value)
            if payload.quote_date:
                quotation.created_at = payload.quote_date
            quotation.items.clear()
            db.flush()
        else:
            quotation = models.Quotation(quote_number=(payload.quote_number or "").strip() or _next_quote_number(db), **data)
            if payload.quote_date:
                quotation.created_at = payload.quote_date
            db.add(quotation)
        quotation.customer = customer
        quotation.project = project
        _add_items(quotation, payload, db)
        db.flush()
        db.refresh(quotation)

        if fmt == "pdf":
            return _quotation_pdf_response(quotation, db, inline=True)
        return _quotation_excel_response(quotation, db)
    finally:
        db.rollback()


@router.post("/bulk-delete")
def bulk_delete_quotations(payload: schemas.IdsIn, db: Session = Depends(get_db),
                           current: models.User = Depends(auth.get_current_user)):
    """Deletes the ticked quotations, the same way as deleting them one by one."""
    quotes = db.query(models.Quotation).filter(models.Quotation.id.in_(payload.ids)).all()
    if not quotes:
        raise HTTPException(status_code=400, detail="Nothing selected.")
    for q in quotes:
        log_activity(db, current.username, "quotation", q.id, q.quote_number, "deleted", "deleted with others (bulk)")
        if q.project is not None:
            workflow.note_on_project(db, q.project, f"{q.quote_number} deleted")
        db.delete(q)
    db.commit()
    return {"deleted": len(quotes)}


@router.post("/line-preview/{product_id}")
def product_line_preview(product_id: int, payload: schemas.ProductCreate, db: Session = Depends(get_db),
                         current: models.User = Depends(auth.get_current_user)):
    """How a product looks as a quotation line - with the edits on the
    product page, saved or not. Nothing is stored."""
    saved = db.query(models.Product).get(product_id)
    if not saved:
        raise HTTPException(status_code=404, detail="Product not found")
    # Unsaved copies, never added to the database session
    prod = models.Product(id=saved.id, sku=payload.sku, name=payload.name, unit=payload.unit or "pcs",
                          image_path=saved.image_path, spec_summary=payload.spec_summary)
    q = models.Quotation(quote_number="PREVIEW", subject=f"Preview - {payload.name}", currency="AED",
                         vat_percent=5.0, freight_charges=0.0, transportation_charges="")
    q.items = [models.QuotationItem(product_id=saved.id, product=prod, description=payload.spec_summary,
                                    quantity=1, unit_price=payload.selling_price or 0.0, unit_cost=0.0,
                                    discount_pct=0.0)]
    try:
        return _quotation_pdf_response(q, db, inline=True, items_only=True)
    finally:
        db.expunge_all()
        db.rollback()


@router.delete("/{quotation_id}", status_code=204)
def delete_quotation(quotation_id: int, db: Session = Depends(get_db), current: models.User = Depends(auth.get_current_user)):
    quotation = db.query(models.Quotation).get(quotation_id)
    if not quotation:
        raise HTTPException(status_code=404, detail="Quotation not found")
    log_activity(db, current.username, "quotation", quotation.id, quotation.quote_number, "deleted")
    if quotation.project is not None:
        workflow.note_on_project(db, quotation.project, f"{quotation.quote_number} deleted")
    db.delete(quotation)
    db.commit()
    return None


@router.post("/{quotation_id}/status/{new_status}")
def update_status(quotation_id: int, new_status: models.DocStatus, db: Session = Depends(get_db), current: models.User = Depends(auth.get_current_user)):
    quotation = db.query(models.Quotation).get(quotation_id)
    if not quotation:
        raise HTTPException(status_code=404, detail="Quotation not found")
    old = quotation.status
    if old == new_status:
        return _out(quotation, current)
    quotation.status = new_status
    log_activity(db, current.username, "quotation", quotation.id, quotation.quote_number,
                 "status_changed", f"{old.value} → {new_status.value}")
    workflow.on_quotation_status(db, quotation, old, new_status, current.username)
    db.commit()
    db.refresh(quotation)
    return _out(quotation, current)


@router.post("/{quotation_id}/revise", status_code=201)
def revise_quotation(quotation_id: int, db: Session = Depends(get_db), current: models.User = Depends(auth.get_current_user)):
    """Make a new version of a quotation (e.g. QTN/CND/0012-R1) as a draft,
    copying every line, so the original stays exactly as the client saw it."""
    original = db.query(models.Quotation).get(quotation_id)
    if not original:
        raise HTTPException(status_code=404, detail="Original quotation not found")

    base = re.sub(r"-R\d+$", "", original.quote_number or "")
    existing = {n for (n,) in db.query(models.Quotation.quote_number)
                .filter(models.Quotation.quote_number.like(base + "-R%")).all()}
    rev = 1
    while f"{base}-R{rev}" in existing:
        rev += 1

    copy_fields = ["customer_id", "project_id", "division", "category", "notes", "attention_to", "subject", "currency", "scope",
                   "delivery_time", "payment_terms", "freight_charges", "transportation_charges",
                   "vat_percent", "prepared_by_name", "prepared_by_title", "section_subtotals",
                   "consultant", "main_contractor", "section_notes", "inclusions", "exclusions", "milestones",
                   "proposal_prices", "room_matrix", "proposal_photos", "proposal_photo_size",
                   "proposal_cover", "proposal_remarks", "proposal_datasheets", "proposal_pages",
                   "proposal_layout", "proposal_hero"]
    new_quote = models.Quotation(
        quote_number=f"{base}-R{rev}",
        version=(original.version or 1) + 1,
        status=models.DocStatus.draft,
        valid_until=datetime.utcnow() + timedelta(days=VALIDITY_DAYS),
        **{f: getattr(original, f) for f in copy_fields},
    )
    for item in original.items:
        new_quote.items.append(models.QuotationItem(
            product_id=item.product_id, unit=item.unit, image_path=item.image_path,
            type_code=item.type_code, description=item.description,
            quantity=item.quantity, unit_price=item.unit_price, unit_cost=item.unit_cost,
            discount_pct=item.discount_pct, runs=item.runs, options=item.options, section=item.section))
    db.add(new_quote)
    db.flush()
    log_activity(db, current.username, "quotation", new_quote.id, new_quote.quote_number, "created",
                 f"revision of {original.quote_number}")
    if new_quote.project_id:
        db.refresh(new_quote)
        workflow.note_on_project(db, new_quote.project, f"{new_quote.quote_number} prepared (revision of {original.quote_number})")
    db.commit()
    db.refresh(new_quote)
    return _out(new_quote, current)


@download_router.get("/{quotation_id}/pdf")
def quotation_pdf(quotation_id: int, token: str = Query(...), preview: bool = False, db: Session = Depends(get_db)):
    auth.get_download_user_from_token(token, db)
    quotation = db.query(models.Quotation).get(quotation_id)
    if not quotation:
        raise HTTPException(status_code=404, detail="Quotation not found")
    return _quotation_pdf_response(quotation, db, inline=preview)


def _quotation_pdf_response(quotation, db: Session, inline: bool = False, items_only: bool = False):
    pdf_bytes = _quotation_pdf_bytes(quotation, db, items_only)
    filename = f"{quotation.quote_number.replace('/', '-')}.pdf"
    # inline opens it in the browser's PDF viewer instead of downloading
    disposition = "inline" if inline else "attachment"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'{disposition}; filename="{filename}"'},
    )


def _datasheet_links(quotation, db: Session):
    """product id -> link to the datasheet that goes with it (see
    app/datasheet_pick.py). "Not needed" / missing: no link."""
    from app.datasheet_pick import latest_by_kind, pick
    products = {i.product_id: i.product for i in quotation.items if i.product_id and i.product}
    latest = latest_by_kind(db, products)
    links = {}
    for pid, p in products.items():
        what, sheet = pick(p, latest)
        if what == "file":
            links[pid] = f"{BASE_URL}/datasheets/{sheet.id}/preview"
        elif what == "auto":
            links[pid] = f"{BASE_URL}/datasheets/halo/{pid}?auto=1"
    return links


def _quotation_pdf_bytes(quotation, db: Session, items_only: bool = False):
    # The product name in the document links straight to its datasheet
    datasheet_links = _datasheet_links(quotation, db)

    from app.entity import for_quotation
    html_str = templates.get_template("quotation_pdf.html").render(
        {"q": quotation, "request": None, "datasheet_links": datasheet_links, "items_only": items_only,
         "ent": for_quotation(quotation)}
    )
    return HTML(string=html_str, base_url=".").write_pdf()


@download_router.get("/{quotation_id}/proposal")
def quotation_proposal(quotation_id: int, token: str = Query(...), preview: bool = False, full: bool = False,
                       db: Session = Depends(get_db)):
    """By system (home automation): a table per section with its scope notes,
    the price summary and the design matrix. With full=1 (from the project page)
    the whole proposal: photo cover, letter, datasheets, general remarks, scope,
    quantities by system, conclusion, design matrix, payment terms and approval."""
    auth.get_download_user_from_token(token, db)
    quotation = db.query(models.Quotation).get(quotation_id)
    if not quotation:
        raise HTTPException(status_code=404, detail="Quotation not found")
    from app import proposal_pdf
    pdf_bytes = proposal_pdf.build(quotation, db, full)
    filename = f"{'Technical-Submittal' if full else 'Quotation'}-{quotation.quote_number.replace('/', '-')}.pdf"
    disposition = "inline" if preview else "attachment"
    return StreamingResponse(io.BytesIO(pdf_bytes), media_type="application/pdf",
                             headers={"Content-Disposition": f'{disposition}; filename="{filename}"'})


@router.get("/{quotation_id}/submittal-check")
def submittal_check(quotation_id: int, db: Session = Depends(get_db)):
    """Items that have no datasheet yet, so the user is warned before the
    submittal is made."""
    quotation = db.query(models.Quotation).get(quotation_id)
    if not quotation:
        raise HTTPException(status_code=404, detail="Quotation not found")
    return {"missing": submittal.missing(quotation, db)}


@download_router.get("/{quotation_id}/submittal")
def quotation_submittal(quotation_id: int, token: str = Query(...), preview: bool = False,
                        db: Session = Depends(get_db)):
    """The quotation followed by every product's datasheet, stamped."""
    auth.get_download_user_from_token(token, db)
    quotation = db.query(models.Quotation).get(quotation_id)
    if not quotation:
        raise HTTPException(status_code=404, detail="Quotation not found")
    pdf_bytes = submittal.build(quotation, db, _quotation_pdf_bytes(quotation, db))
    filename = f"Submittal-{quotation.quote_number.replace('/', '-')}.pdf"
    disposition = "inline" if preview else "attachment"
    return StreamingResponse(io.BytesIO(pdf_bytes), media_type="application/pdf",
                             headers={"Content-Disposition": f'{disposition}; filename="{filename}"'})


@download_router.get("/{quotation_id}/excel")
def quotation_excel(quotation_id: int, token: str = Query(...), db: Session = Depends(get_db)):
    auth.get_download_user_from_token(token, db)
    quotation = db.query(models.Quotation).get(quotation_id)
    if not quotation:
        raise HTTPException(status_code=404, detail="Quotation not found")
    return _quotation_excel_response(quotation, db)


def _quotation_excel_response(quotation, db: Session):
    # Clickable product names in the sheet, to each product's datasheet
    datasheet_links = _datasheet_links(quotation, db)

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
    FONT = "Arial"
    FONT_MONO = "Arial"

    center = Alignment(horizontal="center", vertical="center")
    center_wrap = Alignment(horizontal="center", vertical="center", wrap_text=True)
    left_wrap = Alignment(horizontal="left", vertical="top", wrap_text=True)
    thin = Side(style="thin", color=LINE)
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    thin_bottom = Border(bottom=Side(style="thin", color=INK))

    from app.entity import for_quotation
    ent = for_quotation(quotation)

    def add_logo(ws, cell="A1", height=40):
        logo_path = ent["logo"]
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

    add_logo(cover, "B2", height=54)
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

    cust = quotation.customer.company or quotation.customer.name
    pairs = [("CUSTOMER", cust)]
    if quotation.attention_to and quotation.attention_to != cust:
        pairs.append(("ATTENTION", quotation.attention_to))
    if quotation.project:
        pairs.append(("PROJECT", quotation.project.name))
    if len(pairs) % 2:
        pairs.append(("", ""))
    meta = [("QUOTATION NO.", quotation.quote_number, "DATE", quotation.created_at.strftime("%d %B %Y"))] + \
        [(pairs[i][0], pairs[i][1], pairs[i + 1][0], pairs[i + 1][1]) for i in range(0, len(pairs), 2)]
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
    cover[f"B{r}"] = "FOR " + ent["name"].upper()
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
    widths = {"A": 4, "B": 10, "C": 37, "D": 7, "E": 6, "F": 11, "G": 16}
    for col, w in widths.items():
        ws.column_dimensions[col].width = w

    add_logo(ws, "A1")
    ws.row_dimensions[1].height = 34
    ws.merge_cells("C1:G1")
    ws["C1"] = quotation.quote_number
    ws["C1"].font = Font(name=FONT_MONO, size=9, color=FAINT)
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
    spec_font = InlineFont(rFont=FONT, b=False, sz=8.5, color=MUTED)

    row = header_row + 1
    sec_fill = PatternFill(start_color="F3EEE2", end_color="F3EEE2", fill_type="solid")
    cur_sec, sec_start = None, None

    def section_subtotal(r, name, first, last):
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=6)
        lc = ws.cell(row=r, column=1, value=f"Subtotal — {name}")
        lc.font = Font(name=FONT, size=9, bold=True, color=INK)
        lc.alignment = Alignment(horizontal="right", vertical="center")
        vc = ws.cell(row=r, column=7, value=f"=SUMPRODUCT(E{first}:E{last},F{first}:F{last})")
        vc.font = Font(name=FONT, size=9, bold=True, color=INK)
        vc.number_format = '#,##0.00'
        vc.alignment = center

    for idx, item in enumerate(quotation.items, start=1):
        product = item.product
        # Section heading (and the previous section's subtotal) when the section changes
        if item.section != cur_sec:
            if cur_sec and quotation.section_subtotals:
                section_subtotal(row, cur_sec, sec_start, row - 1)
                row += 1
            cur_sec = item.section
            if cur_sec:
                ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=7)
                hc = ws.cell(row=row, column=1, value=cur_sec.upper())
                hc.font = Font(name=FONT, size=9.5, bold=True, color=INK)
                hc.fill = sec_fill
                hc.alignment = Alignment(horizontal="left", vertical="center", indent=1)
                ws.row_dimensions[row].height = 20
                row += 1
            sec_start = row
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
        if item.print_description:
            blocks.append(TextBlock(spec_font, "\n" + item.print_description))
        if item.runs:
            blocks.append(TextBlock(spec_font, "\nRuns: " + item.runs_text))

        desc_cell = ws.cell(row=row, column=3)
        desc_cell.value = CellRichText(*blocks)
        desc_cell.font = Font(name=FONT, size=10, color=INK)
        desc_cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        desc_cell.border = border
        if ds_url:
            desc_cell.hyperlink = ds_url
        if fill: desc_cell.fill = fill

        for col, val in [(4, item.unit or (product.unit if product else "pcs")), (5, item.quantity),
                          (6, round(item.unit_price, 2))]:
            c = ws.cell(row=row, column=col, value=val)
            c.alignment = center
            c.border = border
            c.font = Font(name=FONT, size=9.5, color=INK)
            if fill: c.fill = fill
            if col == 6:
                c.number_format = '#,##0.00'

        # Line total is the list price (qty × price). Any discount is taken
        # off once in the totals block below, where it is far more visible
        # to the client than a percentage buried in each row.
        total_cell = ws.cell(row=row, column=7)
        total_cell.value = f"=E{row}*F{row}"
        total_cell.alignment = center
        total_cell.border = border
        total_cell.font = Font(name=FONT, size=9.5, color=INK)
        total_cell.number_format = '#,##0.00'
        if fill: total_cell.fill = fill

        b = ws.cell(row=row, column=2); b.border = border
        if fill: b.fill = fill

        # Size the row to fit the spec text so nothing gets clipped
        spec_lines = (item.print_description or "").count("\n") + 1 if item.print_description else 0
        spec_lines += 1 if item.runs else 0
        ws.row_dimensions[row].height = max(62, 26 + spec_lines * 11)

        line_img = item.image_path or (product.image_path if product else None)
        if line_img:
            disk_path = url_to_disk_path(line_img)
            if os.path.exists(disk_path):
                try:
                    xl_img = XLImage(disk_path)
                    xl_img.height = 52
                    xl_img.width = 52
                    ws.add_image(xl_img, f"B{row}")
                except Exception:
                    pass
        row += 1

    if cur_sec and quotation.section_subtotals:
        section_subtotal(row, cur_sec, sec_start, row - 1)
        row += 1
    first_item_row = header_row + 1
    last_item_row = row - 1

    # Each total is keyed explicitly rather than matched on its label -
    # "Subtotal" and "Subtotal (VAT excl.)" are different lines and string
    # matching confused the two.
    rows_by_key = {}
    money_fmt = f'#,##0.00 "{quotation.currency}"'

    # Standard, short totals: Subtotal, Discount (if any), Delivery (if any),
    # VAT, Total.
    delivery_amount = round((quotation.freight_charges or 0) + quotation.transportation_amount, 2)
    delivery_text = quotation.transportation_charges if (quotation.transportation_is_text and not delivery_amount) else None

    spec = [("items_subtotal", "Subtotal", False)]
    if abs(quotation.total_discount) >= 0.01:
        spec.append(("discount", "Discount", False))
    if delivery_amount or delivery_text:
        spec.append(("delivery", "Delivery", False))
    spec.append(("vat", f"VAT {quotation.vat_percent:g}%", False))
    spec.append(("total", "Total", True))

    row += 1
    for key, label, is_grand in spec:
        ws.merge_cells(start_row=row, start_column=5, end_row=row, end_column=6)
        lbl_cell = ws.cell(row=row, column=5, value=label)
        val_cell = ws.cell(row=row, column=7)
        rows_by_key[key] = row

        R = rows_by_key
        if key == "items_subtotal":
            # qty x price of the item rows only (section headings / subtotals have neither)
            val_cell.value = f"=SUMPRODUCT(E{first_item_row}:E{last_item_row},F{first_item_row}:F{last_item_row})"
        elif key == "discount":
            val_cell.value = -quotation.total_discount
        elif key == "delivery":
            val_cell.value = delivery_text if delivery_text else delivery_amount
        elif key == "vat":
            parts = [f"G{R['items_subtotal']}"]
            if "discount" in R:
                parts.append(f"G{R['discount']}")
            if "delivery" in R and not delivery_text:
                parts.append(f"G{R['delivery']}")
            val_cell.value = f"=({'+'.join(parts)})*{quotation.vat_percent / 100}"
        else:
            parts = [f"G{R['items_subtotal']}"]
            if "discount" in R:
                parts.append(f"G{R['discount']}")
            if "delivery" in R and not delivery_text:
                parts.append(f"G{R['delivery']}")
            parts.append(f"G{R['vat']}")
            val_cell.value = "=" + "+".join(parts)

        if not (key == "delivery" and delivery_text):
            val_cell.number_format = money_fmt

        colour = "2E7D52" if key == "discount" else (INK if is_grand else MUTED)
        f = Font(name=FONT, bold=True, size=12 if is_grand else 10, color=colour)
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
            f"Once delivered, goods are no longer the responsibility of {ent['name']} and cannot be returned or refunded.",
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
