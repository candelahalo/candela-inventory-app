# Candela Inventory, Stock & Project Tracker

FastAPI + PostgreSQL backend for Candela — a light supply and home automation
contracting company. Scoped to four core areas: Inventory, Stock Management,
Quotation Preparation, and Live Project Status tracking.

## Modules

- **Products** — catalog of light fittings / home automation gear (SKU, cost/selling price, reorder level)
- **Stock** — warehouses, stock movements (in/out/adjustment), computed on-hand levels,
  low-stock alerts. Stock-out can be tied to a specific project (e.g. "installed at site").
- **Customers** — client records for quotations and projects
- **Quotations** — line items, versioned revisions, can be linked to a project
- **Projects** — the live status pipeline for supply + installation jobs:

  ```
  Enquiry → Quoted → Approved → Ordered → Delivered → Installed → Commissioned → Closed
  ```

  Every status change is recorded in a timeline (`status_history`), so a project's
  full progress is auditable. A `board/summary` endpoint gives a Kanban-style
  count of active jobs per stage.

## Local setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then edit DATABASE_URL
mkdir -p alembic/versions
alembic revision --autogenerate -m "initial schema"
alembic upgrade head
uvicorn main:app --reload
```

Visit `http://localhost:8000/docs` for interactive Swagger docs.

## Key endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/products/` | Create a product |
| GET | `/stock/levels` | Live stock on hand per product/warehouse |
| GET | `/stock/low-stock` | Products below reorder level |
| POST | `/stock/movements` | Record stock in/out/adjustment (optionally tied to a project) |
| POST | `/quotations/` | Create a quotation (optionally linked to a project) |
| POST | `/quotations/{id}/revise` | Create a new versioned revision |
| POST | `/projects/` | Create a project (starts at "Enquiry") |
| POST | `/projects/{id}/status` | Advance/change a project's live status (logged to timeline) |
| GET | `/projects/{id}/timeline` | Full status history for a project |
| GET | `/projects/board/summary` | Kanban-style counts of projects per stage |

## Deployment

Deployed on a BigRock VPS behind nginx + Let's Encrypt SSL, running as a
systemd service (`candela-app.service`), live at `app.candelauae.com`.
DNS (A record) is managed in GoDaddy, pointing `app` to the VPS IP.

## Notes

- Stock levels are **computed** from the movement ledger, not a mutable counter — auditable by design.
- A project can have multiple quotation revisions; the accepted one typically drives the "Approved" status.
- Invoicing/accounting deliberately out of scope for now — Zoho Books can remain the system of record for that.
