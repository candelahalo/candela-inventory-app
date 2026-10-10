"""
Business rules that tie the modules together.

One place decides how a quotation or a stock movement moves a project
along its pipeline, so the behaviour is the same whichever screen
triggered it:

  quotation raised / sent for a project  -> project moves to Quoted
  quotation accepted                     -> project moves to Approved
  quotation rejected                     -> noted on the project timeline
  every line of the approved quotation
  issued from stock to the project       -> project moves to Delivered

Automatic moves only ever go FORWARD. A project someone has already moved
further along by hand is never pulled back.
"""
from collections import OrderedDict

from sqlalchemy import func, case
from sqlalchemy.orm import Session

from app import models
from app.utils import log_activity

STAGES = list(models.ProjectStatus)


def _label(project: models.Project) -> str:
    return f"{project.project_number} — {project.name}"


def advance_project(db: Session, project, target: models.ProjectStatus, reason: str, user: str) -> bool:
    """Move a project forward to `target` (never backwards). Returns True if it moved."""
    if project is None:
        return False
    if STAGES.index(project.status) >= STAGES.index(target):
        return False
    project.status = target
    project.status_history.append(
        models.ProjectStatusHistory(status=target, notes=f"Automatic — {reason}")
    )
    log_activity(db, user, "project", project.id, _label(project), "status_changed",
                 f"Moved to {target.value} automatically ({reason})")
    return True


def note_on_project(db: Session, project, note: str):
    """Add a timeline entry without changing the stage."""
    if project is None:
        return
    project.status_history.append(models.ProjectStatusHistory(status=project.status, notes=note))


def governing_quotation(project: models.Project):
    """The quotation that defines what the job is: the latest accepted one,
    otherwise the latest one raised."""
    quotes = sorted(project.quotations, key=lambda q: (q.created_at, q.id))
    accepted = [q for q in quotes if q.status == models.DocStatus.accepted]
    if accepted:
        return accepted[-1]
    return quotes[-1] if quotes else None


def on_hand(db: Session, product_id: int, warehouse_id=None) -> int:
    signed = case(
        (models.StockMovement.movement_type == models.MovementType.out, -models.StockMovement.quantity),
        else_=models.StockMovement.quantity,
    )
    q = db.query(func.coalesce(func.sum(signed), 0)).filter(models.StockMovement.product_id == product_id)
    if warehouse_id:
        q = q.filter(models.StockMovement.warehouse_id == warehouse_id)
    return int(q.scalar() or 0)


def project_materials(db: Session, project: models.Project) -> dict:
    """What the job needs (from the governing quotation), what has gone to
    site, and whether stock can cover the rest."""
    quote = governing_quotation(project)
    required = OrderedDict()
    if quote:
        for item in quote.items:
            if item.product_id is None:  # custom line: nothing to issue from stock
                continue
            required[item.product_id] = required.get(item.product_id, 0) + item.quantity

    issued = {}
    for m in project.stock_movements:
        if m.movement_type == models.MovementType.out:
            issued[m.product_id] = issued.get(m.product_id, 0) + m.quantity
        elif m.movement_type == models.MovementType.in_:
            # Goods returned from site
            issued[m.product_id] = issued.get(m.product_id, 0) - m.quantity

    product_ids = list(required.keys()) + [pid for pid in issued if pid not in required]
    products = {p.id: p for p in db.query(models.Product).filter(models.Product.id.in_(product_ids)).all()} if product_ids else {}

    rows = []
    for pid in product_ids:
        p = products.get(pid)
        req = required.get(pid, 0)
        iss = max(0, issued.get(pid, 0))
        stock = on_hand(db, pid)
        balance = max(0, req - iss)
        rows.append({
            "product_id": pid,
            "sku": p.sku if p else "",
            "name": p.name if p else "(removed product)",
            "unit": p.unit if p else "",
            "image_path": p.image_path if p else None,
            "required": req,
            "issued": iss,
            "balance": balance,
            "on_hand": stock,
            "shortfall": max(0, balance - stock),
        })

    return {
        "quotation": {"id": quote.id, "quote_number": quote.quote_number, "status": quote.status.value} if quote else None,
        "rows": rows,
        "fully_issued": bool(rows) and quote is not None and all(r["balance"] == 0 for r in rows if r["required"]),
        "total_required": sum(r["required"] for r in rows),
        "total_issued": sum(min(r["issued"], r["required"]) for r in rows if r["required"]),
    }


def check_delivery_complete(db: Session, project, user: str) -> bool:
    """Once everything on the accepted quotation has gone to site, the
    project is Delivered."""
    if project is None:
        return False
    quote = governing_quotation(project)
    if not quote or quote.status != models.DocStatus.accepted:
        return False
    db.flush()
    db.refresh(project)
    if project_materials(db, project)["fully_issued"]:
        return advance_project(db, project, models.ProjectStatus.delivered,
                               f"all materials on {quote.quote_number} issued to site", user)
    return False


def on_quotation_saved(db: Session, quotation: models.Quotation, user: str, created: bool):
    project = quotation.project
    if project is None:
        return
    if created:
        if not advance_project(db, project, models.ProjectStatus.quoted,
                               f"{quotation.quote_number} prepared", user):
            note_on_project(db, project, f"{quotation.quote_number} prepared")


def on_quotation_status(db: Session, quotation: models.Quotation, old, new, user: str):
    project = quotation.project
    num = quotation.quote_number
    if project is None:
        return
    if new == models.DocStatus.sent:
        if not advance_project(db, project, models.ProjectStatus.quoted, f"{num} sent to client", user):
            note_on_project(db, project, f"{num} sent to client")
    elif new == models.DocStatus.accepted:
        if not advance_project(db, project, models.ProjectStatus.approved, f"{num} accepted by client", user):
            note_on_project(db, project, f"{num} accepted by client")
        check_delivery_complete(db, project, user)
    elif new == models.DocStatus.rejected:
        note_on_project(db, project, f"{num} rejected by client")
    elif old == models.DocStatus.accepted:
        note_on_project(db, project, f"{num} no longer marked accepted")


def next_project_number(db: Session) -> str:
    """Next PRJ number after the highest one ever issued (never reused)."""
    import re
    highest = 0
    for (num,) in db.query(models.Project.project_number).all():
        m = re.match(r"PRJ-(\d+)", num or "")
        if m:
            highest = max(highest, int(m.group(1)))
    return f"PRJ-{highest + 1:05d}"
