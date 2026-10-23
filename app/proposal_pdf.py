"""The automation proposal PDF.

By system (full=0): the template as it is.
Full proposal (full=1): the template, then the first page of each product's
datasheet put in after the covering letter (before the general remarks), and
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


def _numbers(n, skip_first=True):
    """n A4 pages with only "Page x of n" at the bottom right (none on the cover)."""
    body = "".join(f'<div class="pg"><span>{"" if (skip_first and i == 1) else f"Page {i} of {n}"}</span></div>'
                   for i in range(1, n + 1))
    doc = f"""<html><head><meta charset="UTF-8"><style>
      @font-face {{ font-family: 'Inter'; src: url('app/static/fonts/Inter-Regular.ttf'); }}
      @page {{ size: A4; margin: 0; }}
      body {{ margin: 0; font-family: 'Inter', sans-serif; }}
      .pg {{ position: relative; width: 210mm; height: 297mm; break-after: page; }}
      .pg span {{ position: absolute; right: 18mm; bottom: 8.6mm; font-size: 7.5px; color: #9A9382; }}
    </style></head><body>{body}</body></html>"""
    return PdfReader(io.BytesIO(HTML(string=doc, base_url=".").write_pdf())).pages


def build(q, db, full=False):
    doc = _render(q, db, full)
    if not full:
        return doc.write_pdf()
    at = _marker_page(doc, "General remarks")
    main = list(PdfReader(io.BytesIO(doc.write_pdf())).pages)
    at = at if at is not None else min(2, len(main))
    sheets = _sheet_pages(q, db)
    pages = main[:at] + sheets + main[at:]
    writer = PdfWriter()
    for p, num in zip(pages, _numbers(len(pages))):
        p.merge_page(num)
        writer.add_page(p)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()
