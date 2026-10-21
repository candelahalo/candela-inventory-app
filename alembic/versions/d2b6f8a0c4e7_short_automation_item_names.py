"""automation division items: short names, their old long text becomes the one-line description

Revision ID: d2b6f8a0c4e7
Revises: c8e2a4f6b0d1
Create Date: 2026-10-21 22:00:00

Data only: products made by "+ Automation divisions" (no brand, old long
name) get the short name, the long text as their one-line description and a
short SKU. Quote lines keep their own text and point at products by id.
"""
import re

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd2b6f8a0c4e7'
down_revision = 'c8e2a4f6b0d1'
branch_labels = None
depends_on = None

# old name -> (new name, one-line description)
RENAME = {
    "AUTOMATION CONTROLLER": ("AUTOMATION CONTROLLER", "Main automation controller for all subsystems"),
    "1 YEAR REMOTE ACCESS SUBSCRIPTION KIT": ("REMOTE ACCESS SUBSCRIPTION 1 YEAR", "1 year remote access subscription kit"),
    "IPAD 10.9\" 10TH GEN, SUPPLIED BY CLIENT": ("IPAD 10.9\" BY CLIENT", "iPad 10.9\" 10th gen, supplied by client"),
    "WALL STATION FOR IPAD 10.9\" 10TH GEN WITH USB-C, BLACK ANODIZED / GOLD ANODIZED / TITANIUM ANODIZED": ("IPAD WALL STATION", "Wall station for iPad 10.9\" 10th gen with USB-C, black anodized / gold anodized / titanium anodized"),
    "USB-C CHARGER & USB-C TO USB-C CABLE": ("USB-C CHARGER AND CABLE", "USB-C charger & USB-C to USB-C cable"),
    "CAT6 CABLING INCLUDING TERMINATION": ("CAT6 CABLING", "Cat6 cabling including termination"),
    "HOME WORKS QS 2-LINK CONTROL PROCESSOR": ("CONTROL PROCESSOR", "Home Works QS 2-link control processor"),
    "2 CHANNEL DALI GATEWAY": ("DALI GATEWAY 2 CHANNEL", "2 channel DALI gateway"),
    "4 CHANNEL ON/OFF CONTROL MODULE FOR SWITCHING LIGHT CIRCUITS": ("SWITCHING MODULE 4 CHANNEL", "4 channel on/off control module for switching light circuits"),
    "RELAY CONTROLLER FOR GARAGE DOOR / POOL PUMPS AND CUSTOM MOTION SENSORS": ("RELAY CONTROLLER", "Relay controller for garage door / pool pumps and custom motion sensors"),
    "SINGLE COLUMN PALLADIOM 4 BUTTON KEYPAD, METAL WITH PREDEFINED ENGRAVING": ("KEYPAD 4 BUTTON SINGLE COLUMN", "Single column Palladiom 4 button keypad, metal with predefined engraving"),
    "DUAL COLUMN PALLADIOM 8 BUTTON KEYPAD, METAL WITH PREDEFINED ENGRAVING": ("KEYPAD 8 BUTTON DUAL COLUMN", "Dual column Palladiom 8 button keypad, metal with predefined engraving"),
    "PALLADIOM THERMOSTAT, METAL WITH PREDEFINED ENGRAVING": ("THERMOSTAT", "Palladiom thermostat, metal with predefined engraving"),
    "VRF HVAC INTEGRATION GATEWAY": ("VRF HVAC GATEWAY", "VRF HVAC integration gateway"),
    "TRANSFORMERS, RELAYS & INSTALLATION ACCESSORIES FOR HVAC INTERFACING": ("HVAC INTERFACE ACCESSORIES", "Transformers, relays & installation accessories for HVAC interfacing"),
    "PIR/US WIRELESS PLASTERED-IN CEILING MOUNT MOTION SENSOR": ("MOTION SENSOR CEILING", "Wireless plastered-in ceiling mount motion sensor (PIR/US)"),
    "HWQS LINK POWER SUPPLY": ("LINK POWER SUPPLY", "HWQS link power supply"),
    "LIGHTING CONTROL PANEL & INSTALLATION ACCESSORIES": ("LIGHTING CONTROL PANEL", "Lighting control panel & installation accessories"),
    "BUS CABLES FOR COMMUNICATION, INCLUDING CURTAIN CONTROL CABLING": ("BUS CABLES", "Bus cables for communication, including curtain control cabling"),
    "8-INCH 2-WAY IN-CEILING SPEAKER": ("IN-CEILING SPEAKER 8\"", "8-inch 2-way in-ceiling speaker"),
    "OUTDOOR 4.1 (4 SATELLITES AND 1 SUBWOOFER) IN-PLANTER SPEAKERS": ("OUTDOOR SPEAKER SET 4.1", "Outdoor 4.1 (4 satellites and 1 subwoofer) in-planter speakers"),
    "NETWORK AUDIO STREAMER": ("NETWORK AUDIO STREAMER", "Network audio streamer"),
    "12 CHANNEL AUDIO FREQUENCY AMPLIFIER": ("AMPLIFIER 12 CHANNEL", "12 channel audio frequency amplifier"),
    "SPEAKER CABLING INCLUDING TERMINATION - INDOOR": ("SPEAKER CABLING INDOOR", "Speaker cabling including termination - indoor"),
    "SPEAKER CABLING INCLUDING TERMINATION - OUTDOOR": ("SPEAKER CABLING OUTDOOR", "Speaker cabling including termination - outdoor"),
    "CAT6 PATCH CORDS": ("CAT6 PATCH CORDS", "Cat6 patch cords"),
    "4MP VARIFOCAL FIXED BULLET CAMERA WITH NIGHT COLOUR": ("BULLET CAMERA 4MP", "4MP varifocal fixed bullet camera with night colour"),
    "16 CHANNEL NETWORK VIDEO RECORDER": ("NVR 16 CHANNEL", "16 channel network video recorder"),
    "24 PORT POE NETWORK SWITCH": ("POE SWITCH 24 PORT", "24 port PoE network switch"),
    "8 TB HDD": ("HARD DISK 8TB", "8 TB HDD"),
    "CCTV MONITOR / LAPTOP, SUPPLIED BY CLIENT": ("CCTV MONITOR BY CLIENT", "CCTV monitor / laptop, supplied by client"),
    "COMPACT WI-FI 7 ACCESS POINT - INDOOR": ("WI-FI 7 ACCESS POINT INDOOR", "Compact Wi-Fi 7 access point - indoor"),
    "WI-FI 6 ACCESS POINT - INDOOR / OUTDOOR": ("WI-FI 6 ACCESS POINT OUTDOOR", "Wi-Fi 6 access point - indoor / outdoor"),
    "ENTERPRISE GRADE RACK MOUNT ROUTER / CLOUD GATEWAY": ("ROUTER / CLOUD GATEWAY", "Enterprise grade rack mount router / cloud gateway"),
    "48 PORT POE NETWORK SWITCH, LAYER 3": ("POE SWITCH 48 PORT L3", "48 port PoE network switch, layer 3"),
    "42U IT RACK, SHELVES, TRAY, PDU & INSTALLATION ACCESSORIES": ("IT RACK 42U", "42U IT rack, shelves, tray, PDU & installation accessories"),
    "CAT6A CABLING INCLUDING TERMINATION": ("CAT6A CABLING", "Cat6a cabling including termination"),
    "DB TO DB, DB TO RACK COMMUNICATION CAT6A UPLINK CABLES, PATCH CORDS AND PATCH PANELS FOR RACK": ("UPLINK CABLING AND PATCH PANELS", "DB to DB, DB to rack communication Cat6a uplink cables, patch cords and patch panels for rack"),
    "IP VIDEO DOOR STATION, KEYPAD & RFID ACCESS, STAINLESS STEEL WITH FLUSH MOUNT KIT": ("DOOR STATION", "IP video door station, keypad & RFID access, stainless steel with flush mount kit"),
    "VIDEO ANSWERING STATION": ("ANSWERING STATION", "Video answering station"),
    "EM LOCK AND ACCESSORIES, SUPPLIED BY DOOR CONTRACTOR": ("EM LOCK BY DOOR CONTRACTOR", "EM lock and accessories, supplied by door contractor"),
    "RFID CARDS OR KEY FOBS, 10 PCS": ("RFID CARDS / FOBS 10 PCS", "RFID cards or key fobs, 10 pcs"),
    "PUSH BUTTON / EXIT BUTTON": ("EXIT BUTTON", "Push button / exit button"),
    "ELV POWER CABLES": ("ELV POWER CABLES", "ELV power cables"),
}


def _slug(s):
    return re.sub(r"[^A-Z0-9]+", "-", (s or "").upper()).strip("-")


def _sku(name):
    words = [w for w in (_slug(x) for x in name.upper().split()) if w]
    return "-".join(["AUTO"] + words[:4])[:48].rstrip("-")


def upgrade():
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, sku, name, brand FROM products")).fetchall()
    taken = {r[1] for r in rows}
    names = {(r[2] or "").upper() for r in rows}
    for pid, sku, name, brand in sorted(rows, key=lambda r: r[0]):
        new = RENAME.get((name or "").upper())
        if not new or (brand or "").strip():
            continue
        new_name, desc = new
        if new_name.upper() in names and new_name.upper() != (name or "").upper():
            continue  # a product with the short name is already there
        base = _sku(new_name)
        s, i = base, 2
        while s in taken and s != sku:
            s = f"{base[:44]}-{i}"
            i += 1
        conn.execute(sa.text("UPDATE products SET name = :n, spec_summary = :d, sku = :s WHERE id = :i"),
                     {"n": new_name, "d": desc, "s": s, "i": pid})
        taken.discard(sku)
        taken.add(s)
        names.add(new_name.upper())


def downgrade():
    pass
