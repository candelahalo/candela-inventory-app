from typing import List, Optional
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app import auth

router = APIRouter(prefix="/activity", tags=["Activity"])


@router.get("/", response_model=List[schemas.ActivityLogOut])
def list_activity(
    entity_type: Optional[str] = None,
    limit: int = 300,
    db: Session = Depends(get_db),
    current: models.User = Depends(auth.require_admin),
):
    """The audit trail is administration - only an admin reads it."""
    q = db.query(models.ActivityLog)
    if entity_type:
        q = q.filter(models.ActivityLog.entity_type == entity_type)
    return q.order_by(models.ActivityLog.created_at.desc()).limit(limit).all()
