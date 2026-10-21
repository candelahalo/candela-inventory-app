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
    return {"systems": out, "brands": brands,
            "milestones": milestones(q.milestones, q.grand_total),
            "inclusions": [l.strip().lstrip("•-* ") for l in (q.inclusions or "").splitlines() if l.strip()],
            "exclusions": [l.strip().lstrip("•-* ") for l in (q.exclusions or "").splitlines() if l.strip()]}
