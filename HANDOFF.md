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

**Migrations are committed to the repo.** Never drop the database on deploy —
that destroys real quotations, stock history, and the link between products and
their uploaded photos.

```bash
cd /opt/candela-inventory-app && git fetch origin && git reset --hard origin/main && \
source venv/bin/activate && pip install -r requirements.txt && \
alembic upgrade head && \
systemctl restart candela-app
```

When changing models, generate a migration **locally**, review it, and commit it:

```bash
alembic revision --autogenerate -m "what changed"
# review the generated file in alembic/versions/ before committing
```

**Never delete or regenerate an existing migration file.** Each one records its
`down_revision`, forming a chain. Deleting a file the live database is stamped
at breaks that chain and produces "Can't locate revision identified by ...",
which then has to be repaired by hand. Always add a new migration on top.

To recover from a broken chain (creates only missing tables, keeps data):

```bash
python3 -c "
from app.database import engine
from app import models
models.Base.metadata.create_all(bind=engine)
" && sudo -u postgres psql -d candela_app -c "DELETE FROM alembic_version;" && alembic stamp head
```

## Uploaded files

Product photos and datasheets live in `app/static/uploads/` and are
**gitignored** — deploys must never touch them. They are not in the repo, so
**back them up separately**:

```bash
tar czf ~/candela-uploads-$(date +%F).tar.gz -C /opt/candela-inventory-app app/static/uploads
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
