"""Lighting submittal: one PDF for consultant / client approval.

Cover page, an index of the quotation's products (type code, product, brand,
page), then each product's datasheet - the supplier's own PDF (Quattrobi,
Tridonic, Ledvance, ...) - with a small strip stamped across the top of every
page: company, project, type code and page number. No prices.

Each product uses its latest datasheet, the same one the quotation PDF links
to. Products without one are listed as "datasheet to follow".
"""
import html
import io
import os
from datetime import date

from pypdf import PdfReader, PdfWriter, Transformation
from weasyprint import HTML

from app import models
from app.utils import url_to_disk_path

COMPANY = "Candelaria Light Fittings Trading LLC"


def _first_line(text):
    return next((l.strip() for l in (text or "").splitlines() if l.strip()), "")


def _rows(quotation, db):
    """One row per product (in quote order; the type codes it's used under),
    plus custom lines, which have no datasheet."""
    rows, by_product = [], {}
    for it in quotation.items:
        if it.product_id and it.product:
            row = by_product.get(it.product_id)
            if row is None:
                p = it.product
                row = {"product_id": p.id, "name": p.name, "sku": p.sku, "brand": p.brand,
                       "types": [], "sheet": None}
                by_product[p.id] = row
                rows.append(row)
        else:
            name = _first_line(it.description) or "Custom item"
            row = {"product_id": None, "name": name, "sku": None, "brand": None, "types": [], "sheet": None}
            rows.append(row)
        if it.type_code and it.type_code not in row["types"]:
            row["types"].append(it.type_code)
    if by_product:
        sheets = (db.query(models.Datasheet)
                  .filter(models.Datasheet.product_id.in_(list(by_product)))
                  .order_by(models.Datasheet.uploaded_at.desc()).all())
        for s in sheets:
            row = by_product[s.product_id]
            if row["sheet"] is None:
                row["sheet"] = s
    return rows


def _open_sheet(sheet):
    """The datasheet's pages, or None when the file is missing or unreadable."""
    path = url_to_disk_path(sheet.file_path)
    if not os.path.exists(path):
        return None
    try:
        reader = PdfReader(path)
        if reader.is_encrypted:
            reader.decrypt("")
        pages = list(reader.pages)
        return pages or None
    except Exception:
        return None


def missing(quotation, db):
    """Names of the items that would show as 'datasheet to follow'."""
    return [r["name"] for r in _rows(quotation, db) if r["sheet"] is None]


def _render_front(templates, quotation, rows, total_pages):
    html_str = templates.get_template("submittal_pdf.html").render({
        "q": quotation, "rows": rows, "today": date.today(), "total_pages": total_pages,
        "missing": sum(1 for r in rows if not r.get("page")), "request": None,
    })
    return HTML(string=html_str, base_url=".").write_pdf()


def _stamps(entries, total):
    """One PDF page per datasheet page, the same size, with only the strip
    on it - merged over the supplier's page afterwards."""
    css, body = [], []
    for i, e in enumerate(entries):
        css.append(f"@page s{i} {{ size: {e['w']:.2f}pt {e['h']:.2f}pt; margin: 0; }}")
        text = " · ".join(filter(None, [
            COMPANY.upper(), e["project"], ("Type " + e["types"]) if e["types"] else None, e["name"],
        ]))
        body.append(
            f'<div class="pg" style="page: s{i}"><div class="strip">'
            f'<span class="t">{html.escape(text)}</span>'
            f'<span class="n">Page {e["page"]} of {total}</span></div></div>')
    doc = f"""<html><head><meta charset="UTF-8"><style>
      @font-face {{ font-family: 'Inter'; font-weight: 400; src: url('app/static/fonts/Inter-Regular.ttf'); }}
      @font-face {{ font-family: 'Inter'; font-weight: 600; src: url('app/static/fonts/Inter-SemiBold.ttf'); }}
      {' '.join(css)}
      body {{ margin: 0; font-family: 'Inter', sans-serif; }}
      .pg {{ break-after: page; }}
      .strip {{ display: flex; justify-content: space-between; gap: 10pt; padding: 3.5pt 12pt;
                background: rgba(255,255,255,0.92); border-bottom: 0.6pt solid #C77D0A;
                font-size: 6.5pt; color: #3A362C; letter-spacing: 0.02em; }}
      .strip .t {{ white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
      .strip .n {{ white-space: nowrap; font-weight: 600; color: #C77D0A; }}
    </style></head><body>{''.join(body)}</body></html>"""
    return PdfReader(io.BytesIO(HTML(string=doc, base_url=".").write_pdf())).pages


def build(quotation, db, templates):
    """The submittal PDF as bytes."""
    rows = _rows(quotation, db)
    project = quotation.project.name if quotation.project else (quotation.subject or "")
    for r in rows:
        r["pages"] = _open_sheet(r["sheet"]) if r["sheet"] else None
        r["note"] = ("datasheet to follow" if r["sheet"] is None
                     else "file can't be read" if r["pages"] is None else "")
        r["types"] = ", ".join(r["types"]) if isinstance(r["types"], list) else r["types"]

    # Cover + index first with no page numbers, to know how many pages it takes
    for r in rows:
        r["page"] = r["last_page"] = None
    front_n = len(PdfReader(io.BytesIO(_render_front(templates, quotation, rows, 0))).pages)
    n = front_n + 1
    for r in rows:
        if r["pages"]:
            r["page"] = n
            n += len(r["pages"])
            r["last_page"] = n - 1
    total = n - 1
    front = PdfReader(io.BytesIO(_render_front(templates, quotation, rows, total)))

    writer = PdfWriter()
    for p in front.pages:
        writer.add_page(p)

    entries, pages = [], []
    page_no = front_n
    for r in rows:
        for p in r["pages"] or []:
            page_no += 1
            if p.get("/Rotate", 0) % 360:
                p.transfer_rotation_to_content()
            box = p.mediabox
            entries.append({"w": float(box.width), "h": float(box.height), "page": page_no,
                            "project": project, "types": r["types"], "name": r["name"]})
            pages.append(p)
    if pages:
        stamps = _stamps(entries, total)
        for p, s in zip(pages, stamps):
            box = p.mediabox
            p.merge_transformed_page(s, Transformation().translate(float(box.left), float(box.bottom)))
            writer.add_page(p)

    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()
