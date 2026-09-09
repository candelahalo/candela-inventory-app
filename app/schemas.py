from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict

from app.models import DocStatus, MovementType, ProjectStatus


# ---------- Product ----------
class ProductBase(BaseModel):
    sku: str
    name: str
    category: Optional[str] = None
    brand: Optional[str] = None
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


class CustomerCreate(CustomerBase):
    pass


class CustomerOut(CustomerBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime


# ---------- Quotation ----------
class QuotationItemCreate(BaseModel):
    product_id: int
    type_code: Optional[str] = None
    description: Optional[str] = None
    quantity: int
    unit_price: float
    discount_pct: float = 0.0


class QuotationItemOut(QuotationItemCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    line_total: float


class QuotationCreate(BaseModel):
    customer_id: int
    project_id: Optional[int] = None
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
    prepared_by_name: Optional[str] = None
    prepared_by_title: Optional[str] = None
    items: List[QuotationItemCreate]


class QuotationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    quote_number: Optional[str]
    customer_id: int
    project_id: Optional[int]
    status: DocStatus
    version: int
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
    grand_total: float
    vat_amount: float
    total_with_vat: float
    transportation_amount: float
    transportation_is_text: bool


# ---------- Project ----------
class ProjectCreate(BaseModel):
    name: str
    customer_id: int
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
