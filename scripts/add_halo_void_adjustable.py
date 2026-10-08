"""
Adds the HALO VOID ADJUSTABLE series (sizes S, M, L) to the product catalog,
each with its datasheet PDF and the product photo, taken from
https://www.halolights.uk/series/void-adjustable

Specifications were checked against each size's datasheet (not the web page,
which doesn't say which figures belong to which size).

Safe to re-run: a product whose SKU already exists has its descriptive fields
refreshed, and its photo / datasheet are only added if missing. Prices and
reorder levels are never overwritten - set those in the app.

Usage (on the server):
    cd /opt/candela-inventory-app && venv/bin/python scripts/add_halo_void_adjustable.py

Testing without internet access:
    python3 scripts/add_halo_void_adjustable.py --files DIR
    (DIR holds S.pdf, M.pdf, L.pdf and product.jpg)
"""
import io
import os
import sys
import urllib.request
import uuid
from types import SimpleNamespace

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PIL import Image  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app import models  # noqa: E402
from app.utils import save_product_image, log_activity, DATASHEET_DIR  # noqa: E402

CDN = "https://cdn.prod.website-files.com/67c9574954761057da264b69/"
SOURCE_PAGE = "https://www.halolights.uk/series/void-adjustable"
PHOTO = ("product.jpg", CDN + "69d4b0c1f63c50fbac5c6df6_Product%20Image.jpg")

COMMON = [
    "CCT: 2700K / 3000K / 4000K / 5000K | CRI >90 | 2 SDCM | UGR <19",
    "Tilt 30° | Rotate 355° | IP44 | Indoor",
    "Die-cast aluminium housing | Finish: White / Black | Reflector: custom finish",
    "Remote driver | Control: On/Off, 1-10V, DALI, Phase-cut dimmable",
]

PRODUCTS = [
    {
        "size": "S",
        "sku": "HALO-VOID-ADJ-S",
        "name": "VOID Adjustable S - Recessed Trimless Downlight 12W",
        "pdf": ("S.pdf", CDN + "69d4ad52625fd8bf9b7701f6_VOID%20ADJUSTABLE%20S.pdf"),
        "spec": [
            "HALO VOID ADJUSTABLE S - Ceiling recessed, trimless, adjustable",
            "12W | 767 lm | 64 lm/W | 250 mA",
            "Beam: 20° / 40° / 55°",
            "Dimensions: Ø51 x 91 mm | Plaster-in trim Ø97 mm | Cut-out Ø60 mm",
            *COMMON,
            "Class III | Lumen maintenance L80/B50 50,000 h",
        ],
    },
    {
        "size": "M",
        "sku": "HALO-VOID-ADJ-M",
        "name": "VOID Adjustable M - Recessed Trimless Downlight 15W",
        "pdf": ("M.pdf", CDN + "69d4ae754503a69b48230bea_VOID%20ADJUSTABLE%20M.pdf"),
        "spec": [
            "HALO VOID ADJUSTABLE M - Ceiling recessed, trimless, adjustable",
            "15W | 809 lm | 54 lm/W | 350 mA",
            "Beam: 25° / 30° / 36° / 50°",
            # The M datasheet gives no cut-out size, so none is stated here.
            "Dimensions: Ø75 x 110 mm | Plaster-in trim Ø121 mm",
            *COMMON,
            # The M datasheet says Class II (S and L say Class III) - kept as published.
            "Class II | Lumen maintenance L80/B50 50,000 h",
        ],
    },
    {
        "size": "L",
        "sku": "HALO-VOID-ADJ-L",
        "name": "VOID Adjustable L - Recessed Trimless Downlight 17W",
        "pdf": ("L.pdf", CDN + "69d4aff53294f28d2ce7d8a7_VOID%20ADJUSTABLE%20L.pdf"),
        "spec": [
            "HALO VOID ADJUSTABLE L - Ceiling recessed, trimless, adjustable",
            "17W | 2004 lm | 117 lm/W | 500 mA",
            "Beam: 20° / 30° / 45° / 55°",
            "Dimensions: Ø90 x 104 mm | Plaster-in trim Ø149 mm | Cut-out Ø100 mm",
            *COMMON,
            "Class III | Lumen maintenance L80/B50 50,000 h",
        ],
    },
]

CATEGORY = "Downlights"
BRAND = "HALO"


def fetch(name, url, files_dir):
    if files_dir:
        with open(os.path.join(files_dir, name), "rb") as f:
            return f.read()
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Candela catalog import)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def main():
    files_dir = None
    if "--files" in sys.argv:
        files_dir = sys.argv[sys.argv.index("--files") + 1]

    # Download and check everything first, so a network problem stops the
    # script before anything is written to the database.
    print("Downloading datasheets and photo from halolights.uk ...")
    downloads = {}
    for p in PRODUCTS:
        name, url = p["pdf"]
        data = fetch(name, url, files_dir)
        if not data.startswith(b"%PDF-"):
            sys.exit(f"Datasheet for size {p['size']} didn't download as a PDF - nothing was changed.")
        downloads[p["size"]] = data
        print(f"  VOID ADJUSTABLE {p['size']}.pdf  {len(data) // 1024} KB")
    photo = fetch(*PHOTO, files_dir)
    try:
        Image.open(io.BytesIO(photo)).verify()
    except Exception:
        sys.exit("The product photo didn't download as an image - nothing was changed.")
    print(f"  product photo  {len(photo) // 1024} KB")

    db = SessionLocal()
    try:
        for p in PRODUCTS:
            spec = "\n".join(p["spec"])
            product = db.query(models.Product).filter(models.Product.sku == p["sku"]).first()
            if product:
                product.name, product.category, product.brand = p["name"], CATEGORY, BRAND
                product.spec_summary = spec
                action = "updated"
            else:
                product = models.Product(
                    sku=p["sku"], name=p["name"], category=CATEGORY, brand=BRAND, unit="pcs",
                    cost_price=0.0, selling_price=0.0, reorder_level=0, is_active=True,
                    spec_summary=spec,
                )
                db.add(product)
                db.flush()
                action = "created"

            if not product.image_path:
                # Same processing as an upload in the app: cropped, centred
                # on an 800x800 white square, compressed to ~50 KB.
                product.image_path = save_product_image(
                    SimpleNamespace(content_type="image/jpeg", file=io.BytesIO(photo)))

            title = f"VOID ADJUSTABLE {p['size']}"
            has_sheet = (db.query(models.Datasheet)
                         .filter(models.Datasheet.product_id == product.id,
                                 models.Datasheet.title == title).first())
            if not has_sheet:
                filename = f"{uuid.uuid4().hex}.pdf"
                (DATASHEET_DIR / filename).write_bytes(downloads[p["size"]])
                db.add(models.Datasheet(
                    title=title, brand=BRAND, category=CATEGORY, product_id=product.id,
                    file_path=f"/static/uploads/datasheets/{filename}",
                    original_filename=f"{title}.pdf",
                ))

            log_activity(db, "system", "product", product.id, f"{product.sku} — {product.name}",
                         action, f"Imported from {SOURCE_PAGE}")
            print(f"  {action}: {product.sku}  {product.name}")

        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    print("\nDone. Set cost and selling prices for the three VOID ADJUSTABLE products in the app.")


if __name__ == "__main__":
    main()
