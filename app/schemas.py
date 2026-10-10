import re
from datetime import datetime
from typing import Optional, List, Literal
from pydantic import BaseModel, ConfigDict, field_validator

from app.models import DocStatus, MovementType, ProjectStatus


# ---------- Product ----------
class ProductBase(BaseModel):
    sku: str
    name: str
    category: Optional[str] = None
    product_type: Optional[str] = None
    brand: Optional[str] = None
    supplier: Optional[str] = None  # usual supplier (HALO is own brand: varies)
    unit: str = "pcs"
    cost_price: float = 0.0
    selling_price: float = 0.0
    reorder_level: int = 0
    is_active: bool = True
    spec_summary: Optional[str] = None


class ProductCreate(ProductBase):
    pass


class ProductOut(ProductBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
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
