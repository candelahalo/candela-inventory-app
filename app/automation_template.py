"""Home automation divisions: the standard systems of an automation quote and
their usual items (as in the EMKAAN 5326 villa proposal). Staff tick the
divisions a project takes; each comes in as a section with its items.

Items are products (category given here, no brand - picked per project);
service lines (drawings, installation, commissioning, fees) are typed lines.
"""
S = None  # a service line, not a product

DIVISIONS = [
    ("central", "Centralized Control System", [
        ("Main automation controller for all subsystems", "Lighting Control"),
        ("1 year remote access subscription kit", "Automation Accessories"),
        ("iPad 10.9\" 10th gen, supplied by client", "Audio / Video / Security"),
        ("Wall station for iPad 10.9\" 10th gen with USB-C, black anodized / gold anodized / titanium anodized", "Keypads & Switches"),
        ("USB-C charger & USB-C to USB-C cable", "Automation Accessories"),
        ("Cat6 cabling including termination", "Automation Accessories"),
        ("CAD drawings, installation and commissioning, advanced logic and centralized integration programming between all subsystems", S),
    ]),
    ("lighting", "Lighting, Shades and AC Control System", [
        ("Home Works QS 2-link control processor", "Lighting Control"),
        ("2 channel DALI gateway", "Lighting Control"),
        ("4 channel on/off control module for switching light circuits", "Lighting Control"),
        ("Relay controller for garage door / pool pumps and custom motion sensors", "Lighting Control"),
        ("Single column Palladiom 4 button keypad, metal with predefined engraving", "Keypads & Switches"),
        ("Dual column Palladiom 8 button keypad, metal with predefined engraving", "Keypads & Switches"),
        ("Palladiom thermostat, metal with predefined engraving", "AC Controls"),
        ("VRF HVAC integration gateway", "AC Controls"),
        ("Transformers, relays & installation accessories for HVAC interfacing", "Automation Accessories"),
        ("Wireless plastered-in ceiling mount motion sensor (PIR/US)", "Sensors"),
        ("HWQS link power supply", "Lighting Control"),
        ("Lighting control panel & installation accessories", "Automation Accessories"),
        ("Bus cables for communication, including curtain control cabling", "Automation Accessories"),
        ("Cat6 cabling including termination", "Automation Accessories"),
        ("CAD drawings, installation and commissioning, logic and scene programming, zone-by-zone routing plans, "
         "load calculations, DB circuit labelling and termination, line testing, grounding requirements and final validation", S),
    ]),
    ("music", "Background Music System", [
        ("8-inch 2-way in-ceiling speaker", "Audio / Video / Security"),
        ("Outdoor 4.1 (4 satellites and 1 subwoofer) in-planter speakers", "Audio / Video / Security"),
        ("Network audio streamer", "Audio / Video / Security"),
        ("12 channel audio frequency amplifier", "Audio / Video / Security"),
        ("Speaker cabling including termination - indoor", "Automation Accessories"),
        ("Speaker cabling including termination - outdoor", "Automation Accessories"),
        ("Cat6 patch cords", "Automation Accessories"),
        ("CAD drawings, installation and commissioning, speaker calibration and tuning", S),
    ]),
    ("cctv", "CCTV System", [
        ("4MP varifocal fixed bullet camera with night colour", "CCTV"),
        ("16 channel network video recorder", "CCTV"),
        ("24 port PoE network switch", "CCTV"),
        ("8 TB HDD", "CCTV"),
        ("CCTV monitor / laptop, supplied by client", "CCTV"),
        ("Cat6 patch cords", "Automation Accessories"),
        ("Cat6 cabling including termination", "Automation Accessories"),
        ("CAD drawings, installation and commissioning, camera mounting and alignment, camera configuration and rack dressing", S),
    ]),
    ("wifi", "Wi-Fi & IT Backend", [
        ("Compact Wi-Fi 7 access point - indoor", "Wi-Fi & Network"),
        ("Wi-Fi 6 access point - indoor / outdoor", "Wi-Fi & Network"),
        ("Enterprise grade rack mount router / cloud gateway", "Wi-Fi & Network"),
        ("48 port PoE network switch, layer 3", "Wi-Fi & Network"),
        ("42U IT rack, shelves, tray, PDU & installation accessories", "Automation Accessories"),
        ("Cat6a cabling including termination", "Automation Accessories"),
        ("DB to DB, DB to rack communication Cat6a uplink cables, patch cords and patch panels for rack", "Automation Accessories"),
        ("CAD drawings, installation and commissioning, Wi-Fi heatmaps, network subnet, SSID and threshold configuration, "
         "rack dressing and cable management", S),
    ]),
    ("intercom", "Video Intercom & Access Control", [
        ("IP video door station, keypad & RFID access, stainless steel with flush mount kit", "Intercom"),
        ("Video answering station", "Intercom"),
        ("EM lock and accessories, supplied by door contractor", "Intercom"),
        ("RFID cards or key fobs, 10 pcs", "Intercom"),
        ("Push button / exit button", "Intercom"),
        ("Cat6 cabling including termination", "Automation Accessories"),
        ("ELV power cables", "Automation Accessories"),
        ("CAD drawings, installation and commissioning, integration with mortise locks and configuration", S),
    ]),
    ("fees", "Professional Fees", [
        ("Project management, site mobilization and engineering services", S),
    ]),
]


def listing():
    return [{"key": k, "name": name, "section": name.upper(), "items": len(items)} for k, name, items in DIVISIONS]


# Short product names (the item text above becomes the one-line description)
SHORT = {
    "Main automation controller for all subsystems": "Automation controller",
    "1 year remote access subscription kit": "Remote access subscription 1 year",
    "iPad 10.9\" 10th gen, supplied by client": "iPad 10.9\" by client",
    "Wall station for iPad 10.9\" 10th gen with USB-C, black anodized / gold anodized / titanium anodized": "iPad wall station",
    "USB-C charger & USB-C to USB-C cable": "USB-C charger and cable",
    "Cat6 cabling including termination": "Cat6 cabling",
    "Home Works QS 2-link control processor": "Control processor",
    "2 channel DALI gateway": "DALI gateway 2 channel",
    "4 channel on/off control module for switching light circuits": "Switching module 4 channel",
    "Relay controller for garage door / pool pumps and custom motion sensors": "Relay controller",
    "Single column Palladiom 4 button keypad, metal with predefined engraving": "Keypad 4 button single column",
    "Dual column Palladiom 8 button keypad, metal with predefined engraving": "Keypad 8 button dual column",
    "Palladiom thermostat, metal with predefined engraving": "Thermostat",
    "VRF HVAC integration gateway": "VRF HVAC gateway",
    "Transformers, relays & installation accessories for HVAC interfacing": "HVAC interface accessories",
    "Wireless plastered-in ceiling mount motion sensor (PIR/US)": "Motion sensor ceiling",
    "HWQS link power supply": "Link power supply",
    "Lighting control panel & installation accessories": "Lighting control panel",
    "Bus cables for communication, including curtain control cabling": "Bus cables",
    "8-inch 2-way in-ceiling speaker": "In-ceiling speaker 8\"",
    "Outdoor 4.1 (4 satellites and 1 subwoofer) in-planter speakers": "Outdoor speaker set 4.1",
    "Network audio streamer": "Network audio streamer",
    "12 channel audio frequency amplifier": "Amplifier 12 channel",
    "Speaker cabling including termination - indoor": "Speaker cabling indoor",
    "Speaker cabling including termination - outdoor": "Speaker cabling outdoor",
    "Cat6 patch cords": "Cat6 patch cords",
    "4MP varifocal fixed bullet camera with night colour": "Bullet camera 4MP",
    "16 channel network video recorder": "NVR 16 channel",
    "24 port PoE network switch": "PoE switch 24 port",
    "8 TB HDD": "Hard disk 8TB",
    "CCTV monitor / laptop, supplied by client": "CCTV monitor by client",
    "Compact Wi-Fi 7 access point - indoor": "Wi-Fi 7 access point indoor",
    "Wi-Fi 6 access point - indoor / outdoor": "Wi-Fi 6 access point outdoor",
    "Enterprise grade rack mount router / cloud gateway": "Router / cloud gateway",
    "48 port PoE network switch, layer 3": "PoE switch 48 port L3",
    "42U IT rack, shelves, tray, PDU & installation accessories": "IT rack 42U",
    "Cat6a cabling including termination": "Cat6a cabling",
    "DB to DB, DB to rack communication Cat6a uplink cables, patch cords and patch panels for rack": "Uplink cabling and patch panels",
    "IP video door station, keypad & RFID access, stainless steel with flush mount kit": "Door station",
    "Video answering station": "Answering station",
    "EM lock and accessories, supplied by door contractor": "EM lock by door contractor",
    "RFID cards or key fobs, 10 pcs": "RFID cards / fobs 10 pcs",
    "Push button / exit button": "Exit button",
    "ELV power cables": "ELV power cables",
}
