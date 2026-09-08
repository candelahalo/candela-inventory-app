import enum
from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, Float, DateTime, ForeignKey, Text, Enum, Boolean
)
from sqlalchemy.orm import relationship

from app.database import Base


class DocStatus(str, enum.Enum):
    draft = "draft"
    sent = "sent"
    accepted = "accepted"
    rejected = "rejected"


class MovementType(str, enum.Enum):
    in_ = "in"
    out = "out"
    adjustment = "adjustment"


class ProjectStatus(str, enum.Enum):
    enquiry = "enquiry"
    quoted = "quoted"
    approved = "approved"
    ordered = "ordered"
    delivered = "delivered"
    installed = "installed"
    commissioned = "commissioned"
    closed = "closed"


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    sku = Column(String(64), unique=True, index=True, nullable=False)
    name = Column(String(255), nullable=False)
    category = Column(String(120), index=True)  # e.g. "Downlights", "Smart Switches", "Home Automation Hub"
    brand = Column(String(120))
    unit = Column(String(32), default="pcs")
    cost_price = Column(Float, default=0.0)
    selling_price = Column(Float, default=0.0)
    reorder_level = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    stock_movements = relationship("StockMovement", back_populates="product")


class Warehouse(Base):
    __tablename__ = "warehouses"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    location = Column(String(255))

    stock_movements = relationship("StockMovement", back_populates="warehouse")


class StockMovement(Base):
    __tablename__ = "stock_movements"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), nullable=False)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)  # link stock-out to a project/site
    movement_type = Column(Enum(MovementType), nullable=False)
    quantity = Column(Integer, nullable=False)
    reference = Column(String(255))  # e.g. "PO #123", "Site delivery"
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    product = relationship("Product", back_populates="stock_movements")
    warehouse = relationship("Warehouse", back_populates="stock_movements")
    project = relationship("Project", back_populates="stock_movements")


class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    company = Column(String(255))
    email = Column(String(255))
    phone = Column(String(64))
    address = Column(Text)
    trn = Column(String(64))  # UAE Tax Registration Number
    created_at = Column(DateTime, default=datetime.utcnow)

    quotations = relationship("Quotation", back_populates="customer")
    projects = relationship("Project", back_populates="customer")


class Quotation(Base):
    __tablename__ = "quotations"

    id = Column(Integer, primary_key=True, index=True)
    quote_number = Column(String(64), unique=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    status = Column(Enum(DocStatus), default=DocStatus.draft)
    version = Column(Integer, default=1)
    notes = Column(Text)
    valid_until = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    customer = relationship("Customer", back_populates="quotations")
    project = relationship("Project", back_populates="quotations")
    items = relationship("QuotationItem", back_populates="quotation", cascade="all, delete-orphan")


class QuotationItem(Base):
    __tablename__ = "quotation_items"

    id = Column(Integer, primary_key=True, index=True)
    quotation_id = Column(Integer, ForeignKey("quotations.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    description = Column(String(500))
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Float, nullable=False)
    discount_pct = Column(Float, default=0.0)

    quotation = relationship("Quotation", back_populates="items")
    product = relationship("Product")

    @property
    def line_total(self):
        return round(self.quantity * self.unit_price * (1 - self.discount_pct / 100), 2)


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    project_number = Column(String(64), unique=True, index=True)
    name = Column(String(255), nullable=False)  # e.g. "Villa 44 - Full Home Automation"
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    site_address = Column(Text)
    status = Column(Enum(ProjectStatus), default=ProjectStatus.enquiry, index=True)
    start_date = Column(DateTime)
    target_completion_date = Column(DateTime)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    customer = relationship("Customer", back_populates="projects")
    quotations = relationship("Quotation", back_populates="project")
    stock_movements = relationship("StockMovement", back_populates="project")
    status_history = relationship(
        "ProjectStatusHistory", back_populates="project",
        cascade="all, delete-orphan", order_by="ProjectStatusHistory.changed_at",
    )


class ProjectStatusHistory(Base):
    __tablename__ = "project_status_history"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    status = Column(Enum(ProjectStatus), nullable=False)
    notes = Column(Text)
    changed_at = Column(DateTime, default=datetime.utcnow)

    project = relationship("Project", back_populates="status_history")
