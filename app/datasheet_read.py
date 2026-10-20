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
from app.naming import FINISH_CODE

BRANDS = ["QUATTROBI", "TRIDONIC", "LEDVANCE", "OSRAM", "PHILIPS", "SIGNIFY", "IGUZZINI", "FLOS", "ERCO",
          "DELTA LIGHT", "ARTEMIDE", "LINEA LIGHT", "SIMES", "BEGA", "ZUMTOBEL", "THORN", "LUCE5", "LEDS C4",
          "MEAN WELL", "LUTRON", "HELVAR", "FOSCARINI", "VIBIA", "SLV", "XAL", "ARKOSLIGHT", "OLIGO",
          "HALO", "RUHA"]
FINISHES = ["WHITE", "BLACK", "GREY", "GRAY", "SILVER", "GOLD", "BRONZE", "BRASS", "CHAMPAGNE", "ANTHRACITE",
            "CHROME", "NICKEL", "COPPER", "TITANIUM", "CORTEN"]

# spec label (lower case) -> standard label used in spec summaries
LABELS = [
    (r"^(power(?! supply)|wattage|watt\b|system power|rated power|consumption|power consumption)", "Wattage"),
    (r"(luminous flux|lumen|light output|flux)", "Luminous Flux"),
    (r"(colou?r temp|cct)", "CCT"),
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
    (r"^(duration|lifetime|life ?time|rated life)", "Rated life"),
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


UNIT = {"power": "W", "watt": "W", "beam": "°"}


def _series_options(text):
    """Options from an ordering-code block, as on HALO sheets:

        CHB-S - [power] - [beam] - [CCT] - [dimming] . [colour]
        Power 12 / 15 (W)          Beam 19 / 25 / 36 / 50 (°)
        CCT 27 / 30 / 35 / 40 (×100 K)
        Dimming 1 / 2 / 3 / 4 (see options)     Colour .01 White / .02 Black
        Dimming options  1 Non-dim  2 Phase-cut dimming  3 0-1-10V  4 DALI

    Returns {"code": "CHB-S-{power}-{beam}-{cct}-{dimming}.{colour}", "groups": [...]}
    or None when the sheet has no such block."""
    m = re.search(r"([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*)\s*((?:\s*[-.]\s*\[[^\]]+\])+)", text)
    if not m:
        return None
    keys = re.findall(r"([-.])\s*\[([^\]]+)\]", m.group(2))
    # Our code is the size only (CHB-M); watt, CCT, beam, dimming and colour
    # go in the description
    code = m.group(1)
    named = {}
    dm = re.search(r"Dimming options\s+(.+?)(?:Suitable track|HALO ARCH|$)", text, re.S | re.I)
    if dm:
        named = dict(re.findall(r"^\s*(\d)\s+(.+?)\s*$", dm.group(1), re.M))
    groups = []
    for _, k in keys:
        key = re.sub(r"[^a-z0-9]", "", k.lower())
        label = k.strip()
        label = "CCT" if key == "cct" else label[:1].upper() + label[1:]
        line = re.search(r"(?:^|\s)" + re.escape(k) + r"\s+((?:\.?\d+[^/\n(]*?)(?:\s*/\s*\.?\d+[^/\n(]*?)*)\s*(?:\(|$)",
                         text, re.I | re.M)
        if not line:
            continue
        choices = []
        for part in line.group(1).split("/"):
            part = part.strip()
            cm = re.match(r"(\.?\d+)\s*(.*)", part)
            if not cm:
                continue
            c, rest = cm.group(1), cm.group(2).strip()
            if c.startswith("."):  # colour ".01 White" -> WH
                name = (rest or "").split()[0].upper() if rest else ""
                choices.append({"label": rest or c, "code": FINISH_CODE.get(name, name[:2] or c[1:])})
            elif key == "cct":
                choices.append({"label": f"{int(c) * 100}K", "code": c})
            elif key in named or key.startswith("dim"):
                choices.append({"label": named.get(c, c), "code": c})
            else:
                choices.append({"label": c + UNIT.get(key, ""), "code": c})
        if choices:
            groups.append({"key": key, "label": label, "choices": choices})
    if not groups:
        return None
    return {"code": code, "groups": groups}


def read(data: bytes, filename: str = "") -> dict:
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        pages = pdf.pages[:3]
        first = pages[0]
        # "‡" is how some PDFs' fonts give "≥" (CRI ≥90)
        text = "\n".join((p.extract_text() or "") for p in pages).replace("‡", "≥").replace("\x00", "fi")
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
                if re.fullmatch(r"[·•|:\-–—]+", t) or t.upper() in BRANDS:
                    continue  # separators and the brand ("QUATTROBI · BAMBOO")
                if re.fullmatch(r"[A-Z0-9]{2,}(?:[-.][A-Z0-9]+)+", t):
                    code = code or t
                    continue
                parts.append(t)
            model = " ".join(parts)
            if not code:
                for line in text.splitlines()[:6]:
                    line = line.strip()
                    if re.fullmatch(r"[A-Z]{1,4}\d{2,5}[A-Z]?(?: [A-Z0-9]{1,5}){0,4}", line) and line != model:
                        code = line
                        break

        # Spec table rows from the first pages
        spec, seen = [], set()
        for p in pages[:2]:
            last, last_x = None, None
            for row in _lines(p):
                # leave out the page header (title, page no.) and footer
                if row[0]["top"] < p.height * 0.1 or row[0]["bottom"] > p.height * 0.9:
                    continue
                pair = _split_row(row)
                if not pair:
                    # a value wrapped onto the next line ("50Hz / 60" + "Hz")
                    t = " ".join(w["text"] for w in row)
                    if last is not None and last_x is not None and abs(row[0]["x0"] - last_x) < 6 and len(t) < 30:
                        last[1] = (last[1] + ("" if last[1].endswith("/") else " ") + t)[:120]
                    last = None
                    continue
                label = _std_label(pair[0])
                if label.lower() in seen:
                    last = None
                    continue
                seen.add(label.lower())
                last = [label, pair[1].replace("‡", "≥")[:120]]
                gap_at = max(range(len(row) - 1), key=lambda i: row[i + 1]["x0"] - row[i]["x1"])
                last_x = row[gap_at + 1]["x0"]
                spec.append(last)
        for row in spec:
            row[0] = row[0].replace("\x00", "fi")
            row[1] = row[1].replace("\x00", "fi")
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
        # the line under the title says what it is ("CHERUB L track spotlight - track adapter")
        subtitle = next((l for l in text.splitlines()
                         if model and l.upper().startswith(model.upper() + " ") and len(l) > len(model) + 5), "")
        body = re.sub(r"(complete |supplied |comes )?with (an? )?(integrated |electronic |remote |built-in )*(driver|power supply)"
                      r"|driver (included|integrated|built[- ]in)"
                      r"|power supply\s*:?\s*\d.*", "", text[:3000], flags=re.I)  # the "Power supply 230V" spec row
        category = (classify(type_value) or classify(model) or classify(subtitle)
                    or classify(body) or "")
        photo = _photo(first)

    options = _series_options(text)
    words_m = model.upper().split()
    series = words_m[0] if options and words_m else ""
    variant = " ".join(words_m[1:]) if options else ""
    if code and not any(k == "Code" for k, _ in spec):
        spec.insert(0, ["Code", code])
    return {"model": model.upper(), "code": code, "brand": brand, "category": category,
            "series": series, "variant": variant, "series_options": options,
            "spec": spec, "options": {"watt": watts, "cct": ccts, "finish": finishes},
            "photo": photo, "halo": brand in ("HALO", "RUHA")}
