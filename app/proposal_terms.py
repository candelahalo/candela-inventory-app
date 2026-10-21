"""Standard automation proposal terms, set once in Settings and used by every
proposal whose own boxes are empty."""
from app import models

KEYS = ("inclusions", "exclusions", "milestones")
DEFAULTS = {
    "inclusions": "\n".join([
        "Supply of the items listed in this proposal.",
        "Installation, programming, testing and commissioning of the systems listed.",
        "Manufacturer warranty on the supplied products from the date of delivery.",
        "Post-handover support for programming adjustments for 45 days.",
        "As-built documentation and client training at handover."]),
    "exclusions": "\n".join([
        "Any civil, electrical or fit-out works, conduiting and cable pulling unless stated.",
        "Supply of light fittings, drivers, AC / FCU units, curtain fabrics and motors unless listed.",
        "Door locks, magnetic locks and strikes unless listed.",
        "TVs, monitors, iPads and other client-supplied devices unless listed.",
        "Electrical accessories / face plates unless listed.",
        "Any item not mentioned in this proposal; changes to the BOQ will be priced separately.",
        "Site passes, authority permits and their fees.",
        "VAT and other government taxes."]),
    "milestones": "\n".join([
        "50% advance with LPO",
        "40% upon delivery of hardware to site",
        "10% upon testing & commissioning"]),
}


def get(db):
    rows = {r.key: r.value for r in db.query(models.AppSetting).filter(
        models.AppSetting.key.in_([f"proposal_{k}" for k in KEYS]))}
    return {k: rows.get(f"proposal_{k}") if rows.get(f"proposal_{k}") is not None else DEFAULTS[k] for k in KEYS}


def save(db, values):
    for k in KEYS:
        if k not in values:
            continue
        row = db.query(models.AppSetting).get(f"proposal_{k}")
        if not row:
            row = models.AppSetting(key=f"proposal_{k}")
            db.add(row)
        row.value = (values[k] or "").strip()
