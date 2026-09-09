from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas

router = APIRouter(prefix="/projects", tags=["Projects"])


def _next_project_number(db: Session) -> str:
    count = db.query(models.Project).count() + 1
    return f"PRJ-{count:05d}"


@router.get("/", response_model=List[schemas.ProjectOut])
def list_projects(status: Optional[models.ProjectStatus] = None, db: Session = Depends(get_db)):
    q = db.query(models.Project)
    if status:
        q = q.filter(models.Project.status == status)
    return q.order_by(models.Project.created_at.desc()).all()


@router.post("/", response_model=schemas.ProjectOut, status_code=201)
def create_project(payload: schemas.ProjectCreate, db: Session = Depends(get_db)):
    customer = db.query(models.Customer).get(payload.customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    project = models.Project(
        project_number=_next_project_number(db),
        name=payload.name,
        customer_id=payload.customer_id,
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
def update_project(project_id: int, payload: schemas.ProjectCreate, db: Session = Depends(get_db)):
    project = db.query(models.Project).get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    for key, value in payload.model_dump().items():
        setattr(project, key, value)
    db.commit()
    db.refresh(project)
    return project


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: int, db: Session = Depends(get_db)):
    project = db.query(models.Project).get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    db.delete(project)
    db.commit()
    return None


@router.post("/{project_id}/status", response_model=schemas.ProjectOut)
def update_project_status(project_id: int, payload: schemas.ProjectStatusUpdate, db: Session = Depends(get_db)):
    """
    Advance (or otherwise change) a project's live status. Every change is
    recorded in status_history so the full timeline of a job is auditable.
    """
    project = db.query(models.Project).get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    project.status = payload.status
    project.status_history.append(
        models.ProjectStatusHistory(status=payload.status, notes=payload.notes)
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
    Kanban-style counts of active projects per stage — a quick 'live status'
    overview across the whole pipeline.
    """
    board = {status.value: [] for status in models.ProjectStatus}
    projects = db.query(models.Project).all()
    for p in projects:
        board[p.status.value].append({"id": p.id, "project_number": p.project_number, "name": p.name})
    return board
