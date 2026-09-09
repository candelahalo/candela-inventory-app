"""
Generates simple, on-brand placeholder photos for products that don't have a
real manufacturer photo yet. Square icon-style graphics in Candela's palette,
varied by category, so the catalog looks intentional rather than blank.
"""
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SIZE = 500
PAPER = (250, 247, 241)
CHARCOAL = (23, 22, 27)
AMBER = (227, 150, 12)
LINE = (228, 221, 205)

FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_PATH_REGULAR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def _font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def _icon_downlight(draw, cx, cy, r):
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=CHARCOAL, width=6)
    draw.ellipse([cx - r * 0.45, cy - r * 0.45, cx + r * 0.45, cy + r * 0.45], fill=AMBER)


def _icon_track(draw, cx, cy, r):
    draw.rounded_rectangle([cx - r, cy - r * 0.15, cx + r, cy + r * 0.15], radius=8, fill=CHARCOAL)
    draw.ellipse([cx - r * 0.3, cy - r * 0.05, cx + r * 0.55, cy + r * 0.75], outline=CHARCOAL, width=6)
    draw.ellipse([cx, cy + r * 0.2, cx + r * 0.25, cy + r * 0.45], fill=AMBER)


def _icon_pendant(draw, cx, cy, r):
    draw.line([cx, cy - r, cx, cy - r * 0.4], fill=CHARCOAL, width=6)
    draw.polygon([(cx - r * 0.55, cy - r * 0.4), (cx + r * 0.55, cy - r * 0.4), (cx + r * 0.75, cy + r * 0.55), (cx - r * 0.75, cy + r * 0.55)], outline=CHARCOAL, width=6)
    draw.ellipse([cx - r * 0.15, cy + r * 0.15, cx + r * 0.15, cy + r * 0.45], fill=AMBER)


def _icon_strip(draw, cx, cy, r):
    draw.rounded_rectangle([cx - r, cy - r * 0.18, cx + r, cy + r * 0.18], radius=10, outline=CHARCOAL, width=6)
    for i in range(-3, 4):
        x = cx + i * (r / 3.5)
        draw.ellipse([x - 8, cy - 8, x + 8, cy + 8], fill=AMBER)


def _icon_automation(draw, cx, cy, r):
    draw.rounded_rectangle([cx - r * 0.7, cy - r * 0.7, cx + r * 0.7, cy + r * 0.7], radius=24, outline=CHARCOAL, width=6)
    draw.ellipse([cx - r * 0.22, cy - r * 0.22, cx + r * 0.22, cy + r * 0.22], fill=AMBER)
    for angle in range(0, 360, 90):
        rad = math.radians(angle)
        x1, y1 = cx + math.cos(rad) * r * 0.32, cy + math.sin(rad) * r * 0.32
        x2, y2 = cx + math.cos(rad) * r * 0.55, cy + math.sin(rad) * r * 0.55
        draw.line([x1, y1, x2, y2], fill=CHARCOAL, width=5)


def _icon_outdoor(draw, cx, cy, r):
    draw.polygon([(cx, cy - r), (cx + r * 0.85, cy + r * 0.55), (cx - r * 0.85, cy + r * 0.55)], outline=CHARCOAL, width=6)
    draw.ellipse([cx - r * 0.18, cy - r * 0.05, cx + r * 0.18, cy + r * 0.31], fill=AMBER)


def _icon_default(draw, cx, cy, r):
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=CHARCOAL, width=6)
    draw.ellipse([cx - r * 0.35, cy - r * 0.35, cx + r * 0.35, cy + r * 0.35], fill=AMBER)


CATEGORY_ICONS = {
    "Downlights": _icon_downlight,
    "Track Lighting": _icon_track,
    "Decorative": _icon_pendant,
    "Strip Lighting": _icon_strip,
    "Home Automation": _icon_automation,
    "Outdoor": _icon_outdoor,
}


def generate_placeholder(product_name: str, category: str, sku: str, dest_path: Path):
    img = Image.new("RGB", (SIZE, SIZE), PAPER)
    draw = ImageDraw.Draw(img)

    draw.rectangle([0, 0, SIZE - 1, SIZE - 1], outline=LINE, width=2)

    icon_fn = CATEGORY_ICONS.get(category, _icon_default)
    icon_fn(draw, SIZE // 2, SIZE // 2 - 30, SIZE * 0.22)

    name_font = _font(FONT_PATH, 26)
    sku_font = _font(FONT_PATH_REGULAR, 20)

    # Wrap product name across up to 2 lines
    words = product_name.split()
    lines, current = [], ""
    for w in words:
        test = (current + " " + w).strip()
        if draw.textlength(test, font=name_font) > SIZE - 60:
            lines.append(current)
            current = w
        else:
            current = test
    if current:
        lines.append(current)
    lines = lines[:2]

    y = SIZE - 110
    for line in lines:
        w = draw.textlength(line, font=name_font)
        draw.text(((SIZE - w) / 2, y), line, font=name_font, fill=CHARCOAL)
        y += 32

    sku_w = draw.textlength(sku, font=sku_font)
    draw.text(((SIZE - sku_w) / 2, y + 6), sku, font=sku_font, fill=AMBER)

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest_path, "JPEG", quality=90)
