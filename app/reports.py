"""
Shared report generator.

Every list page (Products, Stock, Customers, Projects, Activity...) exports
through here, so the styling, letterhead and print setup stay identical
rather than drifting apart per page.

A caller supplies a title, column definitions and rows; this handles the
Candela letterhead, table layout, totals row, and A4 page setup.
"""
import io
import os
from datetime import datetime

from fastapi.responses import StreamingResponse
from fastapi.templating import Jinja2Templates
from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.page import PageMargins
from PIL import Image as PILImage
from weasyprint import HTML

templates = Jinja2Templates(directory="app/templates")

INK = "201E1A"
MUTED = "56503F"
FAINT = "9A9382"
LINE = "DED6C2"
PAPER = "FBF9F4"
FONT = "Arial"

LOGO_PATH = "app/static/candela-logo-dark.png"


def _fmt(value, kind):
    if value is None or value == "":
        return "—"
    if kind == "money":
        return f"{float(value):,.2f}"
    if kind == "number":
        return f"{value:,}" if isinstance(value, (int, float)) else str(value)
    if kind == "date":
        if isinstance(value, str):
            try:
                value = datetime.fromisoformat(value.replace("Z", ""))
            except ValueError:
                return value
        return value.strftime("%d %b %Y")
    if kind == "datetime":
        if isinstance(value, str):
            try:
                value = datetime.fromisoformat(value.replace("Z", ""))
            except ValueError:
                return value
        return value.strftime("%d %b %Y, %I:%M %p")
    return str(value)


def _disposition(name, inline):
    # "inline" makes the browser open the PDF in its own viewer (Preview);
    # "attachment" saves it as a download.
    return f'{"inline" if inline else "attachment"}; filename="{name}"'


def _prepare(rows, columns):
    return [[{"text": _fmt(r.get(c["key"]), c.get("kind", "text")),
              "numeric": c.get("kind") in ("number", "money")} for c in columns] for r in rows]


def build_pdf(title, rows, columns, subtitle=None, landscape=False, filename=None, inline=False):
    """
    A single-table report (every list page).

    columns: list of dicts - {"key", "label", "kind"?, "width"?}
             kind is one of text | number | money | date | datetime
    rows:    list of dicts keyed by column key
    """
    return build_record_pdf(
        title, subtitle=subtitle, sections=[{"title": None, "columns": columns, "rows": rows}],
        landscape=landscape, filename=filename, inline=inline, count=len(rows),
    )


def build_record_pdf(title, subtitle=None, details=None, sections=(), landscape=False,
                     filename=None, inline=False, count=None, empty_text="Nothing to report."):
    """
    A report about one thing (a project, a product, the dashboard): an
    optional block of label/value details followed by any number of titled
    tables. details: list of (label, value). sections: list of
    {"title", "columns", "rows", "empty"?}.
    """
    html = templates.get_template("report_pdf.html").render({
        "request": None,
        "title": title,
        "subtitle": subtitle,
        "details": [(label, "—" if value in (None, "") else value) for label, value in (details or [])],
        "sections": [{
            "title": sec.get("title"),
            "columns": sec["columns"],
            "rows": _prepare(sec["rows"], sec["columns"]),
            "empty": sec.get("empty", empty_text),
        } for sec in sections],
        "generated": datetime.utcnow(),
        "landscape": landscape,
        "count": count,
    })
    pdf = HTML(string=html, base_url=".").write_pdf()
    name = filename or f"{title.lower().replace(' ', '-')}.pdf"
    return StreamingResponse(io.BytesIO(pdf), media_type="application/pdf",
                             headers={"Content-Disposition": _disposition(name, inline)})


# ---------- Excel ----------

def _xl_styles():
    thin = Side(style="thin", color=LINE)
    return {
        "center": Alignment(horizontal="center", vertical="center"),
        "left": Alignment(horizontal="left", vertical="center", wrap_text=True),
        "right": Alignment(horizontal="right", vertical="center"),
        "border": Border(left=thin, right=thin, top=thin, bottom=thin),
    }


def _xl_letterhead(ws, title, subtitle, ncols):
    last_col = get_column_letter(max(ncols, 2))
    if os.path.exists(LOGO_PATH):
        with PILImage.open(LOGO_PATH) as im:
            w, h = im.size
        img = XLImage(LOGO_PATH)
        img.height = 30
        img.width = int(w * (30 / h))
        ws.add_image(img, "A1")
    ws.row_dimensions[1].height = 28

    ws.merge_cells(f"A3:{last_col}3")
    ws["A3"] = title
    ws["A3"].font = Font(name=FONT, size=15, bold=True, color=INK)
    ws.row_dimensions[3].height = 22

    ws.merge_cells(f"A4:{last_col}4")
    ws["A4"] = subtitle or f"Generated {datetime.utcnow().strftime('%d %b %Y')}"
    ws["A4"].font = Font(name=FONT, size=9.5, color=FAINT)


def _xl_table(ws, start_row, columns, rows, st):
    """Write a header row plus data rows from start_row. Returns (header_row, next_free_row)."""
    header_row = start_row
    for i, c in enumerate(columns, start=1):
        cell = ws.cell(row=header_row, column=i, value=c["label"].upper())
        cell.fill = PatternFill(start_color=INK, end_color=INK, fill_type="solid")
        cell.font = Font(name=FONT, color="FFFFFF", bold=True, size=8.5)
        cell.alignment = st["center"]
        cell.border = st["border"]
    ws.row_dimensions[header_row].height = 20

    row_i = header_row + 1
    for n, r in enumerate(rows, start=1):
        fill = PatternFill(start_color=PAPER, end_color=PAPER, fill_type="solid") if n % 2 == 0 else None
        for i, c in enumerate(columns, start=1):
            kind = c.get("kind", "text")
            raw = r.get(c["key"])
            # Keep numbers as numbers so the sheet stays sortable and sum-able
            if kind in ("money", "number") and isinstance(raw, (int, float)):
                cell = ws.cell(row=row_i, column=i, value=raw)
                cell.number_format = '#,##0.00' if kind == "money" else '#,##0'
                cell.alignment = st["right"]
            else:
                cell = ws.cell(row=row_i, column=i, value=_fmt(raw, kind))
                cell.alignment = st["center"] if kind in ("date", "datetime") else st["left"]
            cell.font = Font(name=FONT, size=9.5, color=INK)
            cell.border = st["border"]
            if fill:
                cell.fill = fill
        row_i += 1
    return header_row, row_i


def _xl_widths(ws, tables, extra=()):
    """Size each column to its longest content across every table, within bounds."""
    widths = {}
    for columns, rows in tables:
        for i, c in enumerate(columns, start=1):
            lens = [len(str(c["label"]))] + [len(_fmt(r.get(c["key"]), c.get("kind", "text"))) for r in rows]
            widths[i] = max(widths.get(i, 0), max(lens))
    for i, n in extra:
        widths[i] = max(widths.get(i, 0), n)
    for i, n in widths.items():
        ws.column_dimensions[get_column_letter(i)].width = min(max(n + 3, 9), 42)


def _xl_print_setup(ws, ncols, header_row=None):
    ws.page_setup.orientation = "landscape" if ncols > 6 else "portrait"
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_options.horizontalCentered = True
    if header_row:
        ws.print_title_rows = f"{header_row}:{header_row}"
    ws.page_margins = PageMargins(left=0.4, right=0.4, top=0.6, bottom=0.6)
    ws.oddFooter.center.text = "Page &P of &N"
    ws.oddFooter.center.size = 8
    ws.oddFooter.center.color = FAINT


def _xl_response(wb, name):
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": _disposition(name, False)},
    )


def build_excel(title, rows, columns, subtitle=None, filename=None):
    wb = Workbook()
    ws = wb.active
    ws.title = title[:28]
    ws.sheet_view.showGridLines = False
    st = _xl_styles()

    ncols = len(columns)
    _xl_letterhead(ws, title, subtitle or f"{len(rows)} records · generated {datetime.utcnow().strftime('%d %b %Y')}", ncols)
    header_row, row_i = _xl_table(ws, 6, columns, rows, st)
    _xl_widths(ws, [(columns, rows)])

    ws.freeze_panes = ws.cell(row=header_row + 1, column=1)
    ws.auto_filter.ref = f"A{header_row}:{get_column_letter(ncols)}{max(row_i - 1, header_row)}"
    _xl_print_setup(ws, ncols, header_row)
    return _xl_response(wb, filename or f"{title.lower().replace(' ', '-')}.xlsx")


def build_record_excel(title, subtitle=None, details=None, sections=(), filename=None,
                       empty_text="Nothing to report."):
    """Excel twin of build_record_pdf: details block, then each section as its own table."""
    wb = Workbook()
    ws = wb.active
    ws.title = title[:28].replace("/", "-")
    ws.sheet_view.showGridLines = False
    st = _xl_styles()

    ncols = max([len(sec["columns"]) for sec in sections] + [2])
    _xl_letterhead(ws, title, subtitle, ncols)
    row_i = 6
    extra = []

    if details:
        for label, value in details:
            lc = ws.cell(row=row_i, column=1, value=label)
            lc.font = Font(name=FONT, size=9.5, bold=True, color=MUTED)
            lc.alignment = st["left"]
            vc = ws.cell(row=row_i, column=2, value="—" if value in (None, "") else value)
            vc.font = Font(name=FONT, size=9.5, color=INK)
            vc.alignment = st["left"]
            if ncols > 2:
                ws.merge_cells(start_row=row_i, start_column=2, end_row=row_i, end_column=ncols)
            extra.append((1, len(str(label))))
            row_i += 1
        row_i += 1

    for sec in sections:
        if sec.get("title"):
            h = ws.cell(row=row_i, column=1, value=sec["title"])
            h.font = Font(name=FONT, size=11.5, bold=True, color=INK)
            row_i += 1
        if sec["rows"]:
            _, row_i = _xl_table(ws, row_i, sec["columns"], sec["rows"], st)
        else:
            e = ws.cell(row=row_i, column=1, value=sec.get("empty", empty_text))
            e.font = Font(name=FONT, size=9.5, italic=True, color=FAINT)
            row_i += 1
        row_i += 1

    _xl_widths(ws, [(sec["columns"], sec["rows"]) for sec in sections], extra)
    _xl_print_setup(ws, ncols)
    return _xl_response(wb, filename or f"{title.lower().replace(' ', '-')}.xlsx")
