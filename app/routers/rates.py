"""Exchange rates for product costs in USD and EUR (Settings page)."""
from typing import Dict

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import auth, fx, models
from app.database import get_db
from app.utils import log_activity

router = APIRouter(prefix="/rates", tags=["Exchange rates"],
                   dependencies=[Depends(auth.get_current_user)])


class RatesIn(BaseModel):
    rates: Dict[str, float]


def _out(db):
    rows = {r.currency: r for r in db.query(models.ExchangeRate).all()}
    counts = {c: db.query(models.Product).filter(models.Product.cost_currency == c,
                                                 models.Product.is_active == True).count()  # noqa: E712
              for c in fx.CURRENCIES if c != "AED"}
    return [{"currency": c, "rate": rows[c].rate if c in rows else None,
             "updated_at": rows[c].updated_at if c in rows else None,
             "updated_by": rows[c].updated_by if c in rows else None,
             "products": counts[c]}
            for c in fx.CURRENCIES if c != "AED"]


@router.get("/")
def list_rates(db: Session = Depends(get_db)):
    return _out(db)


@router.put("/")
def save_rates(payload: RatesIn, db: Session = Depends(get_db),
               current: models.User = Depends(auth.require_admin)):
    current_rates = fx.rates(db)
    notes, changed = [], 0
    for cur, rate in payload.rates.items():
        cur = cur.upper()
        if current_rates.get(cur) == rate:
            continue
        changed += fx.set_rate(db, cur, rate, current.username)
        notes.append(f"{cur} = {rate} AED")
    if notes:
        log_activity(db, current.username, "settings", None, "Exchange rates", "updated",
                     "; ".join(notes) + f"; {changed} product costs re-worked")
    db.commit()
    return {"rates": _out(db), "products_updated": changed}
