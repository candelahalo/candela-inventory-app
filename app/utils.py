import os
import uuid
from pathlib import Path

from fastapi import UploadFile, HTTPException, Header
from PIL import Image, ImageOps, ImageChops

UPLOAD_ROOT = Path("app/static/uploads")
PRODUCT_IMAGE_DIR = UPLOAD_ROOT / "products"
DATASHEET_DIR = UPLOAD_ROOT / "datasheets"

PRODUCT_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
DATASHEET_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
CANVAS_SIZE = 800  # every product photo becomes an 800x800 square, regardless of source shape


def get_user_name(x_user_name: str = Header(default="Unknown")) -> str:
    """Identifies who is performing an action for the activity log. There's no
    login system in this app - the frontend asks for a name once and sends it
    on every request via this header."""
    return x_user_name.strip() or "Unknown"


def log_activity(db, user: str, entity_type: str, entity_id, entity_label: str, action: str, details: str = None):
    from app import models
    entry = models.ActivityLog(
        entity_type=entity_type, entity_id=entity_id, entity_label=entity_label,
        action=action, details=details, performed_by=user,
    )
    db.add(entry)


def url_to_disk_path(url_path: str) -> str:
    """Convert a served URL like '/static/uploads/products/x.jpg' to its
    actual filesystem path 'app/static/uploads/products/x.jpg'."""
    return "app" + url_path if url_path.startswith("/static") else url_path.lstrip("/")


def _detect_content_bbox(img: Image.Image, threshold: int = 22, margin_pct: float = 0.04):
    """
    Finds the bounding box of the actual product within the photo by comparing
    every pixel against the photo's own background color (sampled from its
    border), so a tightly-cropped supplier photo and a loosely letterboxed one
    both end up filling the same proportion of the final frame.
    """
    w, h = img.size
    border = max(2, min(w, h) // 50)
    edge_pixels = (
        list(img.crop((0, 0, w, border)).getdata())
        + list(img.crop((0, h - border, w, h)).getdata())
        + list(img.crop((0, 0, border, h)).getdata())
        + list(img.crop((w - border, 0, w, h)).getdata())
    )
    bg_color = tuple(sorted(edge_pixels, key=lambda p: sum(p))[len(edge_pixels) // 2])

    bg_layer = Image.new("RGB", img.size, bg_color)
    diff = ImageChops.difference(img, bg_layer).convert("L")
    mask = diff.point(lambda p: 255 if p > threshold else 0)
    bbox = mask.getbbox()

    if not bbox:
        return None

    x0, y0, x1, y1 = bbox
    mx, my = int((x1 - x0) * margin_pct), int((y1 - y0) * margin_pct)
    x0, y0 = max(0, x0 - mx), max(0, y0 - my)
    x1, y1 = min(w, x1 + mx), min(h, y1 + my)

    # Guard against a degenerate crop (near-blank image or busy photographic
    # background with no clean margin) - fall back to the full photo.
    area_ratio = ((x1 - x0) * (y1 - y0)) / (w * h)
    if area_ratio < 0.02 or area_ratio > 0.98:
        return None
    return (x0, y0, x1, y1)


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

    # Auto-crop to the actual product content, so a loosely letterboxed
    # supplier photo and a tightly-cropped one end up filling the frame the
    # same amount - this is what makes different sources look "uniform".
    bbox = _detect_content_bbox(img)
    if bbox:
        img = img.crop(bbox)

    # Scale to fill a consistent proportion of the canvas, preserving aspect
    # ratio - resize (not thumbnail) so a loosely-cropped source photo gets
    # scaled UP to match, not left small just because its original pixels were.
    inner = int(CANVAS_SIZE * 0.92)
    scale = min(inner / img.width, inner / img.height)
    new_size = (max(1, round(img.width * scale)), max(1, round(img.height * scale)))
    img = img.resize(new_size, Image.LANCZOS)

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
