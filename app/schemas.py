from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict

from app.models import DocStatus, InvoiceStatus, MovementType


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
    notes: Optional[str] = None
    valid_until: Optional[datetime] = None
    items: List[QuotationItemCreate]


class QuotationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    quote_number: Optional[str]
    customer_id: int
    status: DocStatus
    version: int
    notes: Optional[str]
    valid_until: Optional[datetime]
    created_at: datetime
    items: List[QuotationItemOut]


# ---------- Invoice ----------
class InvoiceItemCreate(BaseModel):
    product_id: int
    description: Optional[str] = None
    quantity: int
    unit_price: float
    discount_pct: float = 0.0


class InvoiceItemOut(InvoiceItemCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    line_total: float


class InvoiceCreate(BaseModel):
    customer_id: int
    quotation_id: Optional[int] = None
    due_date: Optional[datetime] = None
    notes: Optional[str] = None
    items: List[InvoiceItemCreate] = []


class InvoiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    invoice_number: Optional[str]
    customer_id: int
    quotation_id: Optional[int]
    status: InvoiceStatus
    due_date: Optional[datetime]
    amount_paid: float
    notes: Optional[str]
    created_at: datetime
    items: List[InvoiceItemOut]


class PaymentUpdate(BaseModel):
    amount: float
