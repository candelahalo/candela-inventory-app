# Candela App — Project Handoff

Paste this whole file into a new chat to bring Claude up to speed on the project.

---

## What this is

An inventory, stock, quotation and project-tracking web app for **Candela
Lighting and Automation LLC** (Dubai, UAE) — a light supply and home
automation contracting company.

- **Live at:** https://app.candelauae.com
- **Repo:** https://github.com/candelahalo/candela-inventory-app
- **Marketing site:** www.candelauae.com (Webflow — separate, don't touch)

## Infrastructure

| Thing | Detail |
|---|---|
| Server | BigRock VPS, Ubuntu 22.04, 1 vCPU / 2GB RAM / 50GB NVMe |
| IP | 66.116.253.249 |
| SSH | `ssh root@66.116.253.249` (root only — no separate user) |
| App path | `/opt/candela-inventory-app` |
| Service | `systemctl {start,stop,restart,status} candela-app` |
| Web server | nginx reverse proxy → uvicorn on 127.0.0.1:8000 |
| SSL | Let's Encrypt via certbot (auto-renews) |
| DNS | Domain at **GoDaddy**; `app` A-record → the VPS IP |
| Database | PostgreSQL, db `candela_app`, user `candela_user` |

## Stack

FastAPI + SQLAlchemy + PostgreSQL + Alembic. Server-rendered Jinja2 templates
with vanilla JS (no build step, no npm). WeasyPrint for PDF, openpyxl for Excel,
Pillow + numpy for image processing.

## Modules

- **Products** — catalog with SKU, prices, reorder level, spec summary, photo
- **Stock** — warehouses, movement ledger (in/out/adjustment), computed on-hand
  levels, low-stock alerts. Movements can be tied to a project.
- **Customers** — clients
- **Quotations** — line items with type codes and spec descriptions, versioning,
  PDF + Excel export
- **Projects** — 8-stage pipeline: Enquiry → Quoted → Approved → Ordered →
  Delivered → Installed → Commissioned → Closed, with full status timeline and a
  Kanban board on the dashboard
- **Datasheets** — manufacturer PDF spec sheets, filterable, preview + download
- **Activity** — audit trail of every create/update/delete

## Important conventions / decisions already made

- **Stock levels are computed** from the movement ledger, never stored as a
  mutable counter — so everything is auditable.
- **Product photos are normalized on upload**: auto-cropped to the product
  content, then centered on a uniform 800×800 white square, so mismatched
  supplier photos look consistent. EXIF rotation is handled.
- **Quotation PDF** is the "premium" document: cover page, itemized schedule,
  Terms & Conditions. Descriptions left-aligned, figures right-aligned, totals
  box on the right. **Don't center the item table** — it was tried and looked
  unprofessional.
- **Quotation Excel** mirrors the PDF as 3 sheets (Cover / Itemized Schedule /
  Terms & Conditions) but stays **editable with live formulas** (line totals,
  subtotal, VAT, grand total). Fitted to A4 printable width at 100% scale.
- **Transportation charges**: defaults to `500`, stored as text so it can hold
  either a figure or words like "Included". Text values display but are excluded
  from totals (and from the Excel SUM formula).
- **Prepared by** defaults to "Johns James" / "Division Head - Projects".
- **Activity log user** is hardcoded to `admin` for now — a real login system
  with per-user tracking is planned but not built.
- **CSS/JS have `?v=N` cache-busting** in `base.html`. **Bump N on every
  styling change**, otherwise browsers serve stale files and it looks like
  nothing changed.
- **IBM Plex fonts must be installed on the server** (`fonts-ibm-plex`) or both
  the PDF and Excel silently fall back to a generic sans-serif.

## Deploy (no schema change)

```bash
cd /opt/candela-inventory-app && git fetch origin && git reset --hard origin/main && systemctl restart candela-app
```

## Deploy (WITH schema change)

Alembic migration files are **not committed** (only `alembic/versions/.gitkeep`
is), so the usual approach has been to rebuild the database. This wipes data —
fine so far because it's still test data, but **once real data is in, switch to
proper incremental migrations instead.**

```bash
cd /opt/candela-inventory-app && git fetch origin && git reset --hard origin/main && \
systemctl stop candela-app && \
sudo -u postgres psql -c "DROP DATABASE candela_app;" && \
sudo -u postgres psql -c "CREATE DATABASE candela_app OWNER candela_user;" && \
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE candela_app TO candela_user;" && \
rm -rf alembic/versions/*.py && \
alembic revision --autogenerate -m "describe change" && \
alembic upgrade head && \
python3 scripts/seed_data.py && \
python3 scripts/add_placeholder_images.py && \
systemctl start candela-app
```

## Known gotchas hit before

- `alembic upgrade head` failing with "Can't locate revision" → stale
  `alembic_version` table pointing at a deleted migration file. Drop and
  recreate the database.
- Git "divergent branches" on the VPS → use `git reset --hard origin/main`,
  never `git pull`.
- Empty directories aren't tracked by git — that's why `alembic/versions/`
  has a `.gitkeep`.
- Pasting terminal *output* back into the terminal causes a wall of
  "command not found" errors. Harmless, just noise.

## Scripts

- `scripts/seed_data.py` — realistic dummy data across all modules
- `scripts/add_placeholder_images.py` — generates on-brand product renders for
  products with no photo (safe to re-run; only fills blanks)
- `scripts/placeholder_images.py` — the render engine for the above

## What's next / not built yet

- Login system with per-user activity tracking (currently hardcoded `admin`)
- Incremental Alembic migrations instead of drop-and-recreate
- Real product photos (currently generated placeholders)
- Zoho Books integration for invoicing was discussed but deliberately left out
  of scope — invoicing is not in this app
