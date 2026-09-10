import io
import json
from datetime import datetime, date
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas, auth
from app.utils import log_activity

router = APIRouter(prefix="/backup", tags=["Backup"])

AUTO_BACKUP_KEEP_DAYS = 40

# Tables included in a backup. Users and backups themselves are excluded:
# a backup of logins would let a restore silently change who has access,
# and a backup of backups is pointless bulk.
BACKUP_TABLES = [
    ("products", models.Product),
    ("warehouses", models.Warehouse),
    ("stock_movements", models.StockMovement),
    ("customers", models.Customer),
    ("projects", models.Project),
    ("project_status_history", models.ProjectStatusHistory),
    ("quotations", models.Quotation),
    ("quotation_items", models.QuotationItem),
    ("datasheets", models.Datasheet),
    ("activity_log", models.ActivityLog),
]


def _serialize(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "value"):  # Enum
        return value.value
    return value


def build_backup_data(db: Session) -> dict:
    """Everything that makes up the business data, as plain JSON."""
    data = {"_meta": {"taken_at": datetime.utcnow().isoformat(), "version": 1}}
    for name, model in BACKUP_TABLES:
        rows = []
        for obj in db.query(model).all():
            rows.append({c.name: _serialize(getattr(obj, c.name)) for c in model.__table__.columns})
        data[name] = rows
    return data


def maybe_create_auto_backup(db: Session):
    """One automatic backup per calendar day, pruned to a rolling window.
    Manual backups are never pruned."""
    today = datetime.utcnow().date()
    latest = (
        db.query(models.Backup)
        .filter(models.Backup.kind == "auto")
        .order_by(models.Backup.created_at.desc())
        .first()
    )
    if latest and latest.created_at.date() == today:
        return

    db.add(models.Backup(kind="auto", created_by="system",
                         payload=json.dumps(build_backup_data(db))))
    db.flush()

    old = (
        db.query(models.Backup)
        .filter(models.Backup.kind == "auto")
        .order_by(models.Backup.created_at.desc())
        .offset(AUTO_BACKUP_KEEP_DAYS)
        .all()
    )
    for b in old:
        db.delete(b)


@router.get("/", response_model=List[schemas.BackupOut])
def list_backups(db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    return db.query(models.Backup).order_by(models.Backup.created_at.desc()).limit(100).all()


@router.post("/", response_model=schemas.BackupOut, status_code=201)
def take_backup(db: Session = Depends(get_db), user: models.User = Depends(auth.get_current_user)):
    backup = models.Backup(kind="manual", created_by=user.username,
                           payload=json.dumps(build_backup_data(db)))
    db.add(backup)
    db.flush()
    log_activity(db, user.username, "backup", backup.id, f"Backup #{backup.id}", "created")
    db.commit()
    db.refresh(backup)
    return backup


@router.get("/{backup_id}/download")
def download_backup(backup_id: int, token: str = Query(...), db: Session = Depends(get_db)):
    """Download a backup as JSON. Uses a short-lived download token since
    this opens via plain browser navigation, which can't send headers."""
    auth.get_download_user_from_token(token, db)
    backup = db.query(models.Backup).get(backup_id)
    if not backup:
        raise HTTPException(status_code=404, detail="Backup not found")
    filename = f"candela-backup-{backup.created_at.strftime('%Y-%m-%d-%H%M')}.json"
    return StreamingResponse(
        io.BytesIO(backup.payload.encode("utf-8")),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{backup_id}/restore")
def restore_backup(backup_id: int, db: Session = Depends(get_db),
                   user: models.User = Depends(auth.require_admin)):
    """Replace all business data with the contents of a backup.

    A safety backup is taken first, so a restore chosen by mistake can
    itself be undone.
    """
    backup = db.query(models.Backup).get(backup_id)
    if not backup:
        raise HTTPException(status_code=404, detail="Backup not found")

    db.add(models.Backup(kind="manual", created_by=f"{user.username} (pre-restore)",
                         payload=json.dumps(build_backup_data(db))))
    db.flush()

    data = json.loads(backup.payload)

    # Delete in reverse dependency order so foreign keys stay valid
    for name, model in reversed(BACKUP_TABLES):
        db.query(model).delete()
    db.flush()

    restored = 0
    for name, model in BACKUP_TABLES:
        for row in data.get(name, []):
            clean = {}
            for col in model.__table__.columns:
                if col.name not in row:
                    continue
                val = row[col.name]
                if val is not None and str(col.type).startswith("DATETIME"):
                    val = datetime.fromisoformat(val)
                clean[col.name] = val
            db.add(model(**clean))
            restored += 1
    db.flush()

    log_activity(db, user.username, "backup", backup.id, f"Backup #{backup.id}",
                 "restored", f"{restored} records")
    db.commit()
    return {"ok": True, "detail": f"Restored {restored} records from backup #{backup_id}."}


@router.delete("/{backup_id}", status_code=204)
def delete_backup(backup_id: int, db: Session = Depends(get_db),
                  user: models.User = Depends(auth.require_admin)):
    backup = db.query(models.Backup).get(backup_id)
    if not backup:
        raise HTTPException(status_code=404, detail="Backup not found")
    log_activity(db, user.username, "backup", backup.id, f"Backup #{backup.id}", "deleted")
    db.delete(backup)
    db.commit()
    return None
