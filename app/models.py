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
    image_path = Column(String(500))  # e.g. /static/uploads/products/xyz.jpg
    spec_summary = Column(Text)  # short spec block used as default quotation line description
    created_at = Column(DateTime, default=datetime.utcnow)

    stock_movements = relationship("StockMovement", back_populates="product")
    datasheets = relationship("Datasheet", back_populates="product")


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

    # Letterhead / cover-letter fields, matching Candela's standard quotation format
    attention_to = Column(String(255))  # e.g. "Mr. Aaditya Bhagra & Ms. Rashmi Gulti"
    subject = Column(String(255))  # e.g. "Quotation for Landscape Lighting"
    currency = Column(String(16), default="AED")
    scope = Column(String(255), default="Delivered to site including all expenses")
    delivery_time = Column(String(255), default="7-9 weeks from the date of order confirmation and advance payment")
    payment_terms = Column(String(255), default="70% in advance, balance 30% before delivery.")
    freight_charges = Column(Float, default=0.0)  # "Air Freight & Customs" style line
    transportation_charges = Column(String(64), default="500")  # number (e.g. "500") or free text (e.g. "Included")
    vat_percent = Column(Float, default=5.0)
    prepared_by_name = Column(String(120), default="Johns James")
    prepared_by_title = Column(String(120), default="Division Head - Projects")

    created_at = Column(DateTime, default=datetime.utcnow)

    customer = relationship("Customer", back_populates="quotations")
    project = relationship("Project", back_populates="quotations")
    items = relationship("QuotationItem", back_populates="quotation", cascade="all, delete-orphan", order_by="QuotationItem.id")

    @property
    def gross_total(self):
        return round(sum(item.line_total for item in self.items), 2)

    @property
    def total_cost(self):
        """Total cost of goods on this quotation (snapshot costs)."""
        return round(sum(item.line_cost for item in self.items), 2)

    @property
    def total_margin(self):
        """Profit on goods, before freight/transportation and excluding VAT."""
        return round(self.gross_total - self.total_cost, 2)

    @property
    def total_margin_pct(self):
        if not self.gross_total:
            return 0.0
        return round(self.total_margin / self.gross_total * 100, 1)

    @property
    def transportation_amount(self):
        """Numeric value of transportation_charges, or 0 when it's free text
        like 'Included' (which shouldn't be added to the total)."""
        try:
            return round(float(str(self.transportation_charges).strip()), 2)
        except (TypeError, ValueError):
            return 0.0

    @property
    def transportation_is_text(self):
        """True when the field holds words (e.g. 'Included') rather than a figure."""
        try:
            float(str(self.transportation_charges).strip())
            return False
        except (TypeError, ValueError):
            return bool(str(self.transportation_charges or "").strip())

    @property
    def grand_total(self):
        return round(self.gross_total + (self.freight_charges or 0) + self.transportation_amount, 2)

    @property
    def vat_amount(self):
        return round(self.grand_total * (self.vat_percent or 0) / 100, 2)

    @property
    def total_with_vat(self):
        return round(self.grand_total + self.vat_amount, 2)


class QuotationItem(Base):
    __tablename__ = "quotation_items"

    id = Column(Integer, primary_key=True, index=True)
    quotation_id = Column(Integer, ForeignKey("quotations.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    type_code = Column(String(64))  # e.g. "WL1", "BL1" - line reference code shown on the quotation
    description = Column(Text)  # multi-line spec block; defaults from product.spec_summary if left blank
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Float, nullable=False)
    unit_cost = Column(Float, default=0.0)  # snapshot of product cost at quoting time, so margin stays historically accurate
    discount_pct = Column(Float, default=0.0)

    quotation = relationship("Quotation", back_populates="items")
    product = relationship("Product")

    @property
    def line_total(self):
        return round(self.quantity * self.unit_price * (1 - self.discount_pct / 100), 2)

    @property
    def line_cost(self):
        return round(self.quantity * (self.unit_cost or 0), 2)

    @property
    def line_margin(self):
        """Profit in currency on this line, after any discount."""
        return round(self.line_total - self.line_cost, 2)

    @property
    def line_margin_pct(self):
        """Margin as a % of the selling price (not a markup on cost)."""
        if not self.line_total:
            return 0.0
        return round(self.line_margin / self.line_total * 100, 1)


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


class User(Base):
    """A staff login. Roles are a plain string rather than an enum so new
    ones can be added without a schema change."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(120), nullable=False)
    role = Column(String(32), nullable=False, default="sales")
    # Comma-separated screens this user may open. Empty means "use the
    # role default", so existing accounts keep working unchanged.
    permissions = Column(Text, default="")
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Backup(Base):
    """A point-in-time snapshot of the business data, stored as JSON."""
    __tablename__ = "backups"

    id = Column(Integer, primary_key=True, index=True)
    kind = Column(String(16), default="manual")  # "manual" | "auto"
    created_by = Column(String(120))
    payload = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class ActivityLog(Base):
    __tablename__ = "activity_log"

    id = Column(Integer, primary_key=True, index=True)
    entity_type = Column(String(64), nullable=False, index=True)  # "product", "customer", "quotation", ...
    entity_id = Column(Integer, nullable=True)
    entity_label = Column(String(255))  # human-readable name/number for display
    action = Column(String(32), nullable=False)  # "created", "updated", "deleted", "status_changed"
    details = Column(String(500))
    performed_by = Column(String(120), default="Unknown")
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class Datasheet(Base):
    __tablename__ = "datasheets"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)  # e.g. "Igniz Zoom - Track Spotlight"
    brand = Column(String(120))  # e.g. "Halo", "One Light"
    category = Column(String(120))  # e.g. "Track Lighting", "LED Drivers"
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True)
    file_path = Column(String(500), nullable=False)  # e.g. /static/uploads/datasheets/xyz.pdf
    original_filename = Column(String(255))
    uploaded_at = Column(DateTime, default=datetime.utcnow)

    product = relationship("Product", back_populates="datasheets")
