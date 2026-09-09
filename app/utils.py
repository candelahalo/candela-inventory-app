import os
import uuid
from pathlib import Path

from fastapi import UploadFile, HTTPException
from PIL import Image

UPLOAD_ROOT = Path("app/static/uploads")
PRODUCT_IMAGE_DIR = UPLOAD_ROOT / "products"
DATASHEET_DIR = UPLOAD_ROOT / "datasheets"

PRODUCT_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
DATASHEET_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_IMAGE_DIM = 1000  # px, longest side - keeps files small while staying print-quality


def url_to_disk_path(url_path: str) -> str:
    """Convert a served URL like '/static/uploads/products/x.jpg' to its
    actual filesystem path 'app/static/uploads/products/x.jpg'."""
    return "app" + url_path if url_path.startswith("/static") else url_path.lstrip("/")


def save_product_image(file: UploadFile) -> str:
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Image must be JPEG, PNG, or WebP")

    ext = ".jpg" if file.content_type == "image/jpeg" else (".png" if file.content_type == "image/png" else ".webp")
    filename = f"{uuid.uuid4().hex}{ext}"
    dest = PRODUCT_IMAGE_DIR / filename

    with open(dest, "wb") as f:
        f.write(file.file.read())

    # Normalize orientation and cap dimensions, preserving aspect ratio,
    # so every product photo displays consistently regardless of source size.
    try:
        with Image.open(dest) as img:
            img = img.convert("RGB") if img.mode in ("P", "CMYK") else img
            img.thumbnail((MAX_IMAGE_DIM, MAX_IMAGE_DIM), Image.LANCZOS)
            img.save(dest, quality=88, optimize=True)
    except Exception:
        os.remove(dest)
        raise HTTPException(status_code=400, detail="Could not process image file")

    return f"/static/uploads/products/{filename}"


def save_datasheet(file: UploadFile) -> tuple[str, str]:
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Datasheet must be a PDF file")

    filename = f"{uuid.uuid4().hex}.pdf"
    dest = DATASHEET_DIR / filename

    with open(dest, "wb") as f:
        f.write(file.file.read())

    return f"/static/uploads/datasheets/{filename}", file.filename
