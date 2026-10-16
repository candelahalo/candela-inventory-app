"""Read a product datasheet PDF to start a new product from it.

Pulls out what a datasheet usually shows: the model name (the biggest text on
page 1), the brand, the spec table (label / value rows), the versions it lists
(wattages, colour temperatures, finishes) and the main product photo. The user
checks and corrects everything before the product is saved, so this aims to
get most of it right, not all of it.
"""
import base64
import io
import re

import pdfplumber
from PIL import Image

from app.categories import classify

BRANDS = ["QUATTROBI", "TRIDONIC", "LEDVANCE", "OSRAM", "PHILIPS", "SIGNIFY", "IGUZZINI", "FLOS", "ERCO",
          "DELTA LIGHT", "ARTEMIDE", "LINEA LIGHT", "SIMES", "BEGA", "ZUMTOBEL", "THORN", "LUCE5", "LEDS C4",
          "MEAN WELL", "LUTRON", "HELVAR", "FOSCARINI", "VIBIA", "SLV", "XAL", "ARKOSLIGHT", "OLIGO",
          "HALO", "RUHA"]
FINISHES = ["WHITE", "BLACK", "GREY", "GRAY", "SILVER", "GOLD", "BRONZE", "BRASS", "CHAMPAGNE", "ANTHRACITE",
            "CHROME", "NICKEL", "COPPER", "TITANIUM", "CORTEN"]

# spec label (lower case) -> standard label used in spec summaries
LABELS = [
    (r"^(power|wattage|system power|rated power|consumption|power consumption)", "Wattage"),
    (r"(luminous flux|lumen|light output|flux)", "Luminous Flux"),
    (r"(colour temp|color temp|cct)", "CCT"),
    (r"^(cri\b|ra\b|colour rendering|color rendering)", "CRI"),
    (r"(ip rating|protection|ingress|^ip$)", "IP Rating"),
    (r"(beam|optic)", "Beam Angle"),
    (r"(dimension|size|overall|diameter|cut[- ]?out|cutout|hole)", "Dimension"),
    (r"^(finish|colou?rs?|body colou?r)", "Finish"),
    (r"(dimming|control|driver)", "Control"),
    (r"^(light )?source|^led\b", "Source"),
    (r"^(product )?type|^category", "Type"),
    (r"mounting|installation", "Mounting"),
    (r"warranty|guarantee", "Warranty"),
    (r"(voltage|supply)", "Voltage"),
]


def _lines(page):
    """Text lines as lists of words (left to right), top to bottom."""
    words = page.extract_words(keep_blank_chars=False, use_text_flow=False, extra_attrs=["size"])
    rows = []
    for w in sorted(words, key=lambda w: (round(w["top"]), w["x0"])):
        if rows and abs(rows[-1][0]["top"] - w["top"]) < 3:
            rows[-1].append(w)
        else:
            rows.append([w])
    return [sorted(r, key=lambda w: w["x0"]) for r in rows]


def _split_row(row):
    """("label", "value") for a table row - split at the widest gap between
    words - or None when it isn't a label / value row."""
    if len(row) < 2:
        return None
    gaps = [(row[i + 1]["x0"] - row[i]["x1"], i) for i in range(len(row) - 1)]
    gap, at = max(gaps)
    if gap < 12:
        return None
    label = " ".join(w["text"] for w in row[:at + 1]).strip(" :")
    value = " ".join(w["text"] for w in row[at + 1:]).strip(" :")
    if not label or not value or len(label) > 40 or re.fullmatch(r"[\d.,\s/×x-]+", label):
        return None
    if re.match(r"^[\d.,]+\s*(mm|w|k|lm|°)?\b", label, re.I) or label.lower() in ("code", "description"):
        return None  # a row of an ordering / size table, not a spec
    if re.search(r"\.\d{2}\b", label):
        return None  # colour codes header (".01 White .02 Black")
    if re.fullmatch(r"[A-Z0-9]{2,}(?:[-.][A-Z0-9]+){1,}", label):
        return None  # an ordering code
    value = re.sub(r"^\.\d{2}\s+", "", value)  # ".01 White" -> "White"
    return label, value


def _std_label(label):
    l = label.lower()
    for pat, std in LABELS:
        if re.search(pat, l):
            return std
    return label[:1].upper() + label[1:]


def _photo(page):
    """The biggest picture on the page, as a JPEG data URL."""
    imgs = [i for i in page.images if (i["x1"] - i["x0"]) > 60 and (i["bottom"] - i["top"]) > 60]
    if not imgs:
        return None
    big = max(imgs, key=lambda i: (i["x1"] - i["x0"]) * (i["bottom"] - i["top"]))
    box = (max(big["x0"], 0), max(big["top"], 0), min(big["x1"], page.width), min(big["bottom"], page.height))
    try:
        im = page.crop(box).to_image(resolution=170).original.convert("RGB")
    except Exception:
        return None
    im.thumbnail((1200, 1200))
    out = io.BytesIO()
    im.save(out, "JPEG", quality=85)
    return "data:image/jpeg;base64," + base64.b64encode(out.getvalue()).decode()


def _uniq(seq):
    out = []
    for x in seq:
        if x not in out:
            out.append(x)
    return out


def read(data: bytes, filename: str = "") -> dict:
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        pages = pdf.pages[:3]
        first = pages[0]
        text = "\n".join((p.extract_text() or "") for p in pages)
        up = text.upper()

        # Model: the largest text near the top of page 1 (codes like RPH-RC kept apart)
        words = first.extract_words(extra_attrs=["size"])
        top_words = [w for w in words if w["top"] < first.height * 0.3]
        model, code = "", ""
        if top_words:
            biggest = max(w["size"] for w in top_words)
            big = sorted([w for w in top_words if w["size"] >= biggest * 0.45 and w["size"] >= 12],
                         key=lambda w: (round(w["top"] / 4), w["x0"]))
            parts = []
            for w in big:
                t = w["text"].strip()
                if re.match(r"^pag\.?\d*$|^page$|^\d+$", t, re.I):
                    continue
                if re.fullmatch(r"[A-Z0-9]{2,}(?:[-.][A-Z0-9]+)+", t):
                    code = code or t
                    continue
                parts.append(t)
            model = " ".join(parts)

        # Spec table rows from the first pages
        spec, seen = [], set()
        for p in pages[:2]:
            for row in _lines(p):
                # leave out the page header (title, page no.) and footer
                if row[0]["top"] < p.height * 0.1 or row[0]["bottom"] > p.height * 0.9:
                    continue
                pair = _split_row(row)
                if not pair:
                    continue
                label = _std_label(pair[0])
                if label.lower() in seen:
                    continue
                seen.add(label.lower())
                spec.append([label, pair[1][:120]])
        spec = spec[:18]

        brand = next((b for b in BRANDS if re.search(r"\b" + re.escape(b) + r"\b", up)), "")
        if not brand and filename:
            first_word = re.split(r"[\s_\-.]+", filename.upper())[0]
            brand = first_word if first_word.isalpha() and len(first_word) > 2 else ""

        watts = _uniq(re.findall(r"(?<![\d.])(\d{1,3}(?:[.,]\d)?)\s?W(?:/M)?\b", up))
        watts = [w.replace(",", ".") + "W" for w in watts if 0 < float(w.replace(",", ".")) <= 500][:12]
        ccts = _uniq(m + "K" for m in re.findall(r"\b(2[2-9]00|3[0-9]00|4[0-9]00|5[0-9]00|6[0-5]00)\s?K\b", up))[:8]
        finishes = _uniq(f.replace("GRAY", "GREY") for f in FINISHES if re.search(r"\b" + f + r"\b", up))[:8]

        type_value = next((v for k, v in spec if k == "Type"), "")
        category = classify(type_value) or classify(model) or classify(text[:3000]) or ""
        photo = _photo(first)

    return {"model": model.upper(), "code": code, "brand": brand, "category": category,
            "spec": spec, "options": {"watt": watts, "cct": ccts, "finish": finishes},
            "photo": photo, "halo": brand in ("HALO", "RUHA")}
