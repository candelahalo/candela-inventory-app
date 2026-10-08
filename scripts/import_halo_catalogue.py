"""
Imports the full HALO catalogue from halolights.uk into the product list:
one product per size / variant, each with its datasheet PDF, the product
render from that datasheet as its photo, the HALO category, and a spec block
(used as the default quotation description) built from the datasheet.

The catalogue itself lives in scripts/data/halo_catalogue.json. It was read
from every datasheet linked on https://www.halolights.uk/products, pairing
each value with its label by position on the page.

Safe to re-run:
  - a product whose SKU already exists has its name, category, brand and spec
    refreshed; its prices, unit, reorder level and stock are never touched
  - the photo is only added if the product has none
  - a datasheet is only added if the product doesn't already have one with
    the same title

Usage (on the server):
    cd /opt/candela-inventory-app && venv/bin/python scripts/import_halo_catalogue.py

Testing without internet access:
    python3 scripts/import_halo_catalogue.py --files DIR   (PDFs named as in the catalogue)
"""
import io
import json
import os
import sys
import time
import urllib.parse
import urllib.request
import uuid
from types import SimpleNamespace

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import SessionLocal  # noqa: E402
from app import models  # noqa: E402
from app.utils import save_product_image, log_activity, DATASHEET_DIR  # noqa: E402

CATALOGUE = os.path.join(os.path.dirname(__file__), "data", "halo_catalogue.json")
CDN = "https://cdn.prod.website-files.com/67c9574954761057da264b69/"
BRAND = "HALO"


# ---------- naming ----------

def sku_for(item):
    code = item["series"].upper().replace("ADJUSTABLE", "ADJ")
    code = "-".join(code.replace("/", " ").split())
    variant = "".join(ch for ch in item["variant"].upper() if ch.isalnum() or ch == ".")
    return f"HALO-{code}-{variant}"


def name_for(item, specs):
    name = f"{item['series']} {item['variant']}"
    watt = specs.get("Wattage")
    # LED strips are named by wattage already (e.g. "I LINE IP20 4.8W/m")
    if not watt or watt.upper() == "NA" or "W/m" in item["variant"]:
        return name
    return f"{name} - {watt}"


# ---------- spec block ----------

def _clean(v):
    if v is None:
        return None
    v = " ".join(str(v).split()).strip(" ,;")
    if not v or v.upper() in ("NA", "N/A", "-"):
        return None
    v = v.replace("lm/w", "lm/W").replace("> 90+", ">90").replace("> 90", ">90").replace("< 19", "<19").replace("<19", "<19")
    return v


def _join(*parts):
    return " | ".join(p for p in parts if p)


def _kv(label, value):
    value = _clean(value)
    return f"{label}: {value}" if value else None


def spec_block(item):
    s = {k: v for k, v in item["specs"].items()}
    g = lambda *keys: next((_clean(s.get(k)) for k in keys if _clean(s.get(k))), None)  # noqa: E731

    lines = []
    mounting = g("Mounting Type")
    adjustable = (g("Adjustability") or "").lower() == "yes"
    head = f"HALO {item['series']} {item['variant']}"
    lines.append(head + (f" - {mounting}" if mounting else "") + (", adjustable" if adjustable else ""))

    lines.append(_join(g("Wattage"), g("Luminous Flux"), g("Luminaire Efficacy"),
                       g("Forward Current"), _kv("Voltage", g("LED Voltage", "Input Voltage"))))
    lines.append(_join(_kv("Beam", g("Beam Angle")), _kv("Distribution", g("Distribution")), _kv("Optic", g("Optic"))))
    lines.append(_join(_kv("Dimensions", g("Fixture Dimension (mm)", "Dimension (mm)")),
                       _kv("Cut-out", item.get("cutout"))))
    lines.append(_join(_kv("Cutting unit", g("Cutting Unit")), _kv("Max length", g("Maximum Length")),
                       _kv("LED pitch", g("LED Pitch")), _kv("Bending diameter", g("Bending Diameter"))))
    lines.append(_join(_kv("CCT", g("CCT")), _kv("CRI", g("CRI")), g("Chromaticity Tolerance"), _kv("UGR", g("UGR"))))
    lines.append(_join(_kv("Tilt", g("Tilt Angle")), _kv("Rotate", g("Ratate Angle", "Rotate Angle")),
                       g("Ingress Protection"), g("Location")))
    lines.append(_join(_kv("Housing", g("Housing")), _kv("Finish", g("Finish")), _kv("Reflector", g("Reflector Finish"))))
    lines.append(_join(_kv("Ceiling", g("Ceiling Type")), _kv("Fixing", g("Fixing Method"))))
    lines.append(_join(_kv("Driver", g("LED Driver")), _kv("Control", g("Control"))))
    maint_key = next((k for k in s if k.startswith("Lumen Maintenance")), None)
    maint = None
    if maint_key and _clean(s[maint_key]):
        tag = maint_key.replace("Lumen Maintenance", "").strip(" ()") or "lifetime"
        maint = f"Lumen maintenance {tag}: {_clean(s[maint_key])}"
    lines.append(_join(g("Appliance Class"), maint))
    return "\n".join(l for l in lines if l)


# ---------- files ----------

def fetch_pdf(item, files_dir):
    if files_dir:
        with open(os.path.join(files_dir, item["file"]), "rb") as f:
            data = f.read()
    else:
        url = CDN + urllib.parse.quote(item["file"])
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Candela catalog import)"})
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    data = r.read()
                break
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(2)
    if not data.startswith(b"%PDF-"):
        raise ValueError("not a PDF")
    return data


def product_render(pdf_bytes, photo):
    """The product picture from page 1 of the datasheet, matched by its pixel size."""
    if not photo:
        return None
    from pypdf import PdfReader
    page = PdfReader(io.BytesIO(pdf_bytes)).pages[0]
    for img in page.images:
        try:
            pil = img.image
        except Exception:
            continue
        if pil.size == (photo["w"], photo["h"]):
            buf = io.BytesIO()
            pil.save(buf, "PNG")  # PNG keeps transparency, which the app turns into white
            buf.seek(0)
            return buf
    return None


# ---------- main ----------

def main():
    files_dir = sys.argv[sys.argv.index("--files") + 1] if "--files" in sys.argv else None
    with open(CATALOGUE, encoding="utf-8") as f:
        catalogue = json.load(f)

    # Download and check every datasheet before touching the database, so a
    # network problem can't leave a half-finished import.
    print(f"Downloading {len(catalogue)} datasheets from halolights.uk ...")
    pdfs, failed = {}, []
    for n, item in enumerate(catalogue, 1):
        if not item.get("file"):  # e.g. ILUX: no datasheet published, specs from the web page
            continue
        try:
            pdfs[item["file"]] = fetch_pdf(item, files_dir)
        except Exception as e:
            failed.append(f"{item['series']} {item['variant']}: {e}")
        if n % 20 == 0:
            print(f"  {n}/{len(catalogue)}")
    if failed:
        print("\nThese datasheets could not be downloaded - nothing was changed:")
        for f_ in failed:
            print("  " + f_)
        sys.exit(1)
    print(f"  all {len(pdfs)} downloaded")

    db = SessionLocal()
    created = updated = photos = sheets = no_photo = 0
    try:
        for item in catalogue:
            sku = sku_for(item)
            spec = spec_block(item)
            name = name_for(item, item["specs"])
            product = db.query(models.Product).filter(models.Product.sku == sku).first()
            if product:
                product.name, product.category, product.brand, product.spec_summary = name, item["category"], BRAND, spec
                action = "updated"
                updated += 1
            else:
                product = models.Product(
                    sku=sku, name=name, category=item["category"], brand=BRAND,
                    unit=item.get("unit", "pcs"), cost_price=0.0, selling_price=0.0,
                    reorder_level=0, is_active=True, spec_summary=spec,
                )
                db.add(product)
                db.flush()
                action = "created"
                created += 1

            if not item.get("file"):
                log_activity(db, "system", "product", product.id, f"{product.sku} — {product.name}",
                             action, "HALO catalogue import (specs from web page, no datasheet)")
                continue

            if not product.image_path:
                render = product_render(pdfs[item["file"]], item.get("photo"))
                if render:
                    product.image_path = save_product_image(SimpleNamespace(content_type="image/png", file=render))
                    photos += 1
                else:
                    no_photo += 1

            title = f"{item['series']} {item['variant']}"
            exists = (db.query(models.Datasheet)
                      .filter(models.Datasheet.product_id == product.id, models.Datasheet.title == title).first())
            if not exists:
                filename = f"{uuid.uuid4().hex}.pdf"
                (DATASHEET_DIR / filename).write_bytes(pdfs[item["file"]])
                db.add(models.Datasheet(
                    title=title, brand=BRAND, category=item["category"], product_id=product.id,
                    file_path=f"/static/uploads/datasheets/{filename}", original_filename=f"{title}.pdf",
                ))
                sheets += 1

            log_activity(db, "system", "product", product.id, f"{product.sku} — {product.name}",
                         action, "HALO catalogue import from halolights.uk")
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    print(f"\nDone: {created} products created, {updated} updated, {sheets} datasheets attached, {photos} photos added.")
    if no_photo:
        print(f"{no_photo} product(s) got no photo from their datasheet - add one on the product page.")
    print("Set cost and selling prices for the new products in the app.")


if __name__ == "__main__":
    main()
