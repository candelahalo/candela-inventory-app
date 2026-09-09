"""
Generates realistic-looking studio product renders for products that don't
have a real manufacturer photo yet: white background, soft drop shadow,
gradient-shaded 3D-ish shapes varied by category - built entirely from
scratch with PIL/numpy so nothing here is copied from any real photo.
"""
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

SIZE = 900
BODY_DARK = (58, 56, 54)
BODY_LIGHT = (150, 147, 140)
BODY_HILIGHT = (215, 212, 204)
AMBER = (227, 150, 12)
AMBER_LIGHT = (255, 214, 130)
BRASS = (196, 155, 92)
BRASS_LIGHT = (230, 200, 150)


def _radial_gradient(size, inner_color, outer_color, center=None, radius=None):
    """Smooth radial gradient disc as an RGBA numpy-backed image."""
    h, w = size, size
    cy, cx = (center or (h / 2, w / 2))
    r = radius or (size / 2)
    Y, X = np.ogrid[:h, :w]
    dist = np.sqrt((X - cx) ** 2 + (Y - cy) ** 2) / r
    dist = np.clip(dist, 0, 1)
    arr = np.zeros((h, w, 4), dtype=np.uint8)
    for c in range(3):
        arr[..., c] = (inner_color[c] * (1 - dist) + outer_color[c] * dist).astype(np.uint8)
    arr[..., 3] = 255
    return Image.fromarray(arr, "RGBA")


def _linear_gradient(size_w, size_h, top_color, bottom_color, vertical=True):
    h, w = size_h, size_w
    arr = np.zeros((h, w, 4), dtype=np.uint8)
    t = (np.linspace(0, 1, h) if vertical else np.linspace(0, 1, w))
    for c in range(3):
        if vertical:
            col = (top_color[c] * (1 - t) + bottom_color[c] * t).astype(np.uint8)
            arr[..., c] = col[:, None]
        else:
            row = (top_color[c] * (1 - t) + bottom_color[c] * t).astype(np.uint8)
            arr[..., c] = row[None, :]
    arr[..., 3] = 255
    return Image.fromarray(arr, "RGBA")


def _masked_gradient(mask_img, top_color, bottom_color, vertical=True):
    w, h = mask_img.size
    grad = _linear_gradient(w, h, top_color, bottom_color, vertical)
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    out.paste(grad, (0, 0), mask_img)
    return out


def _shape_mask(size, draw_fn):
    mask = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(mask)
    draw_fn(d, size)
    return mask


def _add_shadow(canvas, mask_img, offset=(0, 40), blur=28, opacity=70):
    w, h = canvas.size
    shadow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    solid = Image.new("L", mask_img.size, opacity)
    shadow_layer = Image.new("RGBA", mask_img.size, (0, 0, 0, 0))
    shadow_layer.paste((20, 18, 15, opacity), (0, 0), mask_img)
    shadow.paste(shadow_layer, offset, shadow_layer)
    shadow = shadow.filter(ImageFilter.GaussianBlur(blur))
    canvas.alpha_composite(shadow)


def _paste_gradient_shape(canvas, size, draw_fn, top_color, bottom_color, offset=(0, 0)):
    mask = _shape_mask(size, draw_fn)
    _add_shadow(canvas, mask.resize((int(size * 0.9), int(size * 0.3))) if False else mask, offset=(offset[0], offset[1] + 30))
    grad = _masked_gradient(mask, top_color, bottom_color)
    canvas.alpha_composite(grad, offset)


# ---------- Category renders ----------

def _render_downlight(canvas):
    s = SIZE
    cx, cy, r = s // 2, int(s * 0.46), int(s * 0.26)

    def outer(d, sz):
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=255)
    _paste_gradient_shape(canvas, s, outer, BODY_LIGHT, BODY_DARK)

    ring = _radial_gradient(s, BODY_HILIGHT, BODY_LIGHT, center=(cy, cx), radius=r * 0.82)
    ring_mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(ring_mask).ellipse([cx - r * 0.82, cy - r * 0.82, cx + r * 0.82, cy + r * 0.82], fill=255)
    canvas.paste(ring, (0, 0), ring_mask)

    lens = _radial_gradient(s, AMBER_LIGHT, AMBER, center=(cy, cx), radius=r * 0.55)
    lens_mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(lens_mask).ellipse([cx - r * 0.55, cy - r * 0.55, cx + r * 0.55, cy + r * 0.55], fill=255)
    canvas.paste(lens, (0, 0), lens_mask)


def _render_track(canvas):
    s = SIZE
    rail_h = int(s * 0.06)
    rail_y = int(s * 0.22)
    def rail(d, sz):
        d.rounded_rectangle([s * 0.12, rail_y, s * 0.88, rail_y + rail_h], radius=rail_h // 2, fill=255)
    _paste_gradient_shape(canvas, s, rail, BODY_LIGHT, BODY_DARK)

    hx, hy, hr = int(s * 0.5), int(s * 0.55), int(s * 0.16)
    def head(d, sz):
        d.ellipse([hx - hr, hy - hr * 1.3, hx + hr, hy + hr * 1.3], fill=255)
    _paste_gradient_shape(canvas, s, head, BODY_LIGHT, BODY_DARK, offset=(0, 0))

    lens = _radial_gradient(s, AMBER_LIGHT, AMBER, center=(hy + hr * 0.9, hx), radius=hr * 0.6)
    lens_mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(lens_mask).ellipse([hx - hr * 0.6, hy + hr * 0.3, hx + hr * 0.6, hy + hr * 1.5], fill=255)
    canvas.paste(lens, (0, 0), lens_mask)


def _render_pendant(canvas):
    s = SIZE
    def wire(d, sz):
        d.rectangle([s * 0.49, s * 0.08, s * 0.51, s * 0.34], fill=255)
    _paste_gradient_shape(canvas, s, wire, BODY_DARK, BODY_DARK, offset=(0, 0))

    top_w, bot_w, y0, y1 = s * 0.22, s * 0.42, int(s * 0.32), int(s * 0.58)
    def shade(d, sz):
        d.polygon([(s / 2 - top_w, y0), (s / 2 + top_w, y0), (s / 2 + bot_w, y1), (s / 2 - bot_w, y1)], fill=255)
    _paste_gradient_shape(canvas, s, shade, BRASS_LIGHT, BRASS)

    lens = _radial_gradient(s, AMBER_LIGHT, AMBER, center=(y1 - 10, s // 2), radius=bot_w * 0.32)
    lens_mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(lens_mask).ellipse([s / 2 - bot_w * 0.32, y1 - bot_w * 0.32 - 10, s / 2 + bot_w * 0.32, y1 + bot_w * 0.32 - 10], fill=255)
    canvas.paste(lens, (0, 0), lens_mask)


def _render_strip(canvas):
    s = SIZE
    y0, y1 = int(s * 0.44), int(s * 0.56)
    def body(d, sz):
        d.rounded_rectangle([s * 0.1, y0, s * 0.9, y1], radius=(y1 - y0) // 2, fill=255)
    _paste_gradient_shape(canvas, s, body, BODY_HILIGHT, BODY_LIGHT)

    n = 9
    for i in range(n):
        x = s * 0.16 + i * (s * 0.68 / (n - 1))
        r = (y1 - y0) * 0.28
        lens = _radial_gradient(s, AMBER_LIGHT, AMBER, center=((y0 + y1) / 2, x), radius=r)
        m = Image.new("L", (s, s), 0)
        ImageDraw.Draw(m).ellipse([x - r, (y0 + y1) / 2 - r, x + r, (y0 + y1) / 2 + r], fill=255)
        canvas.paste(lens, (0, 0), m)


def _render_hub(canvas):
    s = SIZE
    r = int(s * 0.22)
    cx, cy = s // 2, int(s * 0.48)
    def body(d, sz):
        d.rounded_rectangle([cx - r, cy - r, cx + r, cy + r], radius=int(r * 0.35), fill=255)
    _paste_gradient_shape(canvas, s, body, BODY_HILIGHT, BODY_DARK)

    ring = _radial_gradient(s, AMBER_LIGHT, AMBER, center=(cy, cx), radius=r * 0.4)
    m = Image.new("L", (s, s), 0)
    ImageDraw.Draw(m).ellipse([cx - r * 0.4, cy - r * 0.4, cx + r * 0.4, cy + r * 0.4], fill=255)
    canvas.paste(ring, (0, 0), m)


def _render_wall_light(canvas):
    s = SIZE
    plate_w, plate_h = int(s * 0.14), int(s * 0.46)
    px, py = int(s * 0.5), int(s * 0.46)
    def plate(d, sz):
        d.rounded_rectangle([px - plate_w, py - plate_h, px, py + plate_h], radius=14, fill=255)
    _paste_gradient_shape(canvas, s, plate, BODY_LIGHT, BODY_DARK)

    body_w = int(s * 0.16)
    def body(d, sz):
        d.polygon([(px, py - plate_h * 0.5), (px + body_w, py - body_w * 0.3), (px + body_w, py + body_w * 0.3), (px, py + plate_h * 0.5)], fill=255)
    _paste_gradient_shape(canvas, s, body, BODY_HILIGHT, BODY_LIGHT, offset=(0, 0))

    lens = _radial_gradient(s, AMBER_LIGHT, AMBER, center=(py, px + body_w * 0.55), radius=body_w * 0.35)
    m = Image.new("L", (s, s), 0)
    ImageDraw.Draw(m).ellipse([px + body_w * 0.2, py - body_w * 0.35, px + body_w * 0.9, py + body_w * 0.35], fill=255)
    canvas.paste(lens, (0, 0), m)


CATEGORY_RENDERERS = {
    "Downlights": _render_downlight,
    "Track Lighting": _render_track,
    "Decorative": _render_pendant,
    "Strip Lighting": _render_strip,
    "Home Automation": _render_hub,
    "Outdoor": _render_wall_light,
}


def generate_placeholder(product_name: str, category: str, sku: str, dest_path: Path):
    canvas = Image.new("RGBA", (SIZE, SIZE), (255, 255, 255, 255))
    renderer = CATEGORY_RENDERERS.get(category, _render_downlight)
    renderer(canvas)

    # Subtle contact shadow at the base for grounding, like studio photography
    shadow_mask = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(shadow_mask).ellipse(
        [SIZE * 0.25, SIZE * 0.78, SIZE * 0.75, SIZE * 0.90], fill=60
    )
    shadow_mask = shadow_mask.filter(ImageFilter.GaussianBlur(18))
    shadow_layer = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    shadow_layer.paste((30, 28, 24, 255), (0, 0), shadow_mask)
    base = Image.new("RGBA", (SIZE, SIZE), (255, 255, 255, 255))
    base.alpha_composite(shadow_layer)
    base.alpha_composite(canvas)

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    base.convert("RGB").save(dest_path, "JPEG", quality=92)
