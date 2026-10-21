"""Which company a quotation is issued from. Candelaria Light Fittings
Trading LLC for everyone, except customers set to quote as Candela Lighting
and Automation LLC (e.g. Infinia) on their customer page."""

ENTITIES = {
    "candelaria": {"name": "Candelaria Light Fittings Trading LLC",
                   "logo": "app/static/candelaria-logo-doc.png"},
    "candela": {"name": "Candela Lighting and Automation LLC",
                "logo": "app/static/candela-logo-doc.png"},
}
DEFAULT = "candelaria"


def for_quotation(quotation):
    """{"key", "name", "logo"} for a quotation, from its customer."""
    key = getattr(getattr(quotation, "customer", None), "quote_entity", None) or DEFAULT
    if key not in ENTITIES:
        key = DEFAULT
    return {"key": key, **ENTITIES[key]}
