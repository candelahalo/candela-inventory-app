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


class ProductCreate(ProductBase):
    pass


class ProductOut(ProductBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
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
    created_at: datetime
    items: List[QuotationItemOut]


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
