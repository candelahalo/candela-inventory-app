"""
Authentication - password hashing and JWT session tokens.

Mirrors the approach used in the Infinia app so both systems behave the
same way: bcrypt for passwords, a 12-hour JWT for the session, and a
short-lived download-scoped token for links that must travel in a query
string (backup downloads open via plain browser navigation, which can't
set an Authorization header).
"""
import os
from datetime import datetime, timedelta

import bcrypt
from jose import jwt, JWTError
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app import models

# In production this MUST come from an environment variable. The default
# is for local development only.
SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "dev-only-secret-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 12  # a typical working day

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)

# Every screen in the app. A user's permissions are a subset of these.
ALL_SCREENS = ["dashboard", "projects", "quotations", "stock", "products",
               "customers", "activity", "settings"]

# What each role can open when no explicit permissions are set.
# Settings is on every role: it's where anyone changes their own password.
# What sits inside it (staff logins, restore) is guarded separately.
ROLE_DEFAULTS = {
    "admin": ALL_SCREENS,
    "office": ["dashboard", "projects", "quotations", "products", "customers", "settings"],
    "store": ["dashboard", "stock", "products", "settings"],
}
ROLES = list(ROLE_DEFAULTS)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    to_encode.update({"exp": datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_download_token(username: str) -> str:
    """A 60-second token scoped only to downloads, so a backup link that
    ends up in browser history or a screen share can't be reused as a
    full session token."""
    expire = datetime.utcnow() + timedelta(seconds=60)
    return jwt.encode({"sub": username, "scope": "download", "exp": expire},
                      SECRET_KEY, algorithm=ALGORITHM)


def screens_for(user: "models.User") -> list:
    """Which screens this user may open."""
    if user.role == "admin":
        return ALL_SCREENS
    if user.permissions:
        return [s for s in user.permissions.split(",") if s in ALL_SCREENS]
    return ROLE_DEFAULTS.get(user.role, [])


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise credentials_exception
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if username is None or payload.get("scope") == "download":
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = db.query(models.User).filter(models.User.username == username).first()
    if user is None or not user.active:
        raise credentials_exception
    return user


def get_download_user_from_token(token: str, db: Session):
    """Validates a download-scoped token specifically - a normal login
    token is rejected here even if otherwise valid."""
    credentials_exception = HTTPException(status_code=401, detail="Invalid or expired download link.")
    if not token or not isinstance(token, str):
        raise credentials_exception
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("scope") != "download":
            raise credentials_exception
        username = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = db.query(models.User).filter(models.User.username == username).first()
    if user is None or not user.active:
        raise credentials_exception
    return user


def require_admin(user: "models.User" = Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="This action requires admin access.")
    return user
