"""
Assigns a generated placeholder photo to every product that doesn't already
have an image. Safe to run any time - only fills in blanks, never overwrites a
product that already has an image_path set.

NOTE: this can only see what's in the database. If the database is rebuilt,
products lose their image_path and this script will assign fresh placeholders
even where a real photo was previously uploaded (the file itself survives in
app/static/uploads/products/, it's just no longer referenced). That's why
deploys must use `alembic upgrade head` rather than dropping the database.

Usage (on the server, inside the venv):
    python3 scripts/add_placeholder_images.py
"""
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import SessionLocal
from app import models
from scripts.placeholder_images import generate_placeholder

db = SessionLocal()
products = db.query(models.Product).filter(
    (models.Product.image_path.is_(None)) | (models.Product.image_path == "")
).all()

if not products:
    print("Every product already has an image. Nothing to do.")
else:
    upload_dir = Path("app/static/uploads/products")
    for p in products:
        filename = f"{uuid.uuid4().hex}.jpg"
        dest = upload_dir / filename
        generate_placeholder(p.name, p.category or "", p.sku, dest)
        p.image_path = f"/static/uploads/products/{filename}"
        print(f"  {p.sku} -> {p.image_path}")

    db.commit()
    print(f"\nDone. Added placeholder images to {len(products)} product(s).")

db.close()
