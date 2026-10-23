"""Supplier bill / invoice / quotation PDF -> item lines (code, description,
qty, unit price), for adding the items to the product list.

Bills come in every layout, so nothing here depends on column positions: a
line is an item when it holds three numbers in a row where qty x unit price =
amount. Text before them is the code and description; anything after (HS
code, country of origin) is ignored. A line with no numbers just below an item
continues its description; an all-capitals line before items is a section
heading (CCTV SYSTEM, WI-FI).
"""
import io
import re

from app.datasheet_read import BRANDS, GENERAL_BRANDS

NUM = re.compile(r"^[($]?(?:US\$|\$|€|AED|USD|EUR)?\s?(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?\)?$")
CODE = re.compile(r"^(?=.*\d)[A-Z0-9][A-Z0-9\-./]{3,}[A-Z0-9]$")
STOP = re.compile(r"^(sub\s*total|total|taxable|vat|grand total|amount in words|net)\b", re.I)
BRAND_ALIASES = {"D LINK": "D-LINK", "D-LINK": "D-LINK", "DLINK": "D-LINK", "RUIJIE": "RUIJIE", "REYEE": "RUIJIE",
                 "TP LINK": "TP-LINK", "TP-LINK": "TP-LINK", "MERAKI": "CISCO", "UNIFI": "UBIQUITI", "HAGER": "HAGER"}
ALL_BRANDS = [b for b in dict.fromkeys(GENERAL_BRANDS + BRANDS) if b not in ("KNX", "DALI", "B&W", "TPLINK")]


def _num(tok):
    m = NUM.match(tok.strip())
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", "") + (m.group(2) or ""))
    except ValueError:
        return None


def _lines(data):
    """Each text line of the PDF as a list of words (text, x0), top to bottom."""
    import pdfplumber
    out = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            words = page.extract_words(keep_blank_chars=False, use_text_flow=False, x_tolerance=1.5)
            rows = []
            for w in sorted(words, key=lambda w: (round(w["top"]), w["x0"])):
                if rows and abs(rows[-1]["top"] - w["top"]) <= 3:
                    rows[-1]["words"].append(w)
                else:
                    rows.append({"top": w["top"], "h": w["bottom"] - w["top"], "words": [w]})
            for r in rows:
                ws = sorted(r["words"], key=lambda w: w["x0"])
                out.append({"page": page.page_number, "top": r["top"], "h": r["h"],
                            "toks": [w["text"] for w in ws], "xs": [w["x0"] for w in ws]})
    return out


def _triple(toks):
    """Index of qty, unit price, amount in the tokens (qty x price = amount)."""
    vals = [_num(t) for t in toks]
    for i in range(1, len(toks) - 2):  # at least one word of description before
        q, p, a = vals[i], vals[i + 1], vals[i + 2]
        if q is None or p is None or a is None or q <= 0 or q > 100000:
            continue
        if abs(q * p - a) <= max(0.05, a * 0.005):
            return i
    return None


def _brand(text):
    up = " " + re.sub(r"\s+", " ", text.upper()) + " "
    for k, v in BRAND_ALIASES.items():
        if re.search(r"(?<![A-Z0-9])" + re.escape(k) + r"(?![A-Z0-9])", up):
            return v
    for b in ALL_BRANDS:
        if re.search(r"(?<![A-Z0-9])" + re.escape(b) + r"(?![A-Z0-9])", up):
            return b
    return ""


def _currency(text):
    m = re.search(r"currency[^\n:]*:\s*(USD|EUR|AED)", text, re.I)
    if m:
        return m.group(1).upper()
    counts = {"USD": len(re.findall(r"\bUSD\b|US\$|\$", text)),
              "EUR": len(re.findall(r"\bEUR\b|€", text)),
              "AED": len(re.findall(r"\bAED\b|\bDHS?\b|dirham", text, re.I))}
    best = max(counts, key=counts.get)
    return best if counts[best] else "AED"


def read(data, filename=""):
    lines = _lines(data)
    text = "\n".join(" ".join(l["toks"]) for l in lines)
    items, section, last, header_end = [], "", None, 12
    for l in lines:
        toks = l["toks"]
        i = _triple(toks)
        if i is not None and not STOP.match(" ".join(toks[:i])):
            desc_toks = toks[:i]
            if not items:
                header_end = len([x for x in lines if x is not l and (x["page"], x["top"]) < (l["page"], l["top"])])
            items.append({"lead": desc_toks, "x": l["xs"][0], "qty": _num(toks[i]),
                          "unit_price": _num(toks[i + 1]), "amount": _num(toks[i + 2]),
                          "section": section, "page": l["page"], "top": l["top"], "h": l["h"]})
            last = items[-1]
            continue
        joined = " ".join(toks).strip()
        if not joined or STOP.match(joined) or any(_num(t) is not None and "." in t for t in toks):
            last = None if STOP.match(joined) else last
            continue
        near = last and last["page"] == l["page"] and 0 < l["top"] - last["top"] <= last["h"] * 2.6 + 4
        if near and not (joined.isupper() and len(joined) < 40):
            last["lead"] = last["lead"] + toks  # description runs onto a second line
            last["top"] = l["top"]
            continue
        last = None
        if joined.isupper() and 2 < len(joined) < 40 and not re.search(r"\d{4,}|:", joined) \
                and not re.search(r"INVOICE|QUOTATION|PROFORMA|DELIVERY|L\.?L\.?C|TRADING|\bFZE\b|\bFZCO\b|DESCRIPTION|\bQTY\b", joined):
            section = joined.title() if len(joined) > 4 else joined

    # Sr. numbers 1, 2, 3 ... in front of the description: drop them
    firsts = [it["lead"][0] for it in items if it["lead"]]
    serial = len(items) >= 2 and sum(1 for k, f in enumerate(firsts) if f.rstrip(".") == str(k + 1)) >= len(items) * 0.6

    doc_brand = _brand(" ".join(" ".join(l["toks"]) for l in lines[:header_end]))
    out = []
    for it in items:
        lead = list(it["lead"])
        if serial and lead and re.fullmatch(r"\d{1,3}\.?", lead[0]):
            lead = lead[1:]
        code = ""
        if lead and CODE.match(lead[0]) and (re.search(r"[A-Z]", lead[0]) or len(lead[0]) >= 6) and len(lead) > 1:
            code, lead = lead[0], lead[1:]
        desc = re.sub(r"\s*\((?:lot|pcs?|nos?)\)\s*$", "", " ".join(lead), flags=re.I).strip(" -–:")
        if not desc:
            continue
        unit = "lot" if re.search(r"\(lot\)|\blot\b", " ".join(it["lead"]), re.I) else "pcs"
        out.append({"code": code, "description": desc, "brand": _brand(desc) or doc_brand,
                    "qty": it["qty"], "unit_price": round(it["unit_price"], 4), "amount": it["amount"],
                    "unit": unit, "section": it["section"],
                    "service": bool(re.search(r"installation|commissioning|configuration|programming|labou?r|support|testing", desc, re.I))})
    return {"currency": _currency(text), "brand": doc_brand, "lines": out}
