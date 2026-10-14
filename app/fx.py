"""Product costs in foreign currency.

A product's cost is entered as the supplier quotes it (AED, USD or EUR) plus a
landed-cost % for freight, duty and clearing. The AED cost that profit uses is

    amount x rate x (1 + landed % / 100)

with the rate from Settings. Supplier orders use the plain supplier price.
Quotations keep the AED cost they were made with, so changing a rate or a
landed % only affects new quotations.
"""
from datetime import datetime

from fastapi import HTTPException

from app import models

CURRENCIES = ("AED", "USD", "EUR")


def rates(db):
    out = {"AED": 1.0}
    for r in db.query(models.ExchangeRate).all():
        out[r.currency] = r.rate
    return out


def to_aed(amount, currency, rate_map, landed_pct=0.0):
    rate = rate_map.get(currency or "AED")
    if rate is None:
        return None
    return round((amount or 0.0) * rate * (1 + (landed_pct or 0.0) / 100), 2)


def apply_cost(product, rate_map):
    """Work out product.cost_price from its currency fields. Products saved the
    old way (only cost_price) are taken as AED."""
    cur = (product.cost_currency or "AED").upper()
    if cur not in CURRENCIES:
        raise HTTPException(status_code=400, detail=f"Cost currency must be one of {', '.join(CURRENCIES)}")
    if product.cost_amount is None:
        product.cost_amount = product.cost_price or 0.0
        product.landed_pct = 0.0
        cur = "AED"
    product.cost_currency = cur
    product.landed_pct = product.landed_pct or 0.0
    if product.landed_pct < 0 or product.landed_pct > 500:
        raise HTTPException(status_code=400, detail="Landed cost % should be between 0 and 500")
    aed = to_aed(product.cost_amount, cur, rate_map, product.landed_pct)
    if aed is None:
        raise HTTPException(status_code=400, detail=f"Set the {cur} rate in Settings first")
    product.cost_price = aed


def set_rate(db, currency, rate, username):
    """Save a rate and re-work the AED cost of every product priced in it.
    Returns how many products changed."""
    currency = currency.upper()
    if currency not in CURRENCIES or currency == "AED":
        raise HTTPException(status_code=400, detail="Only USD and EUR rates can be set")
    if not rate or rate <= 0 or rate > 100:
        raise HTTPException(status_code=400, detail="Rate should be AED for 1 " + currency + ", e.g. 4.02")
    row = db.query(models.ExchangeRate).get(currency)
    if row is None:
        row = models.ExchangeRate(currency=currency)
        db.add(row)
    row.rate = rate
    row.updated_at = datetime.utcnow()
    row.updated_by = username
    db.flush()
    rate_map = rates(db)
    changed = 0
    for p in db.query(models.Product).filter(models.Product.cost_currency == currency).all():
        before = p.cost_price
        apply_cost(p, rate_map)
        if p.cost_price != before:
            changed += 1
    return changed
