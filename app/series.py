"""Series products: several sizes picked as one in a quote, with options.

CHERUB comes in S, M, L and XL. Each size is its own product (own price,
stock and datasheet) with series = "CHERUB" and variant = "S". On the quote
line the series shows once; you pick the size, then each option (watt,
beam, CCT, dimming, colour), which go in the line's description. The
ordering code is the size's own (CHB-S); a pattern may also use the chosen
option codes, e.g. "CHB-S-{power}":

    {"code": "CHB-S",
     "groups": [{"key": "power", "label": "Power",
                 "choices": [{"label": "12W", "code": "12"}, ...]},
                ...]}

Prices are the size's own; a dearer option (e.g. DALI) is priced by hand on
the quote line.
"""
import re

from fastapi import HTTPException


def clean(options):
    """Checked and tidied options, or None when there are none."""
    if not options:
        return None
    if not isinstance(options, dict):
        raise HTTPException(status_code=400, detail="Options are not in the right form")
    groups, keys = [], set()
    for g in options.get("groups") or []:
        label = str(g.get("label") or "").strip()[:40]
        key = re.sub(r"[^a-z0-9]+", "", str(g.get("key") or label).lower())[:20]
        choices = []
        for c in g.get("choices") or []:
            cl = str(c.get("label") or "").strip()[:60]
            if not cl:
                continue
            choices.append({"label": cl, "code": str(c.get("code") or "").strip()[:20]})
        if not label or not choices:
            continue
        if not key or key in keys:
            raise HTTPException(status_code=400, detail=f"Two options are both called '{label}'")
        keys.add(key)
        groups.append({"key": key, "label": label, "choices": choices[:30]})
    if not groups:
        return None
    return {"code": str(options.get("code") or "").strip()[:120], "groups": groups[:10]}


def build_code(options, chosen):
    """Ordering code from the pattern and the chosen option codes."""
    pattern = (options or {}).get("code") or ""
    chosen = chosen or {}
    return re.sub(r"\{(\w+)\}", lambda m: str(chosen.get(m.group(1), "?")), pattern)
