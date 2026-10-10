from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.utils import log_activity
from app import auth
from app import workflow

router = APIRouter(prefix="/projects", tags=["Projects"],
                   dependencies=[Depends(auth.get_current_user)])


def _next_project_number(db: Session) -> str:
    return workflow.next_project_number(db)


@router.get("/", response_model=List[schemas.ProjectOut])
def list_projects(status: Optional[models.ProjectStatus] = None, db: Session = Depends(get_db)):
    q = db.query(models.Project)
    if status:
        q = q.filter(models.Project.status == status)
    return q.order_by(models.Project.created_at.desc()).all()


@router.post("/", response_model=schemas.ProjectOut, status_code=201)
def create_project(payload: schemas.ProjectCreate, db: Session = Depends(get_db), current: models.User = Depends(auth.get_current_user)):
    customer = db.query(models.Customer).get(payload.customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    project = models.Project(
        project_number=_next_project_number(db),
        name=payload.name,
        customer_id=payload.customer_id,
        division=payload.division,
        category=payload.category,
        site_address=payload.site_address,
        start_date=payload.start_date,
        target_completion_date=payload.target_completion_date,
        notes=payload.notes,
        status=models.ProjectStatus.enquiry,
    )
    db.add(project)
    db.flush()  # get project.id before adding history row

    project.status_history.append(
        models.ProjectStatusHistory(status=models.ProjectStatus.enquiry, notes="Project created")
    )
    log_activity(db, current.username, "project", project.id, f"{project.project_number} — {project.name}", "created")

    db.commit()
    db.refresh(project)
    return project


@router.get("/{project_id}", response_model=schemas.ProjectOut)
def get_project(project_id: int, db: Session = Depends(get_db)):
    project = db.query(models.Project).get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.put("/{project_id}", response_model=schemas.ProjectOut)
def update_project(project_id: int, payload: schemas.ProjectCreate, db: Session = Depends(get_db), current: models.User = Depends(auth.get_current_user)):
    project = db.query(models.Project).get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    for key, value in payload.model_dump().items():
        setattr(project, key, value)
    log_activity(db, current.username, "project", project.id, f"{project.project_number} — {project.name}", "updated")
    db.commit()
    db.refresh(project)
    return project


@router.get("/{project_id}/links")
def project_links(project_id: int, db: Session = Depends(get_db)):
    """What's attached to a project - asked before deleting it."""
    project = db.query(models.Project).get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return {
        "quotations": [{"id": q.id, "quote_number": q.quote_number} for q in project.quotations],
        "stock_movements": len(project.stock_movements),
    }


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: int, quotations: Optional[str] = None,
                   db: Session = Depends(get_db), current: models.User = Depends(auth.get_current_user)):
    """
    Deletes a project. If quotations are linked, the caller must say what to
    do with them: quotations=keep (they stay, no longer linked to a project)
    or quotations=delete (they're deleted with the project).

    Stock movements are always kept and just unlinked: deleting them would
    change stock levels.
    """
    project = db.query(models.Project).get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    linked = list(project.quotations)
    if linked and quotations not in ("keep", "delete"):
        raise HTTPException(status_code=400,
                            detail="This project has quotations linked to it. Choose whether to keep or delete them.")
    label = f"{project.project_number} — {project.name}"

    for q in linked:
        if quotations == "delete":
            log_activity(db, current.username, "quotation", q.id, q.quote_number, "deleted",
                         f"deleted with project {project.project_number}")
            db.delete(q)
        else:
            q.project_id = None
    for m in list(project.stock_movements):
        m.project_id = None

    detail = None
    if linked:
        detail = f"{len(linked)} quotation{'s' if len(linked) != 1 else ''} {'deleted' if quotations == 'delete' else 'kept, unlinked'}"
    log_activity(db, current.username, "project", project.id, label, "deleted", detail)
    db.flush()
    db.delete(project)
    db.commit()
    return None


@router.post("/{project_id}/status", response_model=schemas.ProjectOut)
def update_project_status(project_id: int, payload: schemas.ProjectStatusUpdate, db: Session = Depends(get_db), current: models.User = Depends(auth.get_current_user)):
    """
    Advance (or otherwise change) a project's live status. Every change is
    recorded in status_history so the full timeline of a job is auditable.
    """
    project = db.query(models.Project).get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.status == payload.status and not payload.notes:
        return project
    project.status = payload.status
    project.status_history.append(
        models.ProjectStatusHistory(status=payload.status, notes=payload.notes)
    )
    log_activity(db, current.username, "project", project.id, f"{project.project_number} — {project.name}",
        "status_changed", f"Moved to {payload.status.value}",
    )
    db.commit()
    db.refresh(project)
    return project


@router.get("/{project_id}/timeline", response_model=List[schemas.ProjectStatusHistoryOut])
def project_timeline(project_id: int, db: Session = Depends(get_db)):
    project = db.query(models.Project).get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project.status_history


@router.get("/board/summary")
def status_board(db: Session = Depends(get_db)):
    """
    Pipeline overview: every stage with its projects, each carrying the
    context needed to judge it at a glance - customer, quoted value, and
    how long it has been sitting at its current stage.
    """
    STAGES = [s.value for s in models.ProjectStatus]

    customers = {c.id: c for c in db.query(models.Customer).all()}

    # Value per project: its accepted quotation, otherwise the latest one.
    values = {}
    for proj in db.query(models.Project).all():
        gq = workflow.governing_quotation(proj)
        if gq:
            values[proj.id] = gq.total_with_vat

    now = datetime.utcnow()
    board = {s: [] for s in STAGES}
    totals = {s: {"count": 0, "value": 0.0} for s in STAGES}

    for p in db.query(models.Project).order_by(models.Project.created_at.desc()).all():
        # When the project last changed stage, so a stalled job is visible
        last_change = p.created_at
        if p.status_history:
            last_change = max(h.changed_at for h in p.status_history)
        days_in_stage = max(0, (now - last_change).days) if last_change else 0

        customer = customers.get(p.customer_id)
        value = values.get(p.id, 0.0)
        stage = p.status.value

        board[stage].append({
            "id": p.id,
            "project_number": p.project_number,
            "name": p.name,
            "customer": customer.name if customer else None,
            "value": value,
            "days_in_stage": days_in_stage,
            "stage_index": STAGES.index(stage),
        })
        totals[stage]["count"] += 1
        totals[stage]["value"] += value

    active = [s for s in STAGES if s != "closed"]
    return {
        "stages": STAGES,
        "board": board,
        "totals": totals,
        "active_count": sum(totals[s]["count"] for s in active),
        "active_value": round(sum(totals[s]["value"] for s in active), 2),
        "won_value": round(totals["closed"]["value"], 2),
    }


@router.get("/board/attention")
def needs_attention(db: Session = Depends(get_db)):
    """Short list of things someone should act on today."""
    now = datetime.utcnow()
    items = []

    for q in db.query(models.Quotation).filter(models.Quotation.status == models.DocStatus.sent).all():
        cust = q.customer.name if q.customer else ""
        if q.valid_until and q.valid_until < now:
            items.append({"kind": "expired", "priority": 1, "title": f"{q.quote_number} has expired",
                          "detail": f"{cust} · valid until {q.valid_until:%d %b}",
                          "href": f"/quotations?edit={q.id}"})
        elif q.valid_until and (q.valid_until - now).days <= 7:
            items.append({"kind": "expiring", "priority": 2, "title": f"{q.quote_number} expires soon",
                          "detail": f"{cust} · valid until {q.valid_until:%d %b}",
                          "href": f"/quotations?edit={q.id}"})
        elif (now - q.created_at).days >= 7:
            items.append({"kind": "followup", "priority": 3, "title": f"Follow up {q.quote_number}",
                          "detail": f"{cust} · sent {(now - q.created_at).days} days ago, no answer yet",
                          "href": f"/quotations?edit={q.id}"})

    for p in db.query(models.Project).filter(models.Project.status != models.ProjectStatus.closed).all():
        last = max([h.changed_at for h in p.status_history] or [p.created_at])
        days = (now - last).days
        if p.status in (models.ProjectStatus.approved, models.ProjectStatus.ordered):
            mats = workflow.project_materials(db, p)
            short = [r for r in mats["rows"] if r["shortfall"] > 0]
            if short:
                items.append({"kind": "shortage", "priority": 1,
                              "title": f"{p.project_number}: {len(short)} item{'s' if len(short) != 1 else ''} short in stock",
                              "detail": p.name, "href": f"/projects/view/{p.id}"})
                continue
        if days >= 14:
            items.append({"kind": "stalled", "priority": 3, "title": f"{p.project_number} idle for {days} days",
                          "detail": f"{p.name} · at {p.status.value}", "href": f"/projects/view/{p.id}"})

    items.sort(key=lambda x: x["priority"])
    return {"items": items[:8], "total": len(items)}


@router.get("/{project_id}/materials")
def project_materials(project_id: int, db: Session = Depends(get_db)):
    """Required (from the accepted / latest quotation) vs issued to site vs in stock."""
    project = db.query(models.Project).get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return workflow.project_materials(db, project)
