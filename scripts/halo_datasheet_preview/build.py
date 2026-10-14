"""Preview: a HALO spec sheet generated from a product's data, in the RAPHAEL layout."""
import re
import sys
from datetime import date
from pathlib import Path
from weasyprint import HTML

HERE = Path(__file__).parent


def fields(spec):
    out = []
    for line in spec.splitlines():
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


def code_for(word, n):
    w = re.sub(r"[^A-Z]", "", word.upper())
    if not w:
        return ""
    cons = [c for c in w[1:] if c not in "AEIOU"]
    return (w[0] + "".join(cons))[:n]


def dim_svg(dim):
    nums = dict(re.findall(r"([LWHD])\s*(\d+(?:\.\d+)?)", dim.upper()))
    if "L" in nums:   # linear: side view + section
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
    D, H = nums.get("D", "?"), nums.get("H", "?")
    return f'''<svg viewBox="0 0 300 140" width="250">
      <circle cx="60" cy="70" r="45" fill="none" stroke="#444" stroke-width=".9"/>
      <circle cx="60" cy="70" r="30" fill="none" stroke="#999" stroke-width=".6"/>
      <line x1="15" y1="128" x2="105" y2="128" stroke="#222" stroke-width=".8"/><text x="60" y="140" font-size="9" text-anchor="middle">Ø {D}</text>
      <rect x="160" y="25" width="90" height="90" fill="none" stroke="#444" stroke-width=".9"/>
      <line x1="265" y1="25" x2="265" y2="115" stroke="#222" stroke-width=".8"/><text x="272" y="74" font-size="9">{H}</text>
    </svg>'''


def build(p, out):
    f = fields(p["spec"])
    get = lambda k: next((v for kk, v in f if kk.lower() == k.lower()), None)  # noqa: E731
    model = (get("Model") or p["name"]).split(",")[0].strip()
    words = model.split()
    family, variant = words[0].title(), " ".join(w.title() if len(w) > 2 else w for w in words[1:])
    code = "-".join(filter(None, [code_for(words[0], 3), code_for(words[1], 2) if len(words) > 1 else ""]))
    ptype = p.get("ptype") or "LED luminaire"
    sub1 = f"{model} - {ptype}"
    sub2 = " - ".join(filter(None, [get("Wattage"), get("Luminous Flux"), get("CCT"), (("CRI " + get("CRI")) if get("CRI") else None), get("IP Rating")]))
    groups = [
        [("Product type", ptype), ("Mounting", p.get("mounting")), ("Model", model), ("Dimensions", get("Dimension"))],
        [("Wattage", get("Wattage")), ("Luminous flux", get("Luminous Flux")), ("Light source", get("Source")),
         ("CCT", get("CCT")), ("CRI", get("CRI")), ("Beam angle", get("Beam Angle")), ("Control", get("Control"))],
        [("Finish", get("Finish")), ("Protection", get("IP Rating"))],
        [("Warranty", get("Warranty"))],
    ]
    table = "".join(
        '<div class="grp">' + "".join(f'<div class="row"><span>{k}</span><span>{v}</span></div>' for k, v in g if v) + "</div>"
        for g in groups)
    head = f'''<div class="head"><div class="title">{family} <span>{variant}</span></div>
      <div class="code">{code}</div><div class="pag">Pag.{{n}}</div></div>'''
    foot = f'''<div class="foot"><img src="halo-logo.png"><div class="brand">HALO ARCHITECTURAL LIGHTS UK</div>
      <div class="upd">Last update: {date.today():%d/%m/%Y}</div></div>'''
    html = f'''<html><head><style>
    @font-face {{ font-family: Corm; src: url(cormorant-garamond-latin-400-normal.woff); }}
    @font-face {{ font-family: CormL; src: url(cormorant-garamond-latin-300-normal.woff); }}
    @font-face {{ font-family: Sans; src: url(LiberationSans-Regular.ttf); }}
    @font-face {{ font-family: Sans; font-weight: bold; src: url(LiberationSans-Bold.ttf); }}
    @page {{ size: A4; margin: 0; }}
    body {{ margin: 0; font-family: Sans; color: #222; font-size: 6.8pt; }}
    .page {{ width: 210mm; height: 297mm; position: relative; page-break-after: always; overflow: hidden; }}
    .page.p1::before {{ content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 49.6%; background: #ECEAE6; }}
    .head {{ position: absolute; left: 12.3mm; right: 12.3mm; top: 9mm; height: 16mm; border-bottom: .6pt solid #555; }}
    .title {{ position: absolute; left: 0; bottom: 1.6mm; font-family: Corm; font-size: 33pt; line-height: 1; }}
    .title span {{ font-family: CormL; font-size: 17pt; color: #8a8a8a; }}
    .code {{ position: absolute; left: 50.2%; bottom: 3.3mm; font-weight: bold; font-size: 16pt; }}
    .pag {{ position: absolute; right: 0; bottom: 3.6mm; font-weight: bold; font-size: 6pt; }}
    .right {{ position: absolute; left: 54.5%; right: 12.3mm; top: 32mm; }}
    .sub {{ font-weight: bold; font-size: 7.2pt; line-height: 1.45; margin-bottom: 6.5mm; }}
    .grp {{ margin-bottom: 6.5mm; }}
    .row {{ display: flex; border-bottom: .5pt solid #777; height: 6.1mm; align-items: center; }}
    .row span:first-child {{ width: 50.5%; }}
    .left {{ position: absolute; left: 12.3mm; width: 82mm; top: 32mm; }}
    .photo {{ width: 46mm; height: 46mm; margin: 11mm auto 0; display: block; object-fit: cover; }}
    h4 {{ font-size: 6.8pt; margin: 0 0 3mm; }}
    .dims {{ margin-top: 22mm; }}
    .cap {{ color: #999; font-size: 6pt; margin-top: 3mm; }}
    .foot img {{ position: absolute; left: 12.3mm; bottom: 15.5mm; width: 25mm; }}
    .foot .brand {{ position: absolute; left: 12.3mm; bottom: 11.5mm; font-weight: bold; font-size: 5.6pt; }}
    .foot .upd {{ position: absolute; right: 12.3mm; bottom: 11.5mm; color: #999; font-size: 5.6pt; }}
    .p2 .left {{ width: 86mm; }}
    .p2 .bigphoto {{ background: #ECEAE6; height: 86mm; display: flex; align-items: center; justify-content: center; margin-top: 0; }}
    .p2 .bigphoto img {{ width: 48mm; height: 48mm; object-fit: cover; }}
    .desc {{ margin: 6mm 0 6mm; line-height: 1.45; font-size: 7pt; }}
    .ph {{ color: #b0473a; }}
    .sw {{ display: inline-block; width: 7pt; height: 7pt; border-radius: 50%; border: .5pt solid #666; vertical-align: -1pt; margin-right: 4pt; }}
    table.ord {{ width: 100%; border-collapse: collapse; margin-top: 2mm; }}
    table.ord th {{ text-align: left; font-size: 6.8pt; padding: 2mm 0; border-bottom: .6pt solid #333; }}
    table.ord td {{ padding: 1.8mm 0; border-bottom: .5pt solid #888; }}
    </style></head><body>
    <div class="page p1">{head.replace("{n}", "1")}
      <div class="left"><img class="photo" src="{p["photo"]}">
        <div class="dims"><h4>Technical dimensions</h4>{dim_svg(get("Dimension") or "")}
        <div class="cap">Dimensions (mm) · {get("Dimension") or ""}</div></div></div>
      <div class="right"><div class="sub">{sub1}<br>{sub2}</div>{table}</div>{foot}</div>
    <div class="page p2">{head.replace("{n}", "2")}
      <div class="left"><div class="bigphoto"><img src="{p["photo"]}"></div>
        <div class="desc ph">[Short description of the product — written once on the product page]</div>
        <h4>Colours</h4><div style="margin-bottom:6mm"><span class="sw" style="background:{p["swatch"]}"></span>{get("Finish")}</div>
        <h4>Ordering information</h4>
        <table class="ord"><tr><th>Code</th><th>Description</th></tr>
          <tr><td>{p["sku"]}</td><td>{p["name"]}</td></tr></table></div>
      <div class="right"><h4>Product features</h4><div class="desc ph">[Features text — optional, from the product page]</div></div>
      {foot}</div>
    </body></html>'''
    HTML(string=html, base_url=str(HERE)).write_pdf(out)


if __name__ == "__main__":
    build({"sku": "HALO-SLIDE-SUSPENDED-50WM-30K-GY", "name": "SLIDE SUSPENDED 50W/M 3000K Grey", "photo": "slide.jpg",
           "ptype": "Linear suspended LED", "mounting": "Suspended", "swatch": "#8d8d8d",
           "spec": open(HERE / "slide.txt").read()}, HERE / "preview-slide.pdf")
    build({"sku": "HALO-AGE-M-15W-40K-WH", "name": "AGE M 15W 4000K White", "photo": "age.jpg",
           "ptype": "Adjustable LED downlight", "mounting": "Recessed", "swatch": "#ffffff",
           "spec": open(HERE / "age.txt").read()}, HERE / "preview-age.pdf")
