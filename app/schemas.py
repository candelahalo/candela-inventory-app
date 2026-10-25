import re
from datetime import datetime
from typing import Optional, List, Literal
from pydantic import BaseModel, ConfigDict, field_validator

from app.models import DocStatus, MovementType, ProjectStatus


# ---------- Product ----------
class ProductBase(BaseModel):
    sku: str = ""  # empty: made from the name (see app/naming.py)
    name: str
    category: Optional[str] = None
    product_type: Optional[str] = None
    brand: Optional[str] = None
    supplier: Optional[str] = None  # usual supplier (HALO is own brand: varies)
    unit: str = "pcs"
    # Cost as the supplier quotes it plus a landed-cost %; cost_price (AED,
    # landed) is worked out from these on save. Leave cost_amount out to give
    # cost_price in AED.
    cost_currency: str = "AED"
    cost_amount: Optional[float] = None
    landed_pct: Optional[float] = 0.0
    cost_price: float = 0.0
    selling_price: float = 0.0
    reorder_level: int = 0
    is_active: bool = True
    spec_summary: Optional[str] = None
    description: Optional[str] = None  # HALO datasheet texts
    features: Optional[str] = None
    series: Optional[str] = None  # e.g. "CHERUB" - sizes of one series are picked together in a quote
    variant: Optional[str] = None  # this size, e.g. "S"
    options: Optional[dict] = None  # see app/series.py


class ProductCreate(ProductBase):
    pass


class ProductOut(ProductBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    no_datasheet: Optional[bool] = False
    datasheet_mode: Optional[str] = "supplier"
    cost_currency: Optional[str] = "AED"
    image_path: Optional[str] = None
    created_at: datetime


# ---------- Warehouse ----------
class WarehouseBase(BaseModel):
    name: str
    location: Optional[str] = None


class WarehouseCreate(WarehouseBase):
    pass


class WarehouseOut(WarehouseBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


# ---------- Stock Movement ----------
class StockMovementCreate(BaseModel):
    product_id: int
    warehouse_id: int
    project_id: Optional[int] = None
    movement_type: MovementType
    quantity: int
    reference: Optional[str] = None
    notes: Optional[str] = None


class StockMovementOut(StockMovementCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime


class StockLevel(BaseModel):
    product_id: int
    sku: str
    name: str
    category: Optional[str] = None
    product_type: Optional[str] = None
    warehouse_id: int
    warehouse_name: str
    quantity_on_hand: int
    reorder_level: int
    below_reorder: bool


# ---------- Customer ----------
class CustomerBase(BaseModel):
    name: str
    company: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    trn: Optional[str] = None
    category: Optional[Literal["retail", "residential"]] = None
    # company their quotations come from (left out: unchanged / Candelaria for a new one)
    quote_entity: Optional[Literal["candelaria", "candela"]] = None


class CustomerCreate(CustomerBase):
    pass


class CustomerOut(CustomerBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime


# ---------- Quotation ----------
class QuotationItemCreate(BaseModel):
    product_id: Optional[int] = None  # None = custom line, not from the product list
    unit: Optional[str] = None
    image_path: Optional[str] = None
    type_code: Optional[str] = None
    description: Optional[str] = None
    quantity: int
    unit_price: float
    unit_cost: Optional[float] = None  # omitted on create -> snapshotted from the product
    discount_pct: float = 0.0
    runs: Optional[str] = None  # lengths a linear light is made in: "9 + 10 + 15"
    options: Optional[dict] = None  # series product: chosen option codes {"power": "15", ...}
    section: Optional[str] = None  # heading this line sits under


    @field_validator("image_path")
    @classmethod
    def _only_uploaded_photos(cls, v):
        # Only a photo the app itself stored may be referenced
        if v and not re.fullmatch(r"/static/uploads/products/[0-9a-f]{32}\.jpg", v):
            raise ValueError("invalid image path")
        return v or None

    @field_validator("unit")
    @classmethod
    def _short_unit(cls, v):
        return (v or "").strip()[:16] or None

    @field_validator("runs")
    @classmethod
    def _short_runs(cls, v):
        return (v or "").strip()[:255] or None

    @field_validator("section")
    @classmethod
    def _short_section(cls, v):
        return " ".join((v or "").split())[:120] or None

    @field_validator("options")
    @classmethod
    def _small_options(cls, v):
        if not v:
            return None
        return {str(k)[:20]: str(c)[:20] for k, c in list(v.items())[:10]}


class QuotationItemOut(QuotationItemCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    line_total: float
    line_cost: float
    line_margin: float
    line_margin_pct: float


class QuotationCreate(BaseModel):
    customer_id: Optional[int] = None
    # If no customer_id is given, a customer with this name is found or created,
    # so a quotation can be raised for a new client without a separate step.
    customer_name: Optional[str] = None
    project_id: Optional[int] = None
    # If no project_id is given, a project with this name is found or created
    # against the same customer, so a quotation can start a new job directly.
    project_name: Optional[str] = None
    # Bringing in an old quotation: keep its own number and date (new ones only)
    quote_number: Optional[str] = None
    quote_date: Optional[datetime] = None
    # Left empty, these are taken from the project, then the customer
    division: Optional[Literal["lighting", "automation"]] = None
    category: Optional[Literal["retail", "residential"]] = None
    notes: Optional[str] = None
    valid_until: Optional[datetime] = None
    attention_to: Optional[str] = None
    subject: Optional[str] = None
    currency: str = "AED"
    scope: Optional[str] = "Delivered to site including all expenses"
    delivery_time: Optional[str] = "7-9 weeks from the date of order confirmation and advance payment"
    payment_terms: Optional[str] = "70% in advance, balance 30% before delivery."
    freight_charges: float = 0.0
    transportation_charges: str = "500"
    vat_percent: float = 5.0
    prepared_by_name: Optional[str] = "Johns James"
    prepared_by_title: Optional[str] = "Division Head - Projects"
    section_subtotals: bool = False
    consultant: Optional[str] = None
    main_contractor: Optional[str] = None
    section_notes: Optional[dict] = None
    inclusions: Optional[str] = None
    exclusions: Optional[str] = None
    milestones: Optional[str] = None
    proposal_prices: bool = True
    room_matrix: Optional[dict] = None
    proposal_photos: Optional[List[dict]] = None
    proposal_photo_size: str = "M"
    proposal_cover: Optional[str] = None
    proposal_remarks: Optional[dict] = None
    proposal_datasheets: bool = True
    proposal_pages: Optional[List[dict]] = None
    proposal_layout: str = "portrait"
    proposal_hero: Optional[List[str]] = None
    items: List[QuotationItemCreate]


class QuotationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    quote_number: Optional[str]
    customer_id: int
    project_id: Optional[int]
    status: DocStatus
    version: int
    division: Optional[str] = None
    category: Optional[str] = None
    notes: Optional[str]
    valid_until: Optional[datetime]
    attention_to: Optional[str]
    subject: Optional[str]
    currency: str
    scope: Optional[str]
    delivery_time: Optional[str]
    payment_terms: Optional[str]
    freight_charges: float
    transportation_charges: Optional[str]
    vat_percent: float
    prepared_by_name: Optional[str]
    prepared_by_title: Optional[str]
    section_subtotals: Optional[bool] = False
    consultant: Optional[str] = None
    main_contractor: Optional[str] = None
    section_notes: Optional[dict] = None
    inclusions: Optional[str] = None
    exclusions: Optional[str] = None
    milestones: Optional[str] = None
    proposal_prices: Optional[bool] = True
    room_matrix: Optional[dict] = None
    proposal_photos: Optional[List[dict]] = None
    proposal_photo_size: Optional[str] = "M"
    proposal_cover: Optional[str] = None
    proposal_remarks: Optional[dict] = None
    proposal_datasheets: Optional[bool] = True
    proposal_pages: Optional[List[dict]] = None
    proposal_layout: Optional[str] = "portrait"
    proposal_hero: Optional[List[str]] = None
    created_at: datetime
    items: List[QuotationItemOut]
    gross_total: float
    subtotal_before_discount: float
    total_discount: float
    grand_total: float
    vat_amount: float
    total_with_vat: float
    transportation_amount: float
    transportation_is_text: bool
    total_cost: float
    total_margin: float
    total_margin_pct: float


# ---------- Project ----------
class ProjectCreate(BaseModel):
    name: str
    customer_id: int
    division: Optional[Literal["lighting", "automation"]] = None
    category: Optional[Literal["retail", "residential"]] = None
    site_address: Optional[str] = None
    start_date: Optional[datetime] = None
    target_completion_date: Optional[datetime] = None
    notes: Optional[str] = None


class ProjectStatusHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    status: ProjectStatus
    notes: Optional[str]
    changed_at: datetime


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_number: Optional[str]
    name: str
    customer_id: int
    division: Optional[str] = None
    category: Optional[str] = None
    site_address: Optional[str]
    status: ProjectStatus
    start_date: Optional[datetime]
    target_completion_date: Optional[datetime]
    notes: Optional[str]
    created_at: datetime
    status_history: List[ProjectStatusHistoryOut] = []


class ProjectStatusUpdate(BaseModel):
    status: ProjectStatus
    notes: Optional[str] = None


# ---------- Datasheet ----------
class DatasheetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    brand: Optional[str]
    category: Optional[str]
    product_id: Optional[int]
    file_path: str
    original_filename: Optional[str]
    uploaded_at: datetime
    kind: Optional[str] = "supplier"


# ---------- Activity Log ----------
class ActivityLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    entity_type: str
    entity_id: Optional[int]
    entity_label: Optional[str]
    action: str
    details: Optional[str]
    performed_by: str
    created_at: datetime


# ---------- Auth & Users ----------
class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    full_name: str
    role: str
    screens: List[str]


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class UserIn(BaseModel):
    username: str
    password: str
    full_name: Optional[str] = None
    role: str = "office"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    full_name: str
    role: str
    permissions: Optional[str] = ""
    active: bool
    created_at: datetime


class PermissionsIn(BaseModel):
    permissions: List[str]


class ResetPasswordIn(BaseModel):
    new_password: Optional[str] = None


# ---------- Backups ----------
class BackupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    kind: str
    created_by: Optional[str]
    created_at: datetime


# ---------- Supplier orders (purchase orders) ----------
class PurchaseOrderItemIn(BaseModel):
    id: Optional[int] = None  # existing line (keeps what's been received)
    product_id: Optional[int] = None  # empty = not a stock item
    description: Optional[str] = None
    quantity: int
    unit_cost: float = 0.0


class PurchaseOrderIn(BaseModel):
    supplier: str
    supplier_ref: Optional[str] = None
    project_id: Optional[int] = None
    cancelled: bool = False
    order_date: Optional[datetime] = None
    expected_date: Optional[datetime] = None  # ETA arrival
    currency: str = "AED"
    notes: Optional[str] = None
    payment_terms: Optional[str] = None
    advance_paid_date: Optional[datetime] = None
    balance_paid_date: Optional[datetime] = None
    ready_expected: Optional[datetime] = None
    ready_date: Optional[datetime] = None
    ship_mode: Optional[Literal["air", "sea", "road", "courier", "local", "direct"]] = None
    incoterm: Optional[str] = None
    forwarder: Optional[str] = None
    tracking_no: Optional[str] = None
    dispatch_date: Optional[datetime] = None
    arrived_date: Optional[datetime] = None
    customs_agent: Optional[str] = None
    customs_ref: Optional[str] = None
    cleared_date: Optional[datetime] = None
    delivery_planned: Optional[datetime] = None
    delivered_date: Optional[datetime] = None
    delivery_note: Optional[str] = None
    delivered_to: Optional[str] = None
    items: List[PurchaseOrderItemIn]


class PurchaseOrderItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    product_id: Optional[int]
    description: Optional[str]
    quantity: int
    unit_cost: Optional[float] = 0.0
    received_qty: Optional[int] = 0
    delivered_qty: Optional[int] = 0


class PurchaseOrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    po_number: str
    supplier: str
    supplier_ref: Optional[str]
    project_id: Optional[int]
    quotation_id: Optional[int] = None
    status: str
    order_date: Optional[datetime]
    expected_date: Optional[datetime]
    received_date: Optional[datetime]
    currency: Optional[str]
    notes: Optional[str]
    created_at: datetime
    payment_terms: Optional[str] = None
    advance_paid_date: Optional[datetime] = None
    balance_paid_date: Optional[datetime] = None
    ready_expected: Optional[datetime] = None
    ready_date: Optional[datetime] = None
    ship_mode: Optional[str] = None
    incoterm: Optional[str] = None
    forwarder: Optional[str] = None
    tracking_no: Optional[str] = None
    dispatch_date: Optional[datetime] = None
    arrived_date: Optional[datetime] = None
    customs_agent: Optional[str] = None
    customs_ref: Optional[str] = None
    cleared_date: Optional[datetime] = None
    delivery_planned: Optional[datetime] = None
    delivered_date: Optional[datetime] = None
    delivery_note: Optional[str] = None
    delivered_to: Optional[str] = None
    items: List[PurchaseOrderItemOut]
    total: float
    qty_ordered: int
    qty_received: int
    qty_delivered: int
    next_step: Optional[dict] = None
    is_overdue: bool


class ReceiveLine(BaseModel):
    item_id: int
    quantity: int


class ReceiveIn(BaseModel):
    warehouse_id: Optional[int] = None  # needed when product lines are received
    lines: List[ReceiveLine]
    notes: Optional[str] = None


class DeliverIn(BaseModel):
    warehouse_id: Optional[int] = None  # stock is issued from here for product lines
    lines: List[ReceiveLine]
    delivery_note: Optional[str] = None
    delivered_to: Optional[str] = None
    date: Optional[datetime] = None


class IdsIn(BaseModel):
    ids: List[int]



class ProposalTerms(BaseModel):
    inclusions: Optional[str] = None
    exclusions: Optional[str] = None
    milestones: Optional[str] = None


class ProposalSettings(BaseModel):
    """The full automation proposal's own fields, edited on the project page."""
    consultant: Optional[str] = None
    main_contractor: Optional[str] = None
    inclusions: Optional[str] = None
    exclusions: Optional[str] = None
    milestones: Optional[str] = None
    proposal_prices: bool = True
    proposal_photos: Optional[List[dict]] = None
    proposal_photo_size: str = "M"
    proposal_cover: Optional[str] = None
    proposal_remarks: Optional[dict] = None
    proposal_datasheets: bool = True
    proposal_pages: Optional[List[dict]] = None
    proposal_layout: str = "portrait"
    proposal_hero: Optional[List[str]] = None

    @field_validator("proposal_layout")
    @classmethod
    def _layout(cls, v):
        return v if v in ("portrait", "landscape") else "portrait"

    @field_validator("proposal_hero")
    @classmethod
    def _hero(cls, v):
        v = [str(x) for x in (v or []) if isinstance(x, str) and x.startswith("/static/uploads/") and ".." not in x][:3]
        return v or None

    @field_validator("proposal_pages")
    @classmethod
    def _pages(cls, v):
        if not v:
            return None
        out = []
        for pg in v[:40]:
            pg = pg or {}
            layout = pg.get("layout") if pg.get("layout") in ("bleed", "one", "two") else "one"
            imgs = [str(x) for x in (pg.get("images") or []) if isinstance(x, str) and x.startswith("/static/uploads/") and ".." not in x]
            out.append({"layout": layout, "title": str(pg.get("title") or "")[:120], "text": str(pg.get("text") or "")[:600],
                        "images": imgs[:2 if layout == "two" else 1]})
        return out or None

    @field_validator("proposal_cover")
    @classmethod
    def _cover(cls, v):
        v = (v or "").strip()
        if v and (not v.startswith("/static/uploads/") or ".." in v):
            raise ValueError("Cover photo must be an uploaded picture")
        return v or None

    @field_validator("proposal_remarks")
    @classmethod
    def _remarks(cls, v):
        if not v:
            return None
        return {str(k)[:200]: str(t or "")[:5000] for k, t in v.items()}

    @field_validator("proposal_photo_size")
    @classmethod
    def _size(cls, v):
        v = (v or "M").upper()
        return v if v in ("S", "M", "L", "F", "OFF") else "M"
