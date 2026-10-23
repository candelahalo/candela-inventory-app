"""Proposal by system (home automation): the quotation's sections are the
systems. Cover with project / consultant / contractor and the systems list,
then a page per system - scope notes, priced list with brands, system total
and product photos - then a price summary and the terms with payment
milestones and client approval. See templates/quotation_proposal.html."""
import os
import re

from app.utils import url_to_disk_path


def _brand(item):
    if item.product and item.product.brand:
        return item.product.brand
    m = re.search(r"^\s*brand\s*:\s*(.+)$", item.description or "", re.I | re.M)
    return re.split(r"\s*-\s*", m.group(1).strip())[0] if m else ""


def _title(item):
    if item.product:
        return item.product.name
    lines = [l.strip() for l in (item.description or "").splitlines() if l.strip()]
    lines = [l for l in lines if not re.match(r"^(brand|code)\s*:", l, re.I)]
    return lines[0] if lines else "Item"


def _detail(item, title):
    """One short line under the name: the first description line that adds something.
    Automation items are their name alone."""
    from app.categories import AUTOMATION_CATEGORIES
    from app.models import one_line
    if item.product and item.product.category in AUTOMATION_CATEGORIES:
        return one_line(item.description, title)[:140]
    for l in (item.description or "").splitlines():
        l = l.strip()
        if not l or re.match(r"^(brand)\s*:", l, re.I) or l.upper() == title.upper():
            continue
        if title.upper().startswith(l.upper()) or l.upper().startswith(title.upper()):
            continue
        return l[:140]
    return ""


def _photo(item):
    path = item.image_path or (item.product.image_path if item.product else None)
    if path and os.path.exists(url_to_disk_path(path)):
        return "app" + path
    return None


def milestones(text, base):
    """[(pct, text, amount)] from lines like "35% advance against design"."""
    out = []
    for line in (text or "").splitlines():
        line = line.strip().lstrip("•-* ").strip()
        if not line:
            continue
        m = re.match(r"(\d+(?:\.\d+)?)\s*%\s*(.*)", line)
        if m:
            pct = float(m.group(1))
            out.append((pct, m.group(2).strip() or line, round(base * pct / 100, 2)))
        else:
            out.append((None, line, None))
    return out


KEEP_CAPS = {"AC", "IT", "CCTV", "KNX", "DALI", "AV", "HVAC", "BMS", "VRF", "IP", "UPS", "ELV", "DB", "BOH", "TV"}


LOWER_KEEP = {"KNX", "DALI", "POE", "NVR", "DVR", "HDD", "IP", "AC", "HVAC", "VRF", "CCTV", "UPS", "LED", "USB-C", "USB",
              "TV", "RFID", "EM", "AP", "HDMI", "CAT6", "CAT6A", "UTP", "IT", "PIR", "DB", "ELV", "FCU", "4K", "AV", "SIP", "PDU", "L3"}


def _sentence(text):
    """KEYPAD 4 BUTTON KNX -> keypad 4 button KNX (capitals kept for KNX, DALI, ...)."""
    special = {"POE": "PoE", "IPAD": "iPad", "WI-FI": "Wi-Fi", "WIFI": "Wi-Fi", "IPHONE": "iPhone"}
    words = []
    for w in (text or "").split():
        wc = re.sub(r"[^\w-]", "", w).upper()
        if wc in special:
            words.append(w.upper().replace(wc, special[wc]))
            continue
        parts = []
        for part in w.split("-"):
            core = re.sub(r"[^\w]", "", part).upper()
            if core in special:
                parts.append(part.upper().replace(core, special[core]))
            elif core in LOWER_KEEP or (re.search(r"\d", core) and re.search(r"[A-Z]", core) and len(core) <= 6):
                parts.append(part.upper())
            else:
                parts.append(part.lower())
        words.append("-".join(parts))
    return " ".join(words)


def _qty(n):
    return f"{n:g}" if n is not None else ""


def auto_remarks(system):
    """General remarks made from a system's lines: "We have considered 4 no's of keypad from the brand Lutron."
    Service lines (installation, programming, fees) are left out."""
    out = []
    for l in system["lines"]:
        if not l["product"]:
            continue
        what = _sentence(l["title"])
        brand = f" from the brand {l['brand'].title() if l['brand'].isupper() and len(l['brand']) > 4 else l['brand']}" if l["brand"] else ""
        if (l["unit"] or "").lower() in ("pcs", "nos", "no", "pc", "set", "sets", "unit", "units") and l["qty"]:
            out.append(f"We have considered {_qty(l['qty'])} no's of {what}{brand}.")
        else:
            out.append(f"We have considered {what}{brand}.")
    return out


def system_title(name):
    """Section name for headings: the standard division's own spelling, else
    title case that keeps AC, IT, CCTV, KNX... in capitals."""
    from app.automation_template import DIVISIONS
    for _k, title, _i in DIVISIONS:
        if title.upper() == (name or "").strip().upper():
            return title
    words = []
    for w in (name or "").split():
        core = re.sub(r"[^\w-]", "", w).upper()
        if core in KEEP_CAPS:
            words.append(w.upper())
        elif w.lower() in ("and", "of", "&", "for", "the", "with") and words:
            words.append(w.lower())
        else:
            words.append(w[:1].upper() + w[1:].lower())
    return " ".join(words)


_ONES = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten", "Eleven", "Twelve",
         "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen"]
_TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]


def _words(n):
    n = int(n)
    if n < 20:
        return _ONES[n]
    if n < 100:
        return (_TENS[n // 10] + (" " + _ONES[n % 10] if n % 10 else "")).strip()
    if n < 1000:
        return (_ONES[n // 100] + " Hundred" + (" " + _words(n % 100) if n % 100 else "")).strip()
    for size, name in ((10 ** 9, "Billion"), (10 ** 6, "Million"), (1000, "Thousand")):
        if n >= size:
            return (_words(n // size) + " " + name + (" " + _words(n % size) if n % size else "")).strip()
    return ""


def amount_in_words(amount, currency="AED"):
    """382,272.30 -> "UAE Dirhams Three Hundred Eighty Two Thousand Two Hundred Seventy Two and 30/100 Only"."""
    whole = int(amount)
    fils = int(round((amount - whole) * 100))
    if fils == 100:
        whole, fils = whole + 1, 0
    name = "UAE Dirhams" if currency == "AED" else currency
    return f"{name} {_words(whole) or 'Zero'}" + (f" and {fils:02d}/100" if fils else "") + " Only"


def build_context(q, standard=None):
    """standard: the Settings terms, used where the quotation's own boxes are empty."""
    standard = standard or {}
    systems, order = {}, []
    for it in q.items:
        name = it.section or "General"
        if name not in systems:
            systems[name] = {"name": name, "lines": [], "total": 0.0, "photos": [], "brands": []}
            order.append(name)
        s = systems[name]
        title = _title(it)
        brand = _brand(it)
        total = round(it.quantity * it.unit_price, 2)
        s["lines"].append({"brand": brand, "title": title, "detail": _detail(it, title), "unit": it.unit or (it.product.unit if it.product else "pcs"),
                           "qty": it.quantity, "price": it.unit_price, "total": total, "product": bool(it.product)})
        s["total"] = round(s["total"] + total, 2)
        ph = _photo(it)
        if ph and ph not in s["photos"] and len(s["photos"]) < 3:
            s["photos"].append(ph)
        if brand and brand.upper() not in [b.upper() for b in s["brands"]]:
            s["brands"].append(brand)
    notes = q.section_notes or {}
    out = []
    for i, name in enumerate(order, start=1):
        s = systems[name]
        s["no"] = i
        s["title"] = system_title(name)
        s["notes"] = [l.strip().lstrip("•-* ").strip() for l in (notes.get(name) or "").splitlines() if l.strip()]
        s["auto_remarks"] = auto_remarks(s)
        edited = (q.proposal_remarks or {}).get(name)
        s["remarks"] = ([l.strip().lstrip("•-* ").strip() for l in edited.splitlines() if l.strip()]
                        if edited is not None else s["notes"] + s["auto_remarks"])
        out.append(s)
    brands = []
    for s in out:
        for b in s["brands"]:
            if b.upper() not in [x.upper() for x in brands]:
                brands.append(b)
    # Standard automation divisions this quote doesn't take: named in the summary and exclusions
    from app.automation_template import DIVISIONS
    names = {s["name"].strip().upper() for s in out}
    std = [(title.upper(), title) for key, title, _i in DIVISIONS if key != "fees"]  # fees are not a system
    not_included = [title for sec, title in std if sec not in names] if any(sec in names for sec, _t in std) else []
    return {"systems": out, "brands": brands, "matrix": room_matrix(q, order), "not_included": not_included,
            "total_words": amount_in_words(q.total_with_vat, q.currency),
            "gallery": gallery(q), "photo_size": (q.proposal_photo_size or "M").upper(), "cover": cover(q), "pages": brochure_pages(q),
            "milestones": milestones(q.milestones or standard.get("milestones"), q.grand_total),
            "inclusions": [l.strip().lstrip("•-* ") for l in (q.inclusions or standard.get("inclusions") or "").splitlines() if l.strip()],
            "exclusions": [l.strip().lstrip("•-* ") for l in (q.exclusions or standard.get("exclusions") or "").splitlines() if l.strip()]}


def _short(name, n=34):
    name = re.sub(r"\s+", " ", name or "").strip()
    return name if len(name) <= n else name[:n - 1].rstrip(" -,") + "…"


def _short_among(full, names):
    w = full.split(" ")
    sibs = [n.split(" ") for n in names if n != full and n.split(" ")[0] == w[0]]
    cut = 0
    if sibs:
        while cut < len(w) - 1 and all(len(o) > cut and o[cut] == w[cut] for o in sibs):
            cut += 1
    rest = " ".join(w[cut:]).lstrip("-, ")
    return f"{w[0].capitalize()} · {rest}" if cut else full


def room_matrix(q, order=None):
    """Design matrix: one table, all floors. Rooms x devices; per-floor items
    (gateways, actuators ...) show one number for the floor, over all its rows.
    -> [{"cols": [{ref, title, floor}], "floors": [{"name", "rows": [{"sl", "name", "cells": [{"v", "span"} | None]}]}],
         "totals": [..]}]  (a list of parts when there are too many columns for one page width)"""
    m = q.room_matrix or {}
    if not m.get("floors") or not m.get("cols"):
        return []
    order = order or []
    fcols = set(m.get("fcols") or [])
    refs, first, counters = {}, {}, {}
    for it in q.items:
        sec = it.section or "General"
        sno = (order.index(sec) + 1) if sec in order else 1
        counters[sec] = counters.get(sec, 0) + 1
        if it.product_id and str(it.product_id) not in first:
            first[str(it.product_id)] = it
            refs[str(it.product_id)] = f"{sno}.{counters[sec]}" if len(order) > 1 else str(counters[sec])

    def n(d, k):
        try:
            return int((d or {}).get(k) or 0)
        except (TypeError, ValueError):
            return 0

    def floor_total(f, k):
        return n(f.get("fq"), k) if k in fcols else sum(n(r.get("q"), k) for r in f.get("rooms", []))

    keys = list(dict.fromkeys(k for k in m["cols"] if k in first
                              and not (first[k].product and first[k].product.category == "Testing & Commissioning")))
    keys = [k for k in keys if k not in fcols] + [k for k in keys if k in fcols]
    grand = {k: sum(floor_total(f, k) for f in m["floors"]) for k in keys}
    keys = [k for k in keys if grand[k] > 0]
    if not keys:
        return []
    names = [re.sub(r"\s+", " ", (first[k].product.name if first[k].product else _title(first[k])) or "").strip() for k in keys]
    cols = [{"key": k, "ref": refs[k], "title": _short(_short_among(names[i], names), 60), "floor": k in fcols}
            for i, k in enumerate(keys)]
    per = 14  # columns that fit across an A4 portrait page
    parts = []
    for start in range(0, len(cols), per):
        pc = cols[start:start + per]
        floors = []
        for f in m["floors"]:
            room_keys = [c["key"] for c in pc if not c["floor"]]
            rooms = [r for r in f.get("rooms", []) if any(n(r.get("q"), k) for k in room_keys)]
            has_floor = any(n(f.get("fq"), c["key"]) for c in pc if c["floor"])
            if not rooms and not has_floor:
                continue
            rows = []
            for i, r in enumerate(rooms):
                cells = []
                for c in pc:
                    if c["floor"]:
                        cells.append({"v": 0, "floor": True})
                    else:
                        cells.append({"v": n(r.get("q"), c["key"]), "floor": False})
                rows.append({"sl": i + 1, "name": r.get("name") or "", "cells": cells})
            floors.append({"name": f.get("name") or "Floor", "rows": rows,
                           "fq": {c["key"]: n(f.get("fq"), c["key"]) for c in pc if c["floor"]}})
        parts.append({"cols": pc, "floors": floors, "totals": [grand[c["key"]] for c in pc],
                      "part": f"{len(parts) + 1}/{(len(cols) + per - 1) // per}" if len(cols) > per else ""})
    return parts


def default_photos(q):
    """The line photos, one per product, in quote order: [{path, caption, group}]."""
    out, seen = [], set()
    for it in q.items:
        path = it.image_path or (it.product.image_path if it.product else None)
        if not path or path in seen:
            continue
        seen.add(path)
        out.append({"path": path, "caption": it.product.name if it.product else _title(it), "group": it.section or ""})
    return out


def brochure_pages(q):
    """Brochure pages with the image paths WeasyPrint opens; pictures that are gone are skipped."""
    out = []
    for pg in q.proposal_pages or []:
        imgs, wide = [], []
        for path in pg.get("images") or []:
            if path and path.startswith("/static/") and ".." not in path and os.path.exists(url_to_disk_path(path)):
                imgs.append("app" + path)
                wide.append(_aspect(url_to_disk_path(path)) < 0.9)
        if not imgs and not (pg.get("title") or pg.get("text")):
            continue
        layout = pg.get("layout") or "one"
        if layout == "two" and len(imgs) == 2 and all(wide):
            layout = "stack"   # two landscape pictures: one above the other, full width
        out.append({"layout": layout, "title": (pg.get("title") or "").strip(),
                    "text": (pg.get("text") or "").strip(), "images": imgs})
    return out


def cover(q):
    """The cover photo, as a path WeasyPrint can open (None: the plain dark cover)."""
    path = q.proposal_cover or ""
    if not path.startswith("/static/") or ".." in path or not os.path.exists(url_to_disk_path(path)):
        return None
    return "app" + path


# Product image pages, laid out here so every page is filled:
#   per row, card width and the tallest an image may be (mm)
GAL = {"S": (4, 38.0, 40.0), "M": (3, 52.0, 52.0), "L": (2, 80.0, 80.0), "F": (1, 174.0, 104.0)}  # F: 2 a page
GAL_PAGE_H = 247.0   # A4 297 - 24 top - 20 bottom margin, less a little to be safe
GAL_HEAD_H = 16.0    # section title with its rule and the space above it
GAL_GAP = 5.0        # under each row


def _aspect(path):
    """height / width of an image file (1.0 when it can't be read)."""
    try:
        from PIL import Image
        with Image.open(path) as im:
            w, h = im.size
        return (h / w) if w else 1.0
    except Exception:
        return 1.0


def _cap_h(text, width, big=False):
    if not text:
        return 0.0
    per_line = max(8, int(width / (2.0 if big else 1.55)))
    lines = min(3, -(-len(text) // per_line))
    return 2.0 + lines * (4.2 if big else 3.1)


def gallery(q):
    """Product images grouped by system and laid out in pages:
    [{"rows": [{"group"?: title, "h": image height, "pad": extra space under, "photos": [{src, caption}]}]}].
    Rows run on from one section to the next; the space left at the foot of a page
    goes between its rows (images grow first, up to their box), so no page is half empty."""
    size = (q.proposal_photo_size or "M").upper()
    if size == "OFF":
        return []
    size = size if size in GAL else "M"
    cols, cw, maxh = GAL[size]
    photos = q.proposal_photos if q.proposal_photos is not None else default_photos(q)
    groups = []
    for ph in photos:
        path = (ph or {}).get("path") or ""
        disk = url_to_disk_path(path) if path.startswith("/static/") and ".." not in path else ""
        if not disk or not os.path.exists(disk):
            continue
        g = (ph.get("group") or "").strip()
        if not groups or groups[-1]["group"] != g:
            groups.append({"group": g, "photos": []})
        groups[-1]["photos"].append({"src": "app" + path, "caption": (ph.get("caption") or "").strip(),
                                     "ar": _aspect(disk)})
    # rows of each section, with their natural height
    rows = []
    for g in groups:
        for i in range(0, len(g["photos"]), cols):
            ps = g["photos"][i:i + cols]
            ih = max(min(maxh, cw * p["ar"]) for p in ps)
            ch = max(_cap_h(p["caption"], cw, size == "F") for p in ps)
            rows.append({"group": (g["group"] or "Products") if i == 0 else None, "img": ih, "cap": ch,
                         "full": max(cw * p["ar"] for p in ps),
                         "photos": [{"src": p["src"], "caption": p["caption"]} for p in ps]})
    # pages
    pages, cur, used = [], [], 0.0
    for r in rows:
        need = r["img"] + r["cap"] + GAL_GAP + (GAL_HEAD_H if r["group"] else 0.0)
        if cur and used + need > GAL_PAGE_H:
            pages.append((cur, used))
            cur, used = [], 0.0
        cur.append(r)
        used += need
    if cur:
        pages.append((cur, used))
    out = []
    for n, (rs, used) in enumerate(pages):
        spare = max(0.0, GAL_PAGE_H - used)
        last = n == len(pages) - 1
        if last and used < GAL_PAGE_H * 0.55:
            spare = 0.0   # a short last page stays as it is
        # let the images grow into the spare space (not past their box width / the size cap)
        for r in rs:
            room = min(r["full"], maxh * 1.3, GAL_PAGE_H - r["cap"] - GAL_GAP - GAL_HEAD_H) - r["img"]
            grow = max(0.0, min(room, spare / len(rs)))
            r["img"] += grow
        used2 = sum(r["img"] + r["cap"] + GAL_GAP + (GAL_HEAD_H if r["group"] else 0.0) for r in rs)
        pad = max(0.0, GAL_PAGE_H - used2) / len(rs) if spare else 0.0
        out.append({"cw": cw, "size": size.lower(), "fill": bool(spare), "rows": [{"group": r["group"], "h": round(r["img"], 1), "pad": 0,
                              "photos": r["photos"]} for r in rs]})
    return out


