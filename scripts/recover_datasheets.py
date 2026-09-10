"""
Re-registers datasheet PDFs that exist on disk but have no database record.

This happens if the database was rebuilt while the uploaded files survived -
the files are fine, but the rows describing them (title, brand, category) are
gone. This script finds orphaned PDFs and creates a record for each so they
show up in the app again.

Titles are set to "Recovered - <filename>" since the original titles lived
only in the database. Rename them in the app afterwards.

Usage (on the server, inside the venv):
    python3 scripts/recover_datasheets.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import SessionLocal
from app import models

DATASHEET_DIR = Path("app/static/uploads/datasheets")

db = SessionLocal()

if not DATASHEET_DIR.exists():
    print(f"No datasheet directory at {DATASHEET_DIR} - nothing to recover.")
    sys.exit(0)

known_paths = {d.file_path for d in db.query(models.Datasheet).all()}
recovered = 0

for pdf in sorted(DATASHEET_DIR.glob("*.pdf")):
    url_path = f"/static/uploads/datasheets/{pdf.name}"
    if url_path in known_paths:
        continue

    size_mb = pdf.stat().st_size / (1024 * 1024)
    datasheet = models.Datasheet(
        title=f"Recovered - {pdf.stem[:12]}",
        brand=None,
        category=None,
        product_id=None,
        file_path=url_path,
        original_filename=pdf.name,
    )
    db.add(datasheet)
    recovered += 1
    print(f"  re-registered {pdf.name}  ({size_mb:.1f} MB)")

if recovered:
    db.commit()
    print(f"\nDone. Recovered {recovered} datasheet(s).")
    print("Open the Datasheets page to rename them and set brand/category.")
else:
    print("No orphaned datasheets found - everything on disk is already registered.")

db.close()
