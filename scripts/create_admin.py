"""
Creates the first admin login so someone can sign in.

Run once after adding authentication. Safe to re-run: if the username
already exists it just reports that and changes nothing.

Usage:
    python3 scripts/create_admin.py                 # username admin, generated password
    python3 scripts/create_admin.py praveen mypass  # explicit username and password
"""
import os
import secrets
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import SessionLocal
from app import models, auth

username = sys.argv[1] if len(sys.argv) > 1 else "admin"
password = sys.argv[2] if len(sys.argv) > 2 else secrets.token_urlsafe(9)

db = SessionLocal()

existing = db.query(models.User).filter(models.User.username == username).first()
if existing:
    print(f"A login for '{username}' already exists - nothing changed.")
    print("To reset its password, sign in as another admin and use Settings,")
    print("or delete the row and re-run this script.")
else:
    db.add(models.User(
        username=username,
        hashed_password=auth.hash_password(password),
        full_name=username.title(),
        role="admin",
    ))
    db.commit()
    print("Admin login created.\n")
    print(f"  Username: {username}")
    print(f"  Password: {password}\n")
    print("Sign in at /login and change this password from the Settings page.")

db.close()
