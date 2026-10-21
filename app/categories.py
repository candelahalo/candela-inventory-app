"""Product categories: one list for products, stock and datasheets (keep in
step with PRODUCT_CATEGORIES in app/static/app.js)."""
import re

PRODUCT_CATEGORIES = [
    "Spotlight", "Downlight", "230V Track Light", "48V Track Light", "Surface Mounted",
    "Custom Light", "Semi Recessed Light", "Strip Light", "Neon Light", "Drivers", "Accessories",
    "Track Accessories", "BOH",
    # Automation
    "Lighting Control", "Keypads & Switches", "Curtains & Blinds", "Audio / Video / Security", "AC Controls",
    "Sensors", "Intercom", "Automation Accessories",
]
AUTOMATION_CATEGORIES = ["Lighting Control", "Keypads & Switches", "Curtains & Blinds", "Audio / Video / Security",
                         "AC Controls", "Sensors", "Intercom", "Automation Accessories"]

# Earlier category / type names and where they belong now
_OLD_TYPE = {
    "spotlight": "Spotlight", "downlight": "Downlight", "track light": "230V Track Light",
    "low voltage track": "48V Track Light", "strip light": "Strip Light", "neon": "Neon Light",
    "accessories": "Accessories",
}
_OLD_CATEGORY = {
    "semi recessed": "Semi Recessed Light", "low voltage track": "48V Track Light",
    "led flex": "Strip Light", "surface mounted": "Surface Mounted", "accessories": "Accessories",
}

_DRIVER = r"\bdriver|power supply|\bpsu\b|transformer"
_ACCESSORY = r"connector|channel|end ?cap|\bkit\b|feeder|bracket|accessor"


def classify(text):
    """Best-guess category from a product's name / spec, or None."""
    t = (text or "").lower()
    if re.search(r"installation|commissioning|testing|programming|labou?r|site coordination", t):
        return None  # a service line, not a product category
    if re.search(r"intercom|door ?phone|door ?station|video entry|villa station", t):
        return "Intercom"
    if re.search(r"thermostat|\bhvac\b|\bfcu\b|fan coil|\bvrf\b|\bvrv\b|a/?c (control|gateway|interface|integration)"
                 r"|for ac\b|air[- ]?condition|coolmaster|temperature control", t):
        return "AC Controls"
    if re.search(r"keypad|touch ?screen|touch ?panel|push ?button|wall switch|scene switch|\b\d+\s*buttons?\b", t):
        return "Keypads & Switches"
    if re.search(r"\bcables?\b", t):
        # bus / data cable is for automation; anything else stays with the lighting accessories
        return "Automation Accessories" if re.search(r"knx|\beib\b|cat ?6|cat ?5|\butp\b|\bbus\b|dali|network|ethernet", t) else "Accessories"
    if re.search(r"enclosure|db box|distribution box|din rail|patch panel", t):
        return "Automation Accessories"
    if re.search(r"(motion|presence|occupancy|daylight|lux|pir|leak|smoke|temperature|humidity|door|window)\s*(/\s*\w+\s*)?sensor"
                 r"|\bsensors?\b|presence detector|motion detector", t) \
            and not re.search(r"\bdriver\b|luminaire|spotlight|downlight", t):
        return "Sensors"
    if re.search(r"curtain|\bblinds?\b|roller shade|shade motor|tubular motor", t):
        return "Curtains & Blinds"
    if re.search(r"speaker|amplifier|cctv|camera|access control", t):
        return "Audio / Video / Security"
    if re.search(r"\bknx\b|actuator|dimmer module|relay module|dali (gateway|controller|master)|lighting control", t):
        return "Lighting Control"
    if re.search(_DRIVER, t):
        return "Drivers"
    if re.search(_ACCESSORY, t):
        return "Track Accessories" if "track" in t else "Accessories"
    if re.search(r"back[ -]of[ -]house|\bboh\b", t):
        return "BOH"
    if "neon" in t:
        return "Neon Light"
    if re.search(r"strip|led flex|\btape\b", t):
        return "Strip Light"
    if re.search(r"48 ?v|low voltage track|magnetic", t):
        return "48V Track Light"
    if "track" in t:
        return "230V Track Light"
    if re.search(r"semi[ -]?recessed", t):
        return "Semi Recessed Light"
    if re.search(r"linear|profile|w/m\b", t):
        return "Custom Light"
    if re.search(r"downlight|panel", t):
        return "Downlight"
    if re.search(r"spot|adjustable", t):
        return "Spotlight"
    if "surface" in t:
        return "Surface Mounted"
    return None


def from_old(category, product_type, text=""):
    """New category for a product saved with the earlier category / type, or
    None when there's no good match (it then shows under "Other")."""
    t = (text or "").lower()
    if re.search(_DRIVER, t):
        return "Drivers"
    if re.search(_ACCESSORY, t):
        return "Accessories"
    return (_OLD_TYPE.get((product_type or "").strip().lower())
            or (category if category in PRODUCT_CATEGORIES else None)
            or _OLD_CATEGORY.get((category or "").strip().lower())
            or classify(text))
