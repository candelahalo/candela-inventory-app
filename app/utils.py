import os
import uuid
from pathlib import Path

from fastapi import UploadFile, HTTPException
from PIL import Image, ImageOps

UPLOAD_ROOT = Path("app/static/uploads")
PRODUCT_IMAGE_DIR = UPLOAD_ROOT / "products"
DATASHEET_DIR = UPLOAD_ROOT / "datasheets"

PRODUCT_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
DATASHEET_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
CANVAS_SIZE = 800  # every product photo becomes an 800x800 square, regardless of source shape


def url_to_disk_path(url_path: str) -> str:
    """Convert a served URL like '/static/uploads/products/x.jpg' to its
    actual filesystem path 'app/static/uploads/products/x.jpg'."""
    return "app" + url_path if url_path.startswith("/static") else url_path.lstrip("/")


def save_product_image(file: UploadFile) -> str:
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Image must be JPEG, PNG, or WebP")

    filename = f"{uuid.uuid4().hex}.jpg"
    dest = PRODUCT_IMAGE_DIR / filename

    try:
        img = Image.open(file.file)
        img.load()
        img = ImageOps.exif_transpose(img)  # respect phone-camera rotation metadata
    except Exception:
        raise HTTPException(status_code=400, detail="Could not process image file")

    # Normalize to a fixed white square canvas so every product photo is
    # identical in size and aspect ratio, no matter what shape was uploaded.
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        img = img.convert("RGBA")
        background = Image.new("RGBA", img.size, (255, 255, 255, 255))
        img = Image.alpha_composite(background, img).convert("RGB")
    else:
        img = img.convert("RGB")

    # Scale down to fit within the canvas with a small margin, preserving aspect ratio
    inner = int(CANVAS_SIZE * 0.92)
    img.thumbnail((inner, inner), Image.LANCZOS)

    canvas = Image.new("RGB", (CANVAS_SIZE, CANVAS_SIZE), (255, 255, 255))
    offset = ((CANVAS_SIZE - img.width) // 2, (CANVAS_SIZE - img.height) // 2)
    canvas.paste(img, offset)
    canvas.save(dest, "JPEG", quality=90)

    return f"/static/uploads/products/{filename}"


def save_datasheet(file: UploadFile) -> tuple[str, str]:
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Datasheet must be a PDF file")

    filename = f"{uuid.uuid4().hex}.pdf"
    dest = DATASHEET_DIR / filename

    with open(dest, "wb") as f:
        f.write(file.file.read())

    return f"/static/uploads/datasheets/{filename}", file.filename
