import enum
from datetime import datetime

from sqlalchemy import (
    JSON, Column, Integer, String, Float, DateTime, ForeignKey, Text, Enum, Boolean
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
    category = Column(String(120), index=True)  # HALO category, e.g. "Recessed Invisible"
    product_type = Column(String(40), index=True)  # e.g. "Spotlight", "Downlight", "Strip Light"
    brand = Column(String(120))
    supplier = Column(String(255))  # usual supplier; HALO is our own brand, made by several suppliers
    # Fingerprint of the spec, so a product brought in from a PDF quotation is
    # recognised the next time the same item appears
    match_key = Column(String(500), index=True)
    unit = Column(String(32), default="pcs")
    # Cost as the supplier quotes it (AED, USD or EUR) plus a landed-cost %
    # for freight, duty and clearing. cost_price is the result in AED, at the
    # rate in Settings; it is what profit uses. Supplier orders use the plain
    # supplier price (cost_amount).
    cost_currency = Column(String(3), default="AED")
    cost_amount = Column(Float)
    landed_pct = Column(Float, default=0.0)
    cost_price = Column(Float, default=0.0)
    selling_price = Column(Float, default=0.0)
    reorder_level = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    image_path = Column(String(500))  # e.g. /static/uploads/products/xyz.jpg
    spec_summary = Column(Text)  # short spec block used as default quotation line description
    no_datasheet = Column(Boolean, default=False)  # e.g. accessories: the submittal doesn't ask for one
    # Which datasheet goes out with this product: "halo" (made automatically
    # in the HALO layout - the default), "supplier" (the uploaded PDF) or
    # "none" (e.g. accessories). no_datasheet mirrors "none".
    datasheet_mode = Column(String(16), default="supplier", nullable=False)
    description = Column(Text)  # HALO sheet page 2: short description
    features = Column(Text)  # HALO sheet page 2: product features
    # A series is several products picked as one in a quote (CHERUB S / M / L / XL);
    # variant is this one's size within it. options: what is chosen on the quote
    # line and how the ordering code is made, see app/series.py.
    series = Column(String(120), index=True)
    variant = Column(String(40))
    options = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)

    stock_movements = relationship("StockMovement", back_populates="product")
    datasheets = relationship("Datasheet", back_populates="product")


class ExchangeRate(Base):
    """AED for one unit of a currency, set in Settings (e.g. EUR -> 4.02)."""
    __tablename__ = "exchange_rates"

    currency = Column(String(3), primary_key=True)
    rate = Column(Float, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow)
    updated_by = Column(String(64))


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
    category = Column(String(20), index=True)  # "retail" or "residential"
    # Company their quotations come from: "candelaria" (all) or "candela" (e.g. Infinia), see app/entity.py
    quote_entity = Column(String(20), default="candelaria", nullable=False)
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
    division = Column(String(20), index=True)  # "lighting" or "automation"
    category = Column(String(20), index=True)  # "retail" or "residential"
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
    section_subtotals = Column(Boolean, default=False, nullable=False)  # a subtotal after each section
    # Proposal by system (automation): see templates/quotation_proposal.html
    consultant = Column(String(255))
    main_contractor = Column(String(255))
    section_notes = Column(JSON)  # {"HOME AUTOMATION": "We have considered ...\n..."}
    inclusions = Column(Text)
    exclusions = Column(Text)
    milestones = Column(Text)  # one per line: "35% advance against design"
    proposal_prices = Column(Boolean, default=True, nullable=False)  # unit prices in the proposal
    # Rooms per floor x products: {"cols": ["12", ...product ids], "floors": [{"name": "Ground Floor",
    #   "rooms": [{"name": "Family Living", "q": {"12": 2}}]}]}; column totals are the line quantities
    room_matrix = Column(JSON)
    items = relationship("QuotationItem", back_populates="quotation", cascade="all, delete-orphan", order_by="QuotationItem.id")

    @property
    def gross_total(self):
        return round(sum(item.line_total for item in self.items), 2)

    @property
    def subtotal_before_discount(self):
        """List price total, before any line discounts are applied."""
        return round(sum(item.quantity * item.unit_price for item in self.items), 2)

    @property
    def total_discount(self):
        """Total saving across all lines - shown as its own deduction line
        on the quotation so the client can see what they've been given.

        Summed from each line's own discount amount rather than diffing
        subtotal_before_discount against gross_total: those two are each
        rounded independently (once per line, once as a whole), so with
        unit prices carrying 3+ decimal places that diff can land on a
        stray +/-0.01 even when every discount_pct is 0."""
        return round(sum(item.line_discount for item in self.items), 2)

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


LENGTH_UNITS = ("m", "mtr", "mtrs", "meter", "meters", "metre", "metres", "mm", "cm", "rm", "lm")


def parse_runs(text):
    """[9.0, 10.0, 15.0] from "9 + 10 + 15" / "9m, 10m, 15m"; "2 x 10" counts
    as two runs of 10. None when it isn't a list of lengths."""
    import re
    parts = [p.strip() for p in re.split(r"[+,;&]", text or "") if p.strip()]
    nums = []
    for p in parts:
        m = re.fullmatch(r"(?:(\d+)\s*[x×*]\s*)?(\d+(?:\.\d+)?)\s*[a-zA-Z]*\.?", p)
        if not m:
            return None
        nums += [float(m.group(2))] * int(m.group(1) or 1)
    return nums or None


def format_runs(text, unit=None):
    if not (text or "").strip():
        return ""
    nums = parse_runs(text)
    if not nums:
        return text.strip()
    u = unit if (unit or "").lower() in LENGTH_UNITS else "m"
    f = lambda n: f"{n:g}"  # noqa: E731
    shown = " + ".join(f"{f(n)} {u}" for n in nums)
    return shown + (f" = {f(sum(nums))} {u}" if len(nums) > 1 else "")


class QuotationItem(Base):
    __tablename__ = "quotation_items"

    id = Column(Integer, primary_key=True, index=True)
    quotation_id = Column(Integer, ForeignKey("quotations.id"), nullable=False)
    # Empty for a custom line (something not in the product list, e.g. a
    # stretch ceiling or a line brought in from an old PDF quotation)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True)
    unit = Column(String(16))  # overrides the product's unit when set ("pcs", "m")
    image_path = Column(String(255))  # this line's own photo; otherwise the product's
    type_code = Column(String(64))  # e.g. "WL1", "BL1" - line reference code shown on the quotation
    description = Column(Text)  # multi-line spec block; defaults from product.spec_summary if left blank
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Float, nullable=False)
    unit_cost = Column(Float, default=0.0)  # snapshot of product cost at quoting time, so margin stays historically accurate
    discount_pct = Column(Float, default=0.0)
    # Lengths a linear / custom light is made in, as typed: "9 + 10 + 15"
    runs = Column(String(255))
    options = Column(JSON)  # chosen options {"power": "15", "beam": "36", ...} for a series product
    section = Column(String(120))  # heading this line sits under, e.g. "FRONT END MATERIALS"

    quotation = relationship("Quotation", back_populates="items")
    product = relationship("Product")

    @property
    def runs_text(self):
        """Runs for the quotation: "9 m + 10 m + 15 m = 34 m" (or as typed)."""
        return format_runs(self.runs, self.unit or (self.product.unit if self.product else None))

    @property
    def line_total(self):
        return round(self.quantity * self.unit_price * (1 - self.discount_pct / 100), 2)

    @property
    def line_discount(self):
        """Currency amount saved on this line. Exactly 0.0 when discount_pct
        is 0, regardless of unit_price's decimal precision - multiplying by
        zero can't produce rounding residue the way diffing two rounded
        totals can."""
        return round(self.quantity * self.unit_price * self.discount_pct / 100, 2)

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
    division = Column(String(20), index=True)  # "lighting" or "automation"; NULL until assigned
    category = Column(String(20), index=True)  # "retail" or "residential"; NULL until assigned
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
    role = Column(String(32), nullable=False, default="office")
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


# ---------- Supplier orders (purchase orders) ----------
# The stage follows the dates filled in: ordered -> ready at the supplier ->
# shipped -> arrived -> customs cleared -> received into stock -> delivered
# to the client. "draft" until it has an order date; "cancelled" is set by
# hand. Part-received / part-delivered are shown from the quantities.
PO_STATUSES = ["draft", "ordered", "ready", "shipped", "arrived", "cleared", "received", "delivered", "cancelled"]
SHIP_MODES = ["air", "sea", "road", "courier", "local", "direct"]


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    id = Column(Integer, primary_key=True, index=True)
    po_number = Column(String(32), unique=True, index=True, nullable=False)
    supplier = Column(String(255), nullable=False, index=True)
    supplier_ref = Column(String(120))  # supplier's proforma / order confirmation no.
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    quotation_id = Column(Integer, index=True)  # the client quotation it was raised from, if any
    status = Column(String(20), nullable=False, default="draft", index=True)
    order_date = Column(DateTime)
    expected_date = Column(DateTime)  # ETA - arrival in the UAE
    received_date = Column(DateTime)
    currency = Column(String(8), default="AED")
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Supplier payment
    payment_terms = Column(String(255))
    advance_paid_date = Column(DateTime)
    balance_paid_date = Column(DateTime)
    # Readiness at the supplier
    ready_expected = Column(DateTime)
    ready_date = Column(DateTime)
    # Shipment
    ship_mode = Column(String(20))  # air / sea / road / courier / local / direct (supplier to site)
    incoterm = Column(String(10))  # EXW, FCA, FOB, CIF, DAP, DDP ...
    forwarder = Column(String(255))
    tracking_no = Column(String(120))  # AWB / B/L / courier tracking
    dispatch_date = Column(DateTime)
    arrived_date = Column(DateTime)
    # Customs
    customs_agent = Column(String(255))
    customs_ref = Column(String(120))  # bill of entry / declaration no.
    cleared_date = Column(DateTime)
    # Delivery to the client / site
    delivery_planned = Column(DateTime)
    delivered_date = Column(DateTime)
    delivery_note = Column(String(120))
    delivered_to = Column(String(255))  # received by

    project = relationship("Project")
    items = relationship("PurchaseOrderItem", back_populates="order", cascade="all, delete-orphan",
                         order_by="PurchaseOrderItem.id")

    @property
    def total(self):
        return round(sum(i.quantity * (i.unit_cost or 0) for i in self.items), 2)

    @property
    def qty_ordered(self):
        return sum(i.quantity for i in self.items)

    @property
    def qty_received(self):
        return sum(min(i.received_qty or 0, i.quantity) for i in self.items)

    @property
    def qty_delivered(self):
        return sum(min(i.delivered_qty or 0, i.quantity) for i in self.items)

    def derive_status(self):
        """The stage, from the dates and quantities filled in."""
        if self.status == "cancelled":
            return "cancelled"
        if self.delivered_date or (self.qty_ordered and self.qty_delivered >= self.qty_ordered):
            return "delivered"
        if self.qty_ordered and self.qty_received >= self.qty_ordered:
            return "received"
        for attr, st in (("cleared_date", "cleared"), ("arrived_date", "arrived"),
                         ("dispatch_date", "shipped"), ("ready_date", "ready"), ("order_date", "ordered")):
            if getattr(self, attr):
                return st
        return "draft"

    @property
    def next_step(self):
        """What has to happen next, by when, and whether that's late."""
        st = self.status
        local = self.ship_mode in ("local", "direct")
        # Each step is due by its own planned date, or failing that by the
        # next date we've committed to (ETA, then delivery to the client).
        step = {
            "draft": ("Place the order", None),
            "ordered": ("Ready at supplier", self.ready_expected or self.expected_date or self.delivery_planned),
            "ready": ("Dispatch" if not local else "Collect / deliver", self.expected_date or self.delivery_planned),
            "shipped": ("Arrival", self.expected_date or self.delivery_planned),
            "arrived": ("Customs clearance", self.delivery_planned),
            "cleared": ("Receive into stock", self.delivery_planned),
            "received": ("Deliver to client", self.delivery_planned),
        }.get(st)
        if self.ship_mode == "direct" and st in ("shipped", "arrived", "cleared"):
            step = ("Delivered to site", self.delivery_planned or self.expected_date)
        if not step:
            return None
        label, due = step
        today = datetime.utcnow().date()
        return {"label": label, "due": due.isoformat() if due else None,
                "late": bool(due and due.date() < today)}

    @property
    def is_overdue(self):
        n = self.next_step
        return bool(n and n["late"])


class PurchaseOrderItem(Base):
    __tablename__ = "purchase_order_items"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("purchase_orders.id"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True)  # empty = not a stock item
    description = Column(Text)
    quantity = Column(Integer, nullable=False)
    unit_cost = Column(Float, default=0.0)
    received_qty = Column(Integer, default=0)
    delivered_qty = Column(Integer, default=0)  # handed over to the client / site

    order = relationship("PurchaseOrder", back_populates="items")
    product = relationship("Product")


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
    # "supplier": the brand's own PDF; "halo": a HALO sheet made outside the
    # app, used instead of the automatic one
    kind = Column(String(16), default="supplier", nullable=False)

    product = relationship("Product", back_populates="datasheets")
