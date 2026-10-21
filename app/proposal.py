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
    """One short line under the name: the first description line that adds something."""
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


def build_context(q):
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
                           "qty": it.quantity, "price": it.unit_price, "total": total})
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
        s["notes"] = [l.strip().lstrip("•-* ").strip() for l in (notes.get(name) or "").splitlines() if l.strip()]
        out.append(s)
    brands = []
    for s in out:
        for b in s["brands"]:
            if b.upper() not in [x.upper() for x in brands]:
                brands.append(b)
    return {"systems": out, "brands": brands, "matrix": room_matrix(q, order),
            "gallery": gallery(q), "photo_size": (q.proposal_photo_size or "M").upper(),
            "milestones": milestones(q.milestones, q.grand_total),
            "inclusions": [l.strip().lstrip("•-* ") for l in (q.inclusions or "").splitlines() if l.strip()],
            "exclusions": [l.strip().lstrip("•-* ") for l in (q.exclusions or "").splitlines() if l.strip()]}


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
    """Floors of rooms x the quote's products, for a page per floor.
    -> [{"name", "cols": [{ref, title, photo, total}], "rooms": [{name, cells}], "totals"}]"""
    m = q.room_matrix or {}
    if not m.get("floors") or not m.get("cols"):
        return []
    order = order or []
    refs, first = {}, {}
    counters = {}
    for it in q.items:
        sec = it.section or "General"
        sno = (order.index(sec) + 1) if sec in order else 1
        counters[sec] = counters.get(sec, 0) + 1
        if it.product_id and str(it.product_id) not in first:
            first[str(it.product_id)] = it
            refs[str(it.product_id)] = f"{sno}.{counters[sec]}" if len(order) > 1 else str(counters[sec])
    keys = [k for k in m["cols"] if k in first]
    # columns with nothing in any room are left out
    grand = {k: sum((r.get("q") or {}).get(k, 0) or 0 for f in m["floors"] for r in f.get("rooms", [])) for k in keys}
    keys = [k for k in keys if grand[k] > 0]
    if not keys:
        return []
    names = [re.sub(r"\s+", " ", (first[k].product.name if first[k].product else _title(first[k])) or "").strip() for k in keys]
    cols = [{"key": k, "ref": refs[k], "title": _short(_short_among(names[i], names), 46),
             "photo": _photo(first[k]), "total": grand[k]} for i, k in enumerate(keys)]
    floors = []
    for f in m["floors"]:
        rooms = []
        for r in f.get("rooms", []):
            cells = [int((r.get("q") or {}).get(k, 0) or 0) for k in keys]
            if any(cells):
                rooms.append({"name": r.get("name") or "", "cells": cells})
        if rooms:
            floors.append({"name": f.get("name") or "Floor", "rooms": rooms,
                           "totals": [sum(r["cells"][i] for r in rooms) for i in range(len(keys))]})
    # more than ~9 device columns don't fit one landscape page: split into parts
    per = 9
    parts = [cols[i:i + per] for i in range(0, len(cols), per)]
    out = []
    for fl in floors:
        for pi, pc in enumerate(parts):
            idx = [cols.index(c) for c in pc]
            rooms = [{"name": r["name"], "cells": [r["cells"][i] for i in idx]} for r in fl["rooms"]]
            rooms = [r for r in rooms if any(r["cells"])]
            if not rooms:
                continue
            out.append({"name": fl["name"] + (f" ({pi + 1}/{len(parts)})" if len(parts) > 1 else ""),
                        "cols": pc, "rooms": rooms, "totals": [fl["totals"][i] for i in idx]})
    return out


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


def gallery(q):
    """Photos page before the price summary, grouped by system: [{"group", "photos": [{src, caption}]}]."""
    if (q.proposal_photo_size or "M").upper() == "OFF":
        return []
    photos = q.proposal_photos if q.proposal_photos is not None else default_photos(q)
    groups = []
    for ph in photos:
        path = (ph or {}).get("path") or ""
        if not path.startswith("/static/") or ".." in path or not os.path.exists(url_to_disk_path(path)):
            continue
        g = (ph.get("group") or "").strip()
        if not groups or groups[-1]["group"] != g:
            groups.append({"group": g, "photos": []})
        groups[-1]["photos"].append({"src": "app" + path, "caption": (ph.get("caption") or "").strip()})
    return groups
