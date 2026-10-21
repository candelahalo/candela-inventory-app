"""
Reads an existing Candela quotation PDF back into quotation fields, so an
old quote can be brought into the app without retyping it.

Built for Candela's standard quotation: the Excel template printed to PDF -
a cover letter on page 1 (Date, Quotation No, To, Project, Subject, the
bullet-point terms, "Dear ...", "Regards," and who prepared it), then the
item schedule with columns SL NO / TYPE / BRAND / IMAGE / DESCRIPTION /
UNIT / TOTAL QTY / PRICE / TOTAL, then the totals (Gross Total, Air Freight
& Customs, Total Amount ...).

Everything is read by position on the page rather than by guessing at the
text order, which in a printed spreadsheet is jumbled. Nothing is saved
here: the result fills a new quotation form for someone to check and save.
"""
import io
import re
from datetime import datetime, timedelta
from types import SimpleNamespace

import pdfplumber

from app.categories import classify

_NUM = re.compile(r"^\(?-?[\d,]*\d(\.\d+)?\)?$")


def _is_num(s):
    return bool(_NUM.match(s.strip()))


def _num(s):
    s = s.strip()
    neg = s.startswith("(") or s.startswith("-")
    v = float(s.strip("()-").replace(",", ""))
    return -v if neg else v


def _lines(words, tol=4.0):
    """Words grouped into visual lines (top within `tol` points), left to right."""
    lines = []
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if lines and abs(w["top"] - lines[-1]["top"]) <= tol:
            lines[-1]["words"].append(w)
        else:
            lines.append({"top": w["top"], "words": [w]})
    for ln in lines:
        ln["words"].sort(key=lambda w: w["x0"])
        ln["bottom"] = max(w["bottom"] for w in ln["words"])
        ln["text"] = " ".join(w["text"] for w in ln["words"])
    return lines


def _clean(s):
    return " ".join((s or "").replace("•", " ").split()).strip(" :,-")


# ---------- cover letter ----------

_LABELS = [
    ("quotation no", "original_number"), ("quote no", "original_number"), ("ref", "original_number"),
    ("date", "date"), ("to", "customer_name"), ("project", "project_name"), ("subject", "subject"),
    ("attention", "attention_to"), ("attn", "attention_to"), ("kind attn", "attention_to"),
    ("currency", "currency"), ("scope", "scope"), ("delivery time", "delivery_time"),
    ("delivery", "delivery_time"), ("validity", "validity"), ("payment terms", "payment_terms"),
    ("payment", "payment_terms"),
]


def _parse_date(s):
    s = _clean(s).replace(",", "")
    for fmt in ("%d %B %Y", "%d %b %Y", "%B %d %Y", "%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d-%b-%Y", "%d-%b-%y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    return None


def _validity_days(s):
    s = (s or "").lower()
    m = re.search(r"(\d+)\s*(day|week|month)", s)
    if not m:
        return None
    n = int(m.group(1))
    return n * {"day": 1, "week": 7, "month": 30}[m.group(2)]


def _parse_cover(page, out):
    # A label and its value can sit a few points apart ("To" vs ": Allied...")
    lines = _lines(page.extract_words(), tol=7)
    for i, ln in enumerate(lines):
        text = _clean(ln["text"])
        low = text.lower()
        if ":" in text:
            label, value = text.split(":", 1)
            label, value = _clean(label).lower(), _clean(value)
            for key, field in _LABELS:
                if label == key and value and field not in out:
                    out[field] = value
                    break
        if low.startswith("dear ") and "attention_to" not in out:
            out["attention_to"] = _clean(text[5:])
        if low.startswith("regards") and "prepared_by_name" not in out:
            rest = [_clean(l["text"]) for l in lines[i + 1:i + 4] if _clean(l["text"])]
            if rest:
                out["prepared_by_name"] = rest[0]
            if len(rest) > 1 and not rest[1].lower().startswith(("approval", "from", "we ")):
                out["prepared_by_title"] = rest[1].replace("–", "-").replace("  ", " ")


# ---------- item schedule ----------

def _header(lines):
    for ln in lines:
        up = [w["text"].upper() for w in ln["words"]]
        if "DESCRIPTION" in up and ("PRICE" in up or "RATE" in up):
            return ln
    return None


def _columns(header):
    """Start x of each column, from the header words."""
    cols = {}
    words = header["words"]
    for i, w in enumerate(words):
        t = w["text"].upper().strip(".")
        if t in ("SL", "S.NO", "SN", "NO") and "sl" not in cols:
            cols["sl"] = w["x0"]
        elif t == "TYPE":
            cols["type"] = w["x0"]
        elif t == "BRAND":
            cols["brand"] = w["x0"]
        elif t == "IMAGE":
            cols["image"] = w["x0"]
        elif t == "DESCRIPTION":
            cols["desc"] = w["x0"]
        elif t in ("UNIT", "UOM"):
            cols["unit"] = w["x0"]
        elif t in ("QTY", "QUANTITY"):
            prev = words[i - 1] if i else None
            # "TOTAL QTY" is one column: it starts at "TOTAL"
            cols["qty"] = prev["x0"] if prev is not None and prev["text"].upper() == "TOTAL" and w["x0"] - prev["x1"] < 12 else w["x0"]
        elif t in ("PRICE", "RATE"):
            cols["price"] = w["x0"]
        elif t in ("TOTAL", "AMOUNT") and "price" in cols:
            cols["total"] = w["x0"]
    return cols


def _col_of(x, cols):
    best, best_x = None, -1
    for name, cx in cols.items():
        if cx - 3 <= x and cx > best_x:
            best, best_x = name, cx
    return best


def _row_bands(page, header, table_bottom):
    """Row boundaries from the table's horizontal borders, if it has them."""
    ys = sorted(e["top"] for e in page.edges
                if e["orientation"] == "h" and e["width"] > page.width * 0.5
                and header["bottom"] - 2 < e["top"] < table_bottom + 2)
    merged = []
    for y in ys:
        if not merged or y - merged[-1] > 3:
            merged.append(y)
    return list(zip(merged, merged[1:])) if len(merged) >= 2 else []


def _bands_from_gaps(lines, anchor_lines):
    """No borders: rows are blocks of text separated by a bigger gap than
    the line spacing inside a description. Each block goes with the price
    line inside it; a block without one joins the nearest that has one."""
    if not lines:
        return []
    steps = sorted(b["top"] - a["top"] for a, b in zip(lines, lines[1:]))
    typical = steps[len(steps) // 2] if steps else 10
    limit = max(10.0, typical * 1.8)
    blocks = [[lines[0]]]
    for prev, ln in zip(lines, lines[1:]):
        if ln["top"] - prev["top"] > limit:
            blocks.append([ln])
        else:
            blocks[-1].append(ln)
    spans = [[b[0]["top"], b[-1]["bottom"], sum(1 for a in anchor_lines if a in b)] for b in blocks]
    # A block without a price line joins whichever neighbour is closer
    while any(sp[2] == 0 for sp in spans) and len(spans) > 1:
        i = next(k for k, sp in enumerate(spans) if sp[2] == 0)
        gap_prev = spans[i][0] - spans[i - 1][1] if i > 0 else float("inf")
        gap_next = spans[i + 1][0] - spans[i][1] if i + 1 < len(spans) else float("inf")
        j = i - 1 if gap_prev <= gap_next else i + 1
        lo, hi = min(i, j), max(i, j)
        spans[lo:hi + 1] = [[spans[lo][0], spans[hi][1], spans[lo][2] + spans[hi][2]]]
    merged = spans
    bands = []
    for top, bottom, n in merged:
        inside = [a["top"] for a in anchor_lines if top - 1 <= a["top"] <= bottom + 1]
        if len(inside) <= 1:
            bands.append((top - 0.5, bottom + 0.5))
        else:  # several rows packed together: split halfway between price lines
            cuts = [top - 0.5] + [(x + y) / 2 for x, y in zip(inside, inside[1:])] + [bottom + 0.5]
            bands.extend(zip(cuts, cuts[1:]))
    return bands


def _line_image(page, band, cols):
    """The product picture in this row, rendered from the page."""
    x_from = cols.get("image", cols.get("brand", 0))
    x_to = cols.get("desc", page.width)
    for im in page.images:
        cy = (im["top"] + im["bottom"]) / 2
        cx = (im["x0"] + im["x1"]) / 2
        if band[0] <= cy <= band[1] and x_from - 10 <= cx <= x_to + 5:
            bbox = (max(0, im["x0"]), max(0, im["top"]), min(page.width, im["x1"]), min(page.height, im["bottom"]))
            try:
                pil = page.crop(bbox).to_image(resolution=200).original
                buf = io.BytesIO()
                pil.convert("RGB").save(buf, "PNG")
                buf.seek(0)
                return buf
            except Exception:
                return None
    return None


def _parse_table_page(page, items, totals, warnings, want_images, prev_cols=None, state=None):
    """Reads one page of the schedule; returns its columns, so a page that
    carries on without a header row is read with the columns of the one before."""
    lines = _lines(page.extract_words())
    header = _header(lines)
    if header:
        cols = _columns(header)
    elif prev_cols:
        cols = prev_cols
        header = {"top": 0, "bottom": 0}
    else:
        return None
    if not all(k in cols for k in ("desc", "qty", "price", "total")):
        warnings.append(f"Page {page.page_number}: couldn't find all the item columns.")
        return None
    body = [ln for ln in lines if ln["top"] > header["bottom"] + 1]
    # Section headings ("FRONT END MATERIALS", "INTERCOM") start left of the
    # item numbers: not part of any item's description
    left = cols.get("sl", cols.get("brand", cols["desc"])) - 4
    is_heading = lambda ln: (ln["words"][0]["x0"] < left and not re.search(r"\d\.\d\d", ln["text"])  # noqa: E731
                             and ln["text"].upper() == ln["text"])
    headings = [(ln["top"], re.sub(r"\s+([,.])", r"\1", " ".join(ln["text"].split()))) for ln in body if is_heading(ln)]
    body = [ln for ln in body if not is_heading(ln)]
    state = state if state is not None else {}

    def cells(ln):
        c = {}
        for w in ln["words"]:
            c.setdefault(_col_of(w["x0"], cols), []).append(w["text"])
        return {k: " ".join(v) for k, v in c.items()}

    anchors, total_lines = [], []
    for ln in body:
        c = cells(ln)
        q, p, t = c.get("qty", ""), c.get("price", ""), c.get("total", "")
        if _is_num(q) and _is_num(p) and _is_num(t.replace("AED", "").strip()):
            anchors.append((ln, c))
        elif anchors and re.search(r"[\d,]+\.\d\d", ln["text"]):
            total_lines.append(ln)
    if not anchors:
        return cols

    # The table runs to the totals, or to the foot of the page when it carries on overleaf
    table_bottom = (total_lines[0]["top"] - 1) if total_lines else page.height
    bands = _row_bands(page, header, table_bottom) or _bands_from_gaps(
        [ln for ln in body if ln["top"] < table_bottom], [a[0] for a in anchors])

    def band_for(ln, idx):
        for b in bands:
            if b[0] - 1 <= ln["top"] <= b[1] + 1:
                return b
        # No borders: the row runs to halfway to its neighbours' text blocks
        prev_top = anchors[idx - 1][0]["top"] if idx else header["bottom"]
        next_top = anchors[idx + 1][0]["top"] if idx + 1 < len(anchors) else table_bottom
        return ((prev_top + ln["top"]) / 2 if idx else header["bottom"], (ln["top"] + next_top) / 2)

    for idx, (ln, c) in enumerate(anchors):
        band = band_for(ln, idx)
        in_band = [l for l in body if band[0] - 0.5 <= l["top"] < band[1] - 0.5 and l not in total_lines]
        parts = {"type": [], "brand": [], "image": [], "desc": []}
        for l in in_band:
            lc = cells(l)
            for k in parts:
                if lc.get(k):
                    parts[k].append(lc[k])
        qty, price, total = _num(c["qty"]), _num(c["price"]), _num(c["total"].replace("AED", ""))
        above = [h for h in headings if h[0] < ln["top"]]
        if above:
            state["section"] = above[-1][1]
        unit = next((t for t in (c.get("unit") or "").split() if not _is_num(t)), "").strip().lower()
        unit = {"pcs": "pcs", "pc": "pcs", "nos": "pcs", "no": "pcs", "no.": "pcs", "each": "pcs", "ea": "pcs",
                "m": "m", "mtr": "m", "mtrs": "m", "meter": "m", "metre": "m", "lm": "m", "rm": "m"}.get(unit, unit or "pcs")
        desc_lines = [" ".join(x.split()) for x in parts["desc"]]
        lead = " ".join(parts["image"]).strip()  # e.g. "DRIVER" written across the image column
        if lead:
            desc_lines = [(lead + " " + desc_lines[0]) if desc_lines else lead] + desc_lines[1:]
        brand = " ".join(parts["brand"]).strip()
        item = {
            "sl": (c.get("sl") or "").strip(),
            "type_code": " ".join(parts["type"]).strip() or None,
            "brand": brand or None,
            "description": "\n".join(([f"Brand: {brand}"] if brand else []) + desc_lines) or None,
            "unit": unit,
            "quantity_raw": qty,
            "quantity": int(round(qty)) if qty else 0,
            "unit_price": round(price, 2),
            "line_total": round(total, 2),
            "discount_pct": 0.0,
            "section": state.get("section"),
            "image": _line_image(page, band, cols) if want_images else None,
            # raw cells, used to build a product from the line
            "_lead": lead, "_desc": [" ".join(x.split()) for x in parts["desc"]], "_brandcol": brand,
        }
        if qty and price and abs(qty * price - total) > 0.05:
            # The row total is less than qty x price: a line discount
            pct = (1 - total / (qty * price)) * 100
            if 0 < pct < 100:
                item["discount_pct"] = round(pct, 2)
            else:
                warnings.append(f"Line {item['sl'] or len(items) + 1}: total {total:,.2f} doesn't match quantity x price.")
        if qty != int(qty):
            warnings.append(f"Line {item['sl'] or len(items) + 1}: quantity {qty:g} rounded to {item['quantity']} (the app keeps whole quantities).")
        items.append(item)

    # A heading at the foot of the page belongs to the lines on the next one
    if headings and headings[-1][0] > anchors[-1][0]["top"]:
        state["section"] = headings[-1][1]
    for ln in total_lines:
        label = " ".join(w["text"] for w in ln["words"] if w["x0"] < cols.get("unit", cols["qty"]) - 3)
        amounts = [w["text"] for w in ln["words"] if w["x0"] >= cols["price"] - 3 and _is_num(w["text"])]
        if label.strip() and amounts:
            totals.append((_clean(label), _num(amounts[-1])))
    return cols


# ---------- whole document ----------

def _classify(text):
    t = text.lower()
    division = "automation" if "automation" in t else ("lighting" if "light" in t else None)
    category = "retail" if "retail" in t else ("residential" if re.search(r"villa|residen|home|apartment", t) else None)
    return division, category


# ---------- products from imported lines ----------
# A line with an SL number is a fitting; a line without one (driver,
# suspension kit, track channel ...) belongs to the fitting above it.

DRIVER_BRANDS = ("TRIDONIC", "MEAN WELL", "MEANWELL", "OSRAM", "PHILIPS", "LUTRON", "HELVAR",
                 "ELDOLED", "INVENTRONICS", "MOONS", "LIFUD")
SKU_PREFIX = {"QUATTROBI": "QB", "TRIDONIC": "TRI", "HALO": "HALO", "RUHA": "RUHA", "LEDVANCE": "LDV"}
FINISH_CODE = {"white": "WH", "black": "BK", "grey": "GY", "gray": "GY", "silver": "SL", "gold": "GD", "bronze": "BZ"}


def _norm(s):
    return " ".join((s or "").lower().split())


def _slug(s):
    return re.sub(r"[^A-Z0-9]+", "-", (s or "").upper()).strip("-")


def _field(lines, name):
    for l in lines:
        m = re.match(r"\s*" + name + r"\s*:?\s*(.+)", l, re.I)
        if m:
            return m.group(1).strip()
    return None


COUNTRIES = r"(GERMANY|ITALY|SPAIN|FRANCE|UAE|DUBAI|CHINA|UK|USA|TURKEY|INDIA|NETHERLANDS|BELGIUM|SWITZERLAND|AUSTRIA|DENMARK|SWEDEN|POLAND|JAPAN|KOREA)"


def _clean_brand(b):
    # "QUATTROBI - ITALY" -> QUATTROBI, "HALO-UK" -> HALO, "HAGER GERMANY" -> HAGER,
    # "CoolAutoma tion" (wrapped in its cell) -> CoolAutomation
    b = re.split(r"\s*-\s*", (b or "").strip())[0].strip()
    b = re.sub(r"\s+" + COUNTRIES + r"$", "", b, flags=re.I).strip()
    b = re.sub(r"([a-z])\s+([a-z]{1,5})$", r"\1\2", b)
    return b or None


def _category(text, division=None):
    """Category for an imported item (types are no longer used). In an
    automation quotation, accessories are automation accessories."""
    cat = classify(text)
    if division == "automation" and cat == "Accessories":
        cat = "Automation Accessories"
    return cat, None


def product_defs(items, division=None):
    """For each imported line: the product it stands for (name, brand,
    spec in the quotation's own format, SKU, a fingerprint to recognise it
    again), keyed so identical items share one product."""
    parent = None
    for it in items:
        spec = [l for l in it.get("_desc", []) if not l.lower().startswith(("location:", "brand:"))]
        if it.get("sl") or parent is None:
            brand = _clean_brand(it.get("_brandcol"))
            model = _field(spec, "Model")
            if model:
                model = model.split(",")[0].strip()
            else:
                # No "Model:" line (e.g. automation items): the description's first
                # lines, joined while they carry on ("…SWITCH/SHUTTER" + "ACTUATOR 16A C-LOAD")
                free = [l for l in spec if ":" not in l]
                model = free[0] if free else None
                for nxt in (free[1:] if division == "automation" else []):
                    if len(model) + len(nxt) > 70:
                        break
                    model = model.rstrip() + " " + nxt
                model = re.sub(r"[\s,\-/]+$", "", model) if model else None
            watt, cct, finish = _field(spec, "Wattage"), _field(spec, "CCT"), _field(spec, "Finish")
            name = " ".join(filter(None, [model, watt, cct, finish])) or (it.get("_lead") or "Item")
            prefix = SKU_PREFIX.get((brand or "").upper(), _slug(brand)[:4] or "ITEM")
            sku = "-".join(filter(None, [prefix, _slug(model), _slug(watt).replace("-", ""),
                                         (_slug(cct).replace("000K", "0K") if cct else None),
                                         FINISH_CODE.get((finish or "").lower())]))
            cat, typ = _category(" ".join([model or "", _field(spec, "Type") or "", " ".join(spec[:2])]), division)
            if not cat and division == "automation":  # keypads, sensors ...: their words can be further down
                cat, typ = _category(" ".join([model or "", it.get("_lead") or "", " ".join(spec)]), division)
            it["_product"] = {"key": "m|" + _norm(brand) + "|" + _norm("\n".join(spec)), "name": name[:255],
                              "brand": brand, "sku": sku[:64], "spec": "\n".join(spec) or None,
                              "category": cat, "product_type": typ}
            parent = {"brand": brand, "model": model or name, "watt": watt, "prefix": prefix}
            continue
        # A line belonging to the fitting above
        text = " ".join(it.get("_desc", [])).strip()
        label = (it.get("_brandcol") or it.get("_lead") or "").strip()
        driver = "driver" in (label + " " + text).lower()
        brand = next((b for b in DRIVER_BRANDS if b in text.upper()), None) if driver else None
        brand = brand or parent["brand"]
        if driver:
            ref = " ".join(filter(None, [parent["model"].split()[0], parent["watt"]]))
            core = re.sub(r"(?i)\bfor the above\b", "", text)
            core = re.sub(r"(?i)^driver\s+", "", core).strip() or "Driver"
            name = f"{core} for {ref}"
            prefix = SKU_PREFIX.get(brand.upper(), _slug(brand)[:4]) if brand else parent["prefix"]
            sku = f"{prefix}-DRV-{_slug(ref).replace('-W', 'W')}"
        else:
            ref = parent["model"]
            name = f"{text or label} ({ref})"
            sku = f"{parent['prefix']}-{_slug(text or label)}"
            if len(sku) + len(_slug(ref)) < 60:
                sku += "-" + _slug(ref)
        cat, typ = _category(name if driver or text else label, division)
        it["_product"] = {"key": "s|" + _norm(brand) + "|" + _norm(ref) + "|" + _norm(text or label),
                          "name": name[:255], "brand": brand, "sku": sku[:64], "spec": name,
                          # in an automation quote a line under an item isn't necessarily an accessory
                          "category": cat or ("Automation Accessories" if division == "automation" else "Accessories"),
                          "product_type": typ}
    # Different items that came out with the same name (e.g. stretch ceilings
    # of different sizes): add the dimension to tell them apart
    seen = {}
    for it in items:
        p = it["_product"]
        if seen.setdefault(p["name"], p["key"]) != p["key"]:
            dim = _field([l for l in it.get("_desc", [])], "Dimension")
            if dim:
                p["name"] = f"{p['name']} {dim}"[:255]
                p["sku"] = f"{p['sku']}-{_slug(dim).replace('-MM', '')}"[:64]
    return items


def _match_product(item, products):
    """A catalogue product for this line, only when it's clear-cut."""
    desc = item.get("description") or ""
    for p in products:
        if p.sku and re.search(r"(?<![\w-])" + re.escape(p.sku) + r"(?![\w-])", desc, re.I):
            return p
    m = re.search(r"Model\s*:\s*([^,\n]+)", desc, re.I)
    if not m:
        return None
    model = " ".join(m.group(1).upper().split())
    if len(model) < 3:
        return None
    cands = [p for p in products if p.name and (p.name.upper() == model or p.name.upper().startswith(model + " "))]
    w = re.search(r"Wattage\s*:\s*([\d.]+)\s*W\b", desc, re.I)
    if len(cands) > 1 and w:
        cands = [p for p in cands if re.search(r"\b" + re.escape(w.group(1)) + r"\s*W\b", p.name, re.I)]
    return cands[0] if len(cands) == 1 else None


def parse_quotation_pdf(data: bytes, products=(), save_image=None):
    """Returns the fields for a new quotation form, plus `warnings` and the
    PDF's own totals so the person can check nothing was missed."""
    out, items, totals, warnings = {}, [], [], []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        if not pdf.pages:
            raise ValueError("The PDF has no pages.")
        _parse_cover(pdf.pages[0], out)
        title = ""
        cols, state = None, {"section": None}
        for page in pdf.pages:
            if not title:
                # The schedule's heading, e.g. "RETAIL LIGHTING _NARS AVENTURE MALL KUWAIT"
                plines = _lines(page.extract_words())
                hdr = _header(plines)
                above = [l for l in plines if hdr and l["bottom"] < hdr["top"]]
                if above:
                    title = above[0]["text"]
            cols = _parse_table_page(page, items, totals, warnings, save_image is not None, cols, state) or cols
        text_all = "\n".join((p.extract_text() or "") for p in pdf.pages[-2:])

    if not items:
        raise ValueError("No item lines found. This import reads Candela's standard quotation layout "
                         "(SL NO / TYPE / BRAND / IMAGE / DESCRIPTION / UNIT / QTY / PRICE / TOTAL).")

    result = {
        "original_number": out.get("original_number"),
        "customer_name": out.get("customer_name"),
        "project_name": out.get("project_name"),
        "attention_to": out.get("attention_to"),
        "subject": out.get("subject"),
        "scope": out.get("scope"),
        "delivery_time": out.get("delivery_time"),
        "payment_terms": out.get("payment_terms"),
        "prepared_by_name": out.get("prepared_by_name"),
        "prepared_by_title": out.get("prepared_by_title"),
        "currency": "AED",
        "vat_percent": 5.0,
        "freight_charges": 0.0,
        "transportation_charges": "",
    }
    cur = (out.get("currency") or "").upper()
    for code in ("USD", "EUR", "GBP", "SAR", "KWD", "QAR", "OMR", "BHD"):
        if code in cur:
            result["currency"] = code
    m = re.search(r"(\d+(?:\.\d+)?)\s*%\s*VAT", text_all, re.I) or re.search(r"VAT\s*@?\s*(\d+(?:\.\d+)?)\s*%", text_all, re.I)
    if m:
        result["vat_percent"] = float(m.group(1))

    date = _parse_date(out.get("date") or "")
    result["date"] = date.strftime("%Y-%m-%d") if date else None
    days = _validity_days(out.get("validity"))
    result["valid_until"] = (date + timedelta(days=days)).strftime("%Y-%m-%d") if (date and days) else None

    division, category = _classify(" ".join(filter(None, [out.get("subject"), out.get("project_name"), title])))
    result["division"], result["category"] = division, category

    # Totals at the foot of the schedule
    pdf_totals = {}
    discount = 0.0
    for label, amount in totals:
        low = label.lower()
        if "discount" in low:
            discount += abs(amount)
        elif "freight" in low or "custom" in low:
            result["freight_charges"] = round(result["freight_charges"] + amount, 2)
        elif "transport" in low or "delivery" in low:
            result["transportation_charges"] = f"{amount:.2f}".rstrip("0").rstrip(".")
        elif "gross" in low or "sub total" in low or "subtotal" in low:
            pdf_totals["gross"] = amount
        elif "vat" in low and "excl" not in low and "total" not in low:
            pdf_totals["vat"] = amount
        elif "total" in low or ("amount" in low and "excl" in low):  # "Amount in AED (VAT Excluded)"
            pdf_totals.setdefault("total", amount)

    gross = round(sum(i["line_total"] for i in items), 2)
    if discount and gross:
        # One discount on the whole offer: spread as the same % on every line
        pct = discount / gross * 100
        for i in items:
            i["discount_pct"] = round(100 - (100 - i["discount_pct"]) * (1 - pct / 100), 6)
        # Each line total is rounded to fils, so the sum can be a few fils
        # off; the biggest line takes up the difference so the total matches.
        def app_total(i):  # as the app works it out
            return round(i["quantity"] * i["unit_price"] * (1 - i["discount_pct"] / 100), 2)
        target = round(gross - discount, 2)
        diff = round(target - sum(app_total(i) for i in items), 2)
        big = max(items, key=lambda i: i["quantity"] * i["unit_price"])
        base = big["quantity"] * big["unit_price"]
        if diff and base:
            want = app_total(big) + diff
            big["discount_pct"] = (1 - want / base) * 100
        warnings.append(f"Overall discount of {discount:,.2f} applied as {pct:.2f}% on every line.")

    # Products and photos
    matched = 0
    for i in items:
        p = _match_product(i, products)
        i["product_id"] = p.id if p else None
        i["product_label"] = f"{p.sku} — {p.name}" if p else None
        matched += bool(p)
        img = i.pop("image")
        i["image_path"] = None
        if img is not None and save_image is not None:
            try:
                i["image_path"] = save_image(SimpleNamespace(content_type="image/png", file=img))
            except Exception:
                pass

    expected = round(gross - discount + result["freight_charges"]
                     + (float(result["transportation_charges"]) if result["transportation_charges"] else 0), 2)
    if "gross" in pdf_totals and abs(pdf_totals["gross"] - gross) > 0.5:
        warnings.append(f"Lines add up to {gross:,.2f} but the PDF's gross total is {pdf_totals['gross']:,.2f} - check for a missed line.")
    if "total" in pdf_totals and abs(pdf_totals["total"] - expected) > 0.5:
        warnings.append(f"Imported total is {expected:,.2f} but the PDF says {pdf_totals['total']:,.2f}.")

    notes = []
    if result["original_number"] or result["date"]:
        notes.append("Imported from " + " dated ".join(filter(None, [
            result["original_number"], date.strftime("%d %b %Y") if date else None])))
    result["notes"] = "\n".join(notes) or None
    result["items"] = items
    result["matched_lines"] = matched
    result["pdf_total"] = pdf_totals.get("total")
    result["imported_total"] = expected
    result["warnings"] = warnings
    return result
