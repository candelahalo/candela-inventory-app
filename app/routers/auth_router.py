import secrets
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas, auth
from app.utils import log_activity

router = APIRouter(tags=["Auth"])


@router.post("/auth/login", response_model=schemas.TokenResponse)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == form_data.username).first()
    if not user or not user.active or not auth.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    token = auth.create_access_token({"sub": user.username})
    log_activity(db, user.username, "auth", user.id, user.username, "login")
    db.commit()
    return schemas.TokenResponse(
        access_token=token, username=user.username, full_name=user.full_name,
        role=user.role, screens=auth.screens_for(user),
    )


@router.get("/auth/me")
def read_me(user: models.User = Depends(auth.get_current_user)):
    return {
        "username": user.username,
        "full_name": user.full_name,
        "role": user.role,
        "is_admin": user.role == "admin",
        "screens": auth.screens_for(user),
    }


@router.post("/auth/download-token")
def get_download_token(user: models.User = Depends(auth.get_current_user)):
    """A 60-second download-only token for links that travel in a query string."""
    return {"token": auth.create_download_token(user.username)}


@router.post("/auth/change-password")
def change_password(payload: schemas.ChangePasswordRequest, db: Session = Depends(get_db),
                    user: models.User = Depends(auth.get_current_user)):
    if not auth.verify_password(payload.current_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")
    if len(payload.new_password) < 6:
        raise HTTPException(status_code=400, detail="New password must be at least 6 characters.")
    user.hashed_password = auth.hash_password(payload.new_password)
    log_activity(db, user.username, "auth", user.id, user.username, "changed password")
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------
# USER MANAGEMENT (admin only)
# ---------------------------------------------------------------------
@router.get("/users", response_model=List[schemas.UserOut])
def list_users(db: Session = Depends(get_db), user: models.User = Depends(auth.require_admin)):
    return db.query(models.User).order_by(models.User.username).all()


@router.get("/users/screens")
def list_screens(user: models.User = Depends(auth.require_admin)):
    """The screens that can be granted, and each role's default set."""
    return {"all_screens": auth.ALL_SCREENS, "roles": auth.ROLE_DEFAULTS}


@router.post("/users", response_model=schemas.UserOut)
def create_user(payload: schemas.UserIn, db: Session = Depends(get_db),
                user: models.User = Depends(auth.require_admin)):
    if payload.role not in auth.ROLES:
        raise HTTPException(status_code=400, detail=f"Role must be one of: {', '.join(auth.ROLES)}.")
    if len(payload.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters.")
    if db.query(models.User).filter(models.User.username == payload.username).first():
        raise HTTPException(status_code=400, detail="That username is already taken.")

    new_user = models.User(
        username=payload.username,
        hashed_password=auth.hash_password(payload.password),
        full_name=(payload.full_name or "").strip() or payload.username,
        role=payload.role,
    )
    db.add(new_user)
    db.flush()
    log_activity(db, user.username, "user", new_user.id, new_user.username,
                 "created", f"role: {payload.role}")
    db.commit()
    db.refresh(new_user)
    return new_user


@router.put("/users/{user_id}/permissions", response_model=schemas.UserOut)
def set_permissions(user_id: int, payload: schemas.PermissionsIn, db: Session = Depends(get_db),
                    user: models.User = Depends(auth.require_admin)):
    target = db.query(models.User).get(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.role == "admin":
        raise HTTPException(status_code=400, detail="An admin always has every screen.")
    valid = [s for s in payload.permissions if s in auth.ALL_SCREENS]
    target.permissions = ",".join(valid)
    log_activity(db, user.username, "user", target.id, target.username,
                 "updated", "screen permissions")
    db.commit()
    db.refresh(target)
    return target


@router.post("/users/{user_id}/reset-password")
def reset_password(user_id: int, payload: schemas.ResetPasswordIn, db: Session = Depends(get_db),
                   user: models.User = Depends(auth.require_admin)):
    """Set a new password for someone who's locked out. If none is given,
    generate one and return it so the admin can pass it on."""
    target = db.query(models.User).get(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    new_password = (payload.new_password or "").strip() or secrets.token_urlsafe(8)
    if len(new_password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters.")
    target.hashed_password = auth.hash_password(new_password)
    log_activity(db, user.username, "user", target.id, target.username, "updated", "password reset")
    db.commit()
    return {"username": target.username, "password": new_password}


@router.delete("/users/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db),
                user: models.User = Depends(auth.require_admin)):
    """Two things this must not allow: deleting your own account, and
    removing the last admin - which would leave nobody able to restore a
    backup or add a login again."""
    target = db.query(models.User).get(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.id == user.id:
        raise HTTPException(status_code=400, detail="You cannot delete your own account.")
    if target.role == "admin":
        remaining = db.query(models.User).filter(
            models.User.role == "admin", models.User.id != target.id, models.User.active == True  # noqa: E712
        ).count()
        if remaining == 0:
            raise HTTPException(status_code=400, detail="This is the last admin account - it cannot be removed.")
    log_activity(db, user.username, "user", target.id, target.username, "deleted")
    db.delete(target)
    db.commit()
    return {"ok": True, "detail": f"Login for {target.username} deleted."}
