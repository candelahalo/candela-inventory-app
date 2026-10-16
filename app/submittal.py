"""Submittal: the quotation PDF followed by each product's datasheet (the
supplier's own PDF - Quattrobi, Tridonic, Ledvance, ...), in quote order.

Every datasheet page gets a small strip across the top: company, project,
type code and product, so loose pages can still be traced to the quote.

Each product uses its latest datasheet, the same one the quotation PDF links
to. Products without one are simply left out (the user is warned first).
"""
import html
import io
import os

from pypdf import PdfReader, PdfWriter, Transformation
from weasyprint import HTML

from app import models
from app.utils import url_to_disk_path

COMPANY = "Candelaria Light Fittings Trading LLC"


def _items(quotation, db):
    """One entry per product in quote order, with its type codes and latest
    datasheet (None if it has none)."""
    out, by_product = [], {}
    for it in quotation.items:
        if not (it.product_id and it.product):
            continue
        e = by_product.get(it.product_id)
        if e is None:
            e = {"name": it.product.name, "types": [], "sheet": None, "skip": bool(it.product.no_datasheet)}
            by_product[it.product_id] = e
            out.append(e)
        if it.type_code and it.type_code not in e["types"]:
            e["types"].append(it.type_code)
    if by_product:
        sheets = (db.query(models.Datasheet)
                  .filter(models.Datasheet.product_id.in_(list(by_product)))
                  .order_by(models.Datasheet.uploaded_at.desc()).all())
        for s in sheets:
            e = by_product[s.product_id]
            if e["sheet"] is None:
                e["sheet"] = s
    return out


def missing(quotation, db):
    """Products on the quote that have no datasheet yet (not counting the
    ones marked "No datasheet needed")."""
    return [e["name"] for e in _items(quotation, db) if e["sheet"] is None and not e["skip"]]


def _pages(sheet):
    path = url_to_disk_path(sheet.file_path)
    if not os.path.exists(path):
        return []
    try:
        reader = PdfReader(path)
        if reader.is_encrypted:
            reader.decrypt("")
        return list(reader.pages)
    except Exception:
        return []


def _stamps(entries):
    """One page per datasheet page, the same size, with only the strip on it."""
    css, body = [], []
    for i, e in enumerate(entries):
        css.append(f"@page s{i} {{ size: {e['w']:.2f}pt {e['h']:.2f}pt; margin: 0; }}")
        text = " · ".join(filter(None, [COMPANY.upper(), e["project"],
                                        ("Type " + e["types"]) if e["types"] else None, e["name"]]))
        body.append(f'<div class="pg" style="page: s{i}"><div class="strip">{html.escape(text)}</div></div>')
    doc = f"""<html><head><meta charset="UTF-8"><style>
      @font-face {{ font-family: 'Inter'; src: url('app/static/fonts/Inter-Regular.ttf'); }}
      {' '.join(css)}
      body {{ margin: 0; font-family: 'Inter', sans-serif; }}
      .pg {{ break-after: page; }}
      .strip {{ padding: 3.5pt 12pt; background: rgba(255,255,255,0.92); border-bottom: 0.6pt solid #C77D0A;
                font-size: 6.5pt; color: #3A362C; letter-spacing: 0.02em;
                white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
    </style></head><body>{''.join(body)}</body></html>"""
    return PdfReader(io.BytesIO(HTML(string=doc, base_url=".").write_pdf())).pages


def build(quotation, db, quote_pdf: bytes):
    """Quotation PDF + datasheets, as bytes."""
    project = quotation.project.name if quotation.project else (quotation.subject or "")
    writer = PdfWriter()
    for p in PdfReader(io.BytesIO(quote_pdf)).pages:
        writer.add_page(p)

    entries, pages = [], []
    for e in _items(quotation, db):
        if e["sheet"] is None:
            continue
        for p in _pages(e["sheet"]):
            if p.get("/Rotate", 0) % 360:
                p.transfer_rotation_to_content()
            box = p.mediabox
            entries.append({"w": float(box.width), "h": float(box.height), "project": project,
                            "types": ", ".join(e["types"]), "name": e["name"]})
            pages.append(p)
    if pages:
        for p, s in zip(pages, _stamps(entries)):
            box = p.mediabox
            p.merge_transformed_page(s, Transformation().translate(float(box.left), float(box.bottom)))
            writer.add_page(p)

    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()
