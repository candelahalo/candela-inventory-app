"""HALO datasheet made from a product's own data, in the RAPHAEL spec-sheet
layout: page 1 photo, dimension drawing and spec table; page 2 large photo,
description, colour, ordering code and features (page 2's texts come from the
product page and are left out when empty).

Used for any product whose datasheet choice is "HALO" - the default - so a
supplier's item can be issued under the HALO brand without uploading a PDF.
"""
import html
import os
import re
from datetime import date

from weasyprint import HTML

from app.utils import url_to_disk_path

ASSETS = os.path.abspath("app/static/halo")


def fields(spec):
    """[(label, value)] from "Label: value" lines of the spec summary."""
    out = []
    for line in (spec or "").splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r"([^:]+?)\s*:\s*(.+)", line)
        if m:
            out.append((m.group(1).strip(), m.group(2).strip()))
        else:
            k, _, v = line.partition(" ")
            out.append((k, v))
    return out


def _code_for(word, n):
    w = re.sub(r"[^A-Z]", "", word.upper())
    if not w:
        return ""
    cons = [c for c in w[1:] if c not in "AEIOU"]
    return (w[0] + "".join(cons))[:n]


def _swatch(finish):
    f = (finish or "").lower()
    for key, colour in (("white", "#ffffff"), ("black", "#1d1d1d"), ("grey", "#8d8d8d"), ("gray", "#8d8d8d"),
                        ("silver", "#c0c0c0"), ("gold", "#c8a24a"), ("brass", "#b5945a"), ("bronze", "#7b5a3a"),
                        ("champagne", "#d8c7a3")):
        if key in f:
            return colour
    return "#dddddd"


def _dim_svg(dim):
    nums = dict(re.findall(r"([LWHD])\s*(\d+(?:\.\d+)?)", (dim or "").upper()))
    if not nums:
        return ""
    if "L" in nums:  # linear: side view + section
        L, W, H = nums.get("L"), nums.get("W", "?"), nums.get("H", "?")
        return f'''<svg viewBox="0 0 300 120" width="250">
          <line x1="10" y1="18" x2="200" y2="18" stroke="#222" stroke-width=".8"/>
          <line x1="10" y1="13" x2="10" y2="23" stroke="#222" stroke-width=".8"/><line x1="200" y1="13" x2="200" y2="23" stroke="#222" stroke-width=".8"/>
          <text x="105" y="12" font-size="9" text-anchor="middle">{L}</text>
          <rect x="10" y="40" width="190" height="22" fill="none" stroke="#444" stroke-width=".9"/>
          <rect x="240" y="40" width="22" height="22" fill="none" stroke="#444" stroke-width=".9"/>
          <line x1="240" y1="78" x2="262" y2="78" stroke="#222" stroke-width=".8"/><text x="251" y="92" font-size="9" text-anchor="middle">{W}</text>
          <line x1="275" y1="40" x2="275" y2="62" stroke="#222" stroke-width=".8"/><text x="282" y="55" font-size="9">{H}</text>
        </svg>'''
    D, H = nums.get("D", nums.get("W", "?")), nums.get("H", "?")
    return f'''<svg viewBox="0 0 300 140" width="250">
      <circle cx="60" cy="70" r="45" fill="none" stroke="#444" stroke-width=".9"/>
      <circle cx="60" cy="70" r="30" fill="none" stroke="#999" stroke-width=".6"/>
      <line x1="15" y1="128" x2="105" y2="128" stroke="#222" stroke-width=".8"/><text x="60" y="140" font-size="9" text-anchor="middle">Ø {D}</text>
      <rect x="160" y="25" width="90" height="90" fill="none" stroke="#444" stroke-width=".9"/>
      <line x1="265" y1="25" x2="265" y2="115" stroke="#222" stroke-width=".8"/><text x="272" y="74" font-size="9">{H}</text>
    </svg>'''


def build(product) -> bytes:
    e = html.escape
    f = fields(product.spec_summary)
    get = lambda k: next((v for kk, v in f if kk.lower() == k.lower()), None)  # noqa: E731
    model = (get("Model") or product.name).split(",")[0].strip()
    words = model.split() or [product.name]
    family = words[0].title()
    variant = " ".join(w.title() if len(w) > 2 else w for w in words[1:])
    code = "-".join(filter(None, [_code_for(words[0], 3), _code_for(words[1], 2) if len(words) > 1 else ""]))
    ptype = get("Type") or product.category or "LED luminaire"
    dim = get("Dimension") or get("Dimensions")
    sub1 = f"{model} - {ptype}"
    sub2 = " - ".join(filter(None, [get("Wattage"), get("Luminous Flux"), get("CCT"),
                                    ("CRI " + get("CRI")) if get("CRI") else None, get("IP Rating")]))
    groups = [
        [("Product type", ptype), ("Mounting", get("Mounting")), ("Model", model), ("Dimensions", dim)],
        [("Wattage", get("Wattage")), ("Luminous flux", get("Luminous Flux")), ("Light source", get("Source")),
         ("CCT", get("CCT")), ("CRI", get("CRI")), ("Beam angle", get("Beam Angle")), ("Control", get("Control"))],
        [("Finish", get("Finish")), ("Protection", get("IP Rating"))],
        [("Warranty", get("Warranty"))],
    ]
    shown = {k.lower() for g in groups for k, v in g if v}
    used = {"model", "type", "dimension", "dimensions", "wattage", "luminous flux", "source", "cct", "cri",
            "beam angle", "control", "finish", "ip rating", "warranty", "mounting", "brand", "location"}
    extra = [(k, v) for k, v in f if k.lower() not in used and k.lower() not in shown and v]
    if extra:
        groups.insert(3, extra)
    table = "".join(
        '<div class="grp">' + "".join(f'<div class="row"><span>{e(k)}</span><span>{e(v)}</span></div>'
                                      for k, v in g if v) + "</div>"
        for g in groups if any(v for _, v in g))

    photo_path = url_to_disk_path(product.image_path) if product.image_path else None
    photo = (f'<img class="photo" src="file://{os.path.abspath(photo_path)}">'
             if photo_path and os.path.exists(photo_path) else '<div class="photo nophoto"></div>')
    big = (f'<img src="file://{os.path.abspath(photo_path)}">'
           if photo_path and os.path.exists(photo_path) else "")

    head = f'''<div class="head"><div class="title">{e(family)} <span>{e(variant)}</span></div>
      <div class="code">{e(code)}</div><div class="pag">Pag.{{n}}</div></div>'''
    foot = f'''<div class="foot"><img src="file://{ASSETS}/halo-logo.png"><div class="brand">HALO ARCHITECTURAL LIGHTS UK</div>
      <div class="upd">Last update: {date.today():%d/%m/%Y}</div></div>'''

    desc = (product.description or "").strip()
    feats = (product.features or "").strip()
    page2 = f'''<div class="page p2">{head.replace("{n}", "2")}
      <div class="left"><div class="bigphoto">{big}</div>
        {f'<div class="desc">{e(desc)}</div>' if desc else '<div style="height:6mm"></div>'}
        {f'<h4>Colours</h4><div style="margin-bottom:6mm"><span class="sw" style="background:{_swatch(get("Finish"))}"></span>{e(get("Finish"))}</div>' if get("Finish") else ''}
        <h4>Ordering information</h4>
        <table class="ord"><tr><th>Code</th><th>Description</th></tr>
          <tr><td>{e(product.sku)}</td><td>{e(product.name)}</td></tr></table></div>
      {f'<div class="right"><h4>Product features</h4><div class="desc">{e(feats)}</div></div>' if feats else ''}
      {foot}</div>'''

    doc = f'''<html><head><meta charset="UTF-8"><style>
    @font-face {{ font-family: Corm; src: url(file://{ASSETS}/cormorant-garamond-latin-400-normal.woff); }}
    @font-face {{ font-family: CormL; src: url(file://{ASSETS}/cormorant-garamond-latin-300-normal.woff); }}
    @font-face {{ font-family: Sans; src: url(file://{ASSETS}/LiberationSans-Regular.ttf); }}
    @font-face {{ font-family: Sans; font-weight: bold; src: url(file://{ASSETS}/LiberationSans-Bold.ttf); }}
    @page {{ size: A4; margin: 0; }}
    body {{ margin: 0; font-family: Sans; color: #222; font-size: 6.8pt; }}
    .page {{ width: 210mm; height: 297mm; position: relative; page-break-after: always; overflow: hidden; }}
    .page:last-child {{ page-break-after: auto; }}
    .page.p1::before {{ content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 49.6%; background: #ECEAE6; }}
    .head {{ position: absolute; left: 12.3mm; right: 12.3mm; top: 9mm; height: 16mm; border-bottom: .6pt solid #555; }}
    .title {{ position: absolute; left: 0; bottom: 1.6mm; font-family: Corm; font-size: 33pt; line-height: 1; }}
    .title span {{ font-family: CormL; font-size: 17pt; color: #8a8a8a; }}
    .code {{ position: absolute; left: 50.2%; bottom: 3.3mm; font-weight: bold; font-size: 16pt; }}
    .pag {{ position: absolute; right: 0; bottom: 3.6mm; font-weight: bold; font-size: 6pt; }}
    .right {{ position: absolute; left: 54.5%; right: 12.3mm; top: 32mm; }}
    .sub {{ font-weight: bold; font-size: 7.2pt; line-height: 1.45; margin-bottom: 6.5mm; }}
    .grp {{ margin-bottom: 6.5mm; }}
    .row {{ display: flex; border-bottom: .5pt solid #777; min-height: 6.1mm; align-items: center; }}
    .row span:first-child {{ width: 50.5%; flex: none; }}
    .left {{ position: absolute; left: 12.3mm; width: 82mm; top: 32mm; }}
    .photo {{ width: 46mm; height: 46mm; margin: 11mm auto 0; display: block; object-fit: contain; }}
    .nophoto {{ border: .5pt dashed #bbb; }}
    h4 {{ font-size: 6.8pt; margin: 0 0 3mm; }}
    .dims {{ margin-top: 22mm; }}
    .cap {{ color: #999; font-size: 6pt; margin-top: 3mm; }}
    .foot img {{ position: absolute; left: 12.3mm; bottom: 15.5mm; width: 25mm; }}
    .foot .brand {{ position: absolute; left: 12.3mm; bottom: 11.5mm; font-weight: bold; font-size: 5.6pt; }}
    .foot .upd {{ position: absolute; right: 12.3mm; bottom: 11.5mm; color: #999; font-size: 5.6pt; }}
    .p2 .left {{ width: 86mm; }}
    .p2 .bigphoto {{ background: #ECEAE6; height: 86mm; display: flex; align-items: center; justify-content: center; }}
    .p2 .bigphoto img {{ width: 48mm; height: 48mm; object-fit: contain; }}
    .desc {{ margin: 6mm 0 6mm; line-height: 1.45; font-size: 7pt; white-space: pre-line; }}
    .sw {{ display: inline-block; width: 7pt; height: 7pt; border-radius: 50%; border: .5pt solid #666; vertical-align: -1pt; margin-right: 4pt; }}
    table.ord {{ width: 100%; border-collapse: collapse; margin-top: 2mm; }}
    table.ord th {{ text-align: left; font-size: 6.8pt; padding: 2mm 0; border-bottom: .6pt solid #333; }}
    table.ord td {{ padding: 1.8mm 0; border-bottom: .5pt solid #888; }}
    </style></head><body>
    <div class="page p1">{head.replace("{n}", "1")}
      <div class="left">{photo}
        {f'<div class="dims"><h4>Technical dimensions</h4>{_dim_svg(dim)}<div class="cap">Dimensions (mm) · {e(dim)}</div></div>' if dim else ''}</div>
      <div class="right"><div class="sub">{e(sub1)}{('<br>' + e(sub2)) if sub2 else ''}</div>{table}</div>{foot}</div>
    {page2}
    </body></html>'''
    return HTML(string=doc).write_pdf()
