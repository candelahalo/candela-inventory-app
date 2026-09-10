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
FONT = "IBM Plex Sans"

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


def build_pdf(title, rows, columns, subtitle=None, landscape=False, filename=None):
    """
    columns: list of dicts - {"key", "label", "kind"?, "width"?}
             kind is one of text | number | money | date | datetime
    rows:    list of dicts keyed by column key
    """
    prepared = []
    for r in rows:
        prepared.append([
            {"text": _fmt(r.get(c["key"]), c.get("kind", "text")),
             "numeric": c.get("kind") in ("number", "money")}
            for c in columns
        ])

    html = templates.get_template("report_pdf.html").render({
        "request": None,
        "title": title,
        "subtitle": subtitle,
        "columns": columns,
        "rows": prepared,
        "generated": datetime.utcnow(),
        "landscape": landscape,
        "count": len(rows),
    })
    pdf = HTML(string=html, base_url=".").write_pdf()
    name = filename or f"{title.lower().replace(' ', '-')}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


def build_excel(title, rows, columns, subtitle=None, filename=None):
    wb = Workbook()
    ws = wb.active
    ws.title = title[:28]
    ws.sheet_view.showGridLines = False

    center = Alignment(horizontal="center", vertical="center")
    left = Alignment(horizontal="left", vertical="center", wrap_text=True)
    right = Alignment(horizontal="right", vertical="center")
    thin = Side(style="thin", color=LINE)
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    ncols = len(columns)
    last_col = get_column_letter(ncols)

    # Letterhead
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
    ws["A4"] = subtitle or f"{len(rows)} records · generated {datetime.utcnow().strftime('%d %b %Y')}"
    ws["A4"].font = Font(name=FONT, size=9.5, color=FAINT)

    header_row = 6
    for i, c in enumerate(columns, start=1):
        cell = ws.cell(row=header_row, column=i, value=c["label"].upper())
        cell.fill = PatternFill(start_color=INK, end_color=INK, fill_type="solid")
        cell.font = Font(name=FONT, color="FFFFFF", bold=True, size=8.5)
        cell.alignment = center
        cell.border = border
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
                cell.alignment = right
            else:
                cell = ws.cell(row=row_i, column=i, value=_fmt(raw, kind))
                cell.alignment = center if kind in ("date", "datetime") else left
            cell.font = Font(name=FONT, size=9.5, color=INK)
            cell.border = border
            if fill:
                cell.fill = fill
        row_i += 1

    # Column widths from the content, within sensible bounds
    for i, c in enumerate(columns, start=1):
        longest = max([len(str(c["label"]))] +
                      [len(_fmt(r.get(c["key"]), c.get("kind", "text"))) for r in rows] or [10])
        ws.column_dimensions[get_column_letter(i)].width = min(max(longest + 3, 9), 42)

    ws.freeze_panes = ws.cell(row=header_row + 1, column=1)
    ws.auto_filter.ref = f"A{header_row}:{last_col}{max(row_i - 1, header_row)}"

    ws.page_setup.orientation = "landscape" if ncols > 6 else "portrait"
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_options.horizontalCentered = True
    ws.print_title_rows = f"{header_row}:{header_row}"
    ws.page_margins = PageMargins(left=0.4, right=0.4, top=0.6, bottom=0.6)
    ws.oddFooter.center.text = "Page &P of &N"
    ws.oddFooter.center.size = 8
    ws.oddFooter.center.color = FAINT

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    name = filename or f"{title.lower().replace(' ', '-')}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )
