"""Product costs in foreign currency.

A product's cost is entered as the supplier quotes it (AED, USD or EUR). The
AED cost that profit uses is amount x rate, with the rate from Settings.
Freight is charged separately, not added to product costs. Quotations keep the
AED cost they were made with, so changing a rate only affects new quotations.
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


def to_aed(amount, currency, rate_map):
    rate = rate_map.get(currency or "AED")
    if rate is None:
        return None
    return round((amount or 0.0) * rate, 2)


def apply_cost(product, rate_map):
    """Work out product.cost_price from its currency fields. Products saved the
    old way (only cost_price) are taken as AED."""
    cur = (product.cost_currency or "AED").upper()
    if cur not in CURRENCIES:
        raise HTTPException(status_code=400, detail=f"Cost currency must be one of {', '.join(CURRENCIES)}")
    if product.cost_amount is None:
        product.cost_amount = product.cost_price or 0.0
        cur = "AED"
    product.cost_currency = cur
    aed = to_aed(product.cost_amount, cur, rate_map)
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
