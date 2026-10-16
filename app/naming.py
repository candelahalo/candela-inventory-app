"""One naming pattern for every product: name in capitals, SKU in the same
order.

    Lights       KOR S 17W 3000K WHITE                QB-KOR-S-17W-30K-WH
    Drivers      DRIVER ON/OFF — KOR 17W              TRI-DRV-KOR-17W
    Accessories  BAMBOO ENDCAP                        QB-BAMBOO-ENDCAP

Accessories lead with the family they belong to ("Endcap (BAMBOO)" becomes
"BAMBOO ENDCAP"); drivers say what they are, then what they drive. The brand
is its own field, so it isn't repeated in the name.
"""
import re

SKU_PREFIX = {"QUATTROBI": "QB", "TRIDONIC": "TRI", "HALO": "HALO", "RUHA": "RUHA", "LEDVANCE": "LDV",
              "OSRAM": "OSR", "PHILIPS": "PHL", "MEAN WELL": "MW", "MEANWELL": "MW", "LUTRON": "LUT",
              "HELVAR": "HLV", "IGUZZINI": "IGZ", "FLOS": "FLOS", "ERCO": "ERCO", "DELTA LIGHT": "DLT"}
FINISH_CODE = {"WHITE": "WH", "BLACK": "BK", "GREY": "GY", "GRAY": "GY", "SILVER": "SL", "GOLD": "GD",
               "BRONZE": "BZ", "BRASS": "BR", "CHAMPAGNE": "CH"}


def _clean(s):
    return " ".join((s or "").replace(" ", " ").split())


def _units(s):
    """Same spelling for units: 15 W/m -> 15W/M, 1 Mtr -> 1M, 2200 mm -> 2200MM."""
    s = re.sub(r"(\d)\s*W\s*/\s*M\b", r"\1W/M", s, flags=re.I)
    s = re.sub(r"(\d)\s*(W|K|MM|LM)\b", r"\1\2", s, flags=re.I)
    s = re.sub(r"(\d+(?:\.\d+)?)\s*(MTRS?|METERS?|METRES?|MTR)\b", r"\1M", s, flags=re.I)
    return s


def _strip_brand(s, brand):
    if brand:
        s = re.sub(r"\b" + re.escape(brand) + r"\b", "", s, flags=re.I)
    return _clean(s)


def standard_name(name, brand=None, category=None):
    """The product name in the shared pattern (capitals, fixed order)."""
    n = _clean(name)
    if not n:
        return n
    n = _units(n)
    cat = (category or "").lower()
    m = re.match(r"(.*?)\b(?:dimmable\s+)?driver\b\s*(?:for(?: the)?\s+(.+))?$", n, flags=re.I)
    if cat == "drivers" or m:
        if m:
            kind = _strip_brand(m.group(1), brand)
            kind = re.sub(r"\bdimmable\b", "", kind, flags=re.I).strip()
            dimm = " DIMMABLE" if re.search(r"dimmable", n, re.I) and "1-10" not in kind else ""
            target = _clean(m.group(2) or "")
            parts = ["DRIVER", (kind + dimm).strip()]
            out = " ".join(p for p in parts if p)
            return (out + (" — " + target if target else "")).upper()
    # "Thing (FAMILY)" -> "FAMILY THING" for accessories
    m = re.match(r"(.+?)\s*\(([^()]+)\)$", n)
    if m:
        thing, family = _clean(m.group(1)), _clean(m.group(2))
        if family.upper() not in thing.upper():
            n = f"{family} {thing}"
        else:
            n = thing
    return _strip_brand(n, brand).upper() if brand and brand.upper() != n.upper() else n.upper()


def _slug(s):
    return re.sub(r"[^A-Z0-9]+", "-", (s or "").upper()).strip("-")


def standard_sku(name, brand=None, category=None):
    """SKU in the same order as the (standard) name: PREFIX-MODEL-WATT-CCT-FINISH."""
    n = standard_name(name, brand, category)
    b = (brand or "").upper().strip()
    prefix = SKU_PREFIX.get(b) or (_slug(b)[:4] if b else "ITEM")
    if n.startswith("DRIVER"):
        target = n.split("—", 1)[1] if "—" in n else re.sub(r"^DRIVER\s*", "", n)
        body = "DRV-" + _slug(target).replace("W-M", "WM")
    else:
        words = []
        for w in n.replace("—", " ").split():
            if re.fullmatch(r"\d{4}K", w):
                w = w[:2] + "K"  # 3000K -> 30K
            elif w in FINISH_CODE:
                w = FINISH_CODE[w]
            elif re.fullmatch(r"\d+W/M", w):
                w = w.replace("W/M", "WM")
            words.append(w)
        body = _slug(" ".join(words))
    return (prefix + "-" + body)[:64].rstrip("-")


def rename_all(db, models, log=None):
    """Apply the pattern to every product. Returns [(old sku, old name, new sku, new name)]."""
    products = db.query(models.Product).order_by(models.Product.id).all()
    taken = {p.sku for p in products}
    changes = []
    for p in products:
        name = standard_name(p.name, p.brand, p.category)
        sku = standard_sku(p.name, p.brand, p.category)
        if sku != p.sku:
            base, i = sku, 2
            while sku in taken:
                sku = f"{base[:60]}-{i}"
                i += 1
            taken.discard(p.sku)
            taken.add(sku)
        if (name, sku) != (p.name, p.sku):
            changes.append((p.sku, p.name, sku, name))
            p.name, p.sku = name, sku
    return changes
