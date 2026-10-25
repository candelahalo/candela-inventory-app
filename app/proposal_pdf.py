"""The automation proposal PDF.

By system (full=0): the template as it is.
Full proposal (full=1): the template, then the first page of each product's
datasheet put in after the product images, before the equipment by system (can
be turned off), and
the page numbers stamped on at the end so they count the datasheet pages too.
"""
import io

from pypdf import PdfReader, PdfWriter, Transformation, PageObject
from weasyprint import HTML

A4_W, A4_H = 595.28, 841.89


def _render(q, db, full):
    from app.entity import for_quotation
    from app.proposal import build_context
    from app import proposal_terms
    from app.routers.quotations import templates
    html = templates.get_template("quotation_proposal.html").render(
        {"q": q, "p": build_context(q, proposal_terms.get(db)), "ent": for_quotation(q), "full": full})
    return HTML(string=html, base_url=".").render()


def _marker_pages(doc, label):
    """Indexes of every page holding a bookmark with this label."""
    out = []
    def walk(items):
        for it in items:
            if it[0] == label:
                out.append(it[1][0])
            walk(it[2] if len(it) > 2 else [])
    walk(doc.make_bookmark_tree())
    return out


def _marker_page(doc, label):
    """Index of the page holding the bookmark with this label (None if absent)."""
    def walk(items):
        for it in items:
            lab, target = it[0], it[1]
            if lab == label:
                return target[0]
            found = walk(it[2] if len(it) > 2 else [])
            if found is not None:
                return found
        return None
    return walk(doc.make_bookmark_tree())


def _sheet_pages(q, db):
    """First page of each product's datasheet, in quote order, fitted to A4."""
    from app import submittal
    out = []
    for e in submittal._items(q, db):
        if e["what"] == "auto":
            from app import halo_sheet
            pages = list(PdfReader(io.BytesIO(halo_sheet.build(e["product"]))).pages)
        elif e["what"] == "file":
            pages = submittal._pages(e["sheet"])
        else:
            continue
        if not pages:
            continue
        src = pages[0]
        try:
            if src.get("/Rotate", 0) % 360:
                src.transfer_rotation_to_content()
            box = src.mediabox
            w, h = float(box.width), float(box.height)
            page = PageObject.create_blank_page(width=A4_W, height=A4_H)
            k = min(A4_W / w, A4_H / h)
            tx = (A4_W - w * k) / 2 - float(box.left) * k
            ty = (A4_H - h * k) / 2 - float(box.bottom) * k
            page.merge_transformed_page(src, Transformation().scale(k, k).translate(tx, ty))
            out.append(page)
        except Exception:
            continue
    return out


def _numbers(n, skip=()):
    """n A4 pages with only "Page x of n" at the bottom right (none on the cover or full-bleed photos)."""
    body = "".join(f'<div class="pg"><span>{"" if (i == 1 or i in skip) else f"Page {i} of {n}"}</span></div>'
                   for i in range(1, n + 1))
    doc = f"""<html><head><meta charset="UTF-8"><style>
      @font-face {{ font-family: 'Inter'; src: url('app/static/fonts/Inter-Regular.ttf'); }}
      @page {{ size: A4; margin: 0; }}
      body {{ margin: 0; font-family: 'Inter', sans-serif; }}
      .pg {{ position: relative; width: 210mm; height: 297mm; break-after: page; }}
      .pg span {{ position: absolute; right: 18mm; bottom: 8.6mm; font-size: 7.5px; color: #9A9382; }}
    </style></head><body>{body}</body></html>"""
    return PdfReader(io.BytesIO(HTML(string=doc, base_url=".").write_pdf())).pages


def _slides(q, db):
    """The landscape technical submittal: slides like a presentation (no datasheets)."""
    from app.entity import for_quotation
    from app.proposal import build_context, slide_gallery
    from app import proposal_terms
    from app.routers.quotations import templates
    p = build_context(q, proposal_terms.get(db))
    p["slide_gallery"] = slide_gallery(q)
    html = templates.get_template("quotation_slides.html").render({"q": q, "p": p, "ent": for_quotation(q)})
    return HTML(string=html, base_url=".").write_pdf()


def build(q, db, full=False):
    if full and (getattr(q, "proposal_layout", None) or "portrait") == "landscape":
        return _slides(q, db)
    doc = _render(q, db, full)
    if not full:
        return doc.write_pdf()
    at = _marker_page(doc, "Equipment by system")   # datasheets: after the product images
    main = list(PdfReader(io.BytesIO(doc.write_pdf())).pages)
    at = at if at is not None else min(2, len(main))
    sheets = _sheet_pages(q, db) if getattr(q, "proposal_datasheets", True) is not False else []
    pages = main[:at] + sheets + main[at:]
    # full-bleed photo pages: no page number on the photo (1-based numbers after the datasheets went in)
    skip = {i + 1 + (len(sheets) if i >= at else 0) for i in _marker_pages(doc, "nonum")}
    writer = PdfWriter()
    for p, num in zip(pages, _numbers(len(pages), skip)):
        p.merge_page(num)
        writer.add_page(p)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()
