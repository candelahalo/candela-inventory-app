"""Read room names (and the floor name) from an architect's layout PDF.

Room labels on a plan are the most common size of upper-case text inside the
drawing area; words that sit together (same line, or stacked lines such as
"FAMILY / LIVING") are joined into one label. Everything is then shown to the
user to rename / delete before use.
"""
import io
import re
from collections import Counter

from pdfminer.converter import PDFLayoutAnalyzer
from pdfminer.layout import LTChar
from pdfminer.pdfinterp import PDFPageInterpreter, PDFResourceManager
from pdfminer.pdfpage import PDFPage
from pdfplumber.utils import extract_words

FLOOR_RE = re.compile(
    r"\b(BASEMENT|LOWER GROUND|GROUND|FIRST|SECOND|THIRD|FOURTH|FIFTH|MEZZANINE|ROOF|PENTHOUSE|"
    r"TERRACE)\s+FLOOR\b|\b(ROOF|BASEMENT|MEZZANINE|PENTHOUSE)\b")
FLOOR_ORDER = ["BASEMENT", "LOWER GROUND", "GROUND", "MEZZANINE", "FIRST", "SECOND", "THIRD",
               "FOURTH", "FIFTH", "PENTHOUSE", "ROOF", "TERRACE"]
WORD_RE = re.compile(r"^[A-Z][A-Z'&./()-]*$|^\d{1,2}$")
SKIP_LABELS = {"OPEN ABOVE", "OPEN BELOW", "OPEN TO SKY", "OPEN TO BELOW", "PAVEMENT", "PLANTER",
               "LIFT", "SHAFT", "DUCT", "UP", "DN", "VOID", "NORTH", "ABOVE", "BELOW"}
SKIP_WORDS_ONLY = re.compile(r"^(LS|L|D|S|P|SL)-?\d+$")


def _nice(label):
    out = []
    for w in label.split():
        out.append(w if w.isdigit() else w[0] + w[1:].lower())
    s = " ".join(out).replace(" And ", " and ").replace(" Of ", " of ").replace(" To ", " to ")
    return s.replace("Rm.", "Room").replace(" Rm", " Room")


def _drawing_right(words, width):
    """x where the legend / title block starts (labels to the right are not rooms)."""
    for w in words:
        if w["text"] in ("SYMBOL", "LEGEND") and w["x0"] > width * 0.5:
            return w["x0"] - 5
    return width * 0.78


CODE_RE = re.compile(r"(?:^|[-_ ])(GF|FF|SF|TF|RF|B1|B2|M)(?=[-_ .]|$)")
CODES = {"GF": "Ground Floor", "FF": "First Floor", "SF": "Second Floor", "TF": "Third Floor",
         "RF": "Roof", "B1": "Basement", "B2": "Basement 2", "M": "Mezzanine"}


def floor_name(text, filename=""):
    fn = filename.upper().replace("_", " ")
    for src in (text.upper(), fn):
        m = FLOOR_RE.search(src)
        if m:
            name = (m.group(1) or m.group(2)).strip()
            return name.title() + (" Floor" if m.group(1) else "")
    for src in (" ".join(re.findall(r"\S*-(?:GF|FF|SF|TF|RF|B1|B2)-\S*", text.upper())), fn):
        m = CODE_RE.search(src)
        if m:
            return CODES[m.group(1)]
    return "Floor"


def floor_rank(name):
    u = name.upper()
    for i, k in enumerate(FLOOR_ORDER):
        if u.startswith(k):
            return i
    return len(FLOOR_ORDER)


class _TextOnly(PDFLayoutAnalyzer):
    """Collects characters only: plans hold thousands of lines, skipping them is ~2x faster."""
    def __init__(self, rm):
        super().__init__(rm, laparams=None)
        self.pages = []

    def paint_path(self, *a, **k):
        pass

    def render_image(self, *a, **k):
        pass

    def receive_layout(self, lt):
        h = lt.height
        self.pages.append((lt.width, [
            {"text": o.get_text(), "x0": o.x0 - lt.x0, "x1": o.x1 - lt.x0, "top": h - (o.y1 - lt.y0),
             "bottom": h - (o.y0 - lt.y0), "doctop": h - (o.y1 - lt.y0), "size": o.size, "upright": o.upright}
            for o in lt if isinstance(o, LTChar)]))


def _pages(data, limit=6):
    rm = PDFResourceManager()
    dev = _TextOnly(rm)
    it = PDFPageInterpreter(rm, dev)
    for i, page in enumerate(PDFPage.get_pages(io.BytesIO(data))):
        if i >= limit:
            break
        it.process_page(page)
    for width, chars in dev.pages:
        yield width, extract_words(chars, extra_attrs=["size", "upright"]) if chars else []


def read(data, filename=""):
    """-> {"floor": "Ground Floor", "rooms": ["Family Living", ...]} (one floor per PDF page set)."""
    floors = []
    if True:
        for page_width, words in _pages(data):
            if not words:
                continue
            right = _drawing_right(words, page_width)
            text = " ".join(w["text"] for w in words)
            cand = [w for w in words if w["upright"] and w["x1"] < right and WORD_RE.match(w["text"])
                    and not SKIP_WORDS_ONLY.match(w["text"])]
            sizes = Counter(round(w["size"], 1) for w in cand
                            if len(w["text"]) >= 3 and not w["text"][0].isdigit() and 3.5 <= w["size"] <= 14)
            if not sizes:
                continue
            size = sizes.most_common(1)[0][0]
            ws = [w for w in cand if abs(w["size"] - size) <= 0.15]
            # 1) words on the same line
            ws.sort(key=lambda w: (round(w["top"]), w["x0"]))
            lines = []
            for w in ws:
                for ln in lines:
                    if abs(ln["top"] - w["top"]) < size * 0.5 and 0 <= w["x0"] - ln["x1"] < size * 1.3:
                        ln["text"] += " " + w["text"]; ln["x1"] = w["x1"]; ln["bottom"] = max(ln["bottom"], w["bottom"])
                        break
                else:
                    lines.append({"text": w["text"], "x0": w["x0"], "x1": w["x1"], "top": w["top"], "bottom": w["bottom"]})
            # 2) stacked lines ("FAMILY" over "LIVING")
            lines.sort(key=lambda l: l["top"])
            labels = []
            for ln in lines:
                c = (ln["x0"] + ln["x1"]) / 2
                for lb in labels:
                    lc = (lb["x0"] + lb["x1"]) / 2
                    if 0 <= ln["top"] - lb["bottom"] < size * 0.9 and abs(c - lc) < max(lb["x1"] - lb["x0"], ln["x1"] - ln["x0"]) * 0.6:
                        lb["text"] += " " + ln["text"]; lb["bottom"] = ln["bottom"]
                        lb["x0"] = min(lb["x0"], ln["x0"]); lb["x1"] = max(lb["x1"], ln["x1"])
                        break
                else:
                    labels.append(dict(ln))
            rooms = []
            for lb in sorted(labels, key=lambda l: (round(l["top"] / 20), l["x0"])):
                t = re.sub(r"\s+", " ", lb["text"]).strip()
                if t in SKIP_LABELS or t.isdigit() or len(t) < 3:
                    continue
                rooms.append(_nice(t))
            # number repeated names: Bath 1, Bath 2 ...
            cnt = Counter(rooms); seen = Counter(); out = []
            for r in rooms:
                if cnt[r] > 1:
                    seen[r] += 1; out.append(f"{r} {seen[r]}")
                else:
                    out.append(r)
            floors.append({"floor": floor_name(text, filename), "rooms": out})
    if not floors:
        return {"floor": floor_name("", filename), "rooms": []}
    # a multi-page PDF of one floor: join; otherwise the first page
    first = floors[0]
    for f in floors[1:]:
        if f["floor"] == first["floor"]:
            first["rooms"] += [r for r in f["rooms"] if r not in first["rooms"]]
    return first
