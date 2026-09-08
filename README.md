# Candela Inventory, Stock, Quotation & Invoicing System

FastAPI + PostgreSQL backend for Candela's inventory management, stock tracking,
quotations, invoicing, and reporting. Designed to be deployed at `app.candelauae.com`.

## Modules

- **Products** — catalog of light fittings (SKU, cost/selling price, reorder level)
- **Stock** — warehouses, stock movements (in/out/adjustment), computed on-hand levels, low-stock alerts
- **Customers** — client records for quotations/invoices
- **Quotations** — line items, versioning/revisions, status tracking
- **Invoices** — standalone or converted from an accepted quotation, payment tracking
- **Reports** — stock valuation, sales summary, top-selling products

## Local setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then edit DATABASE_URL if needed
```

Create the Postgres database (see deployment steps), then run migrations:

```bash
alembic revision --autogenerate -m "initial schema"
alembic upgrade head
```

Run the dev server:

```bash
uvicorn main:app --reload
```

Visit `http://localhost:8000/docs` for interactive API docs (Swagger UI) —
every endpoint below is testable there directly.

## Key endpoints (see /docs for full list)

| Method | Path | Purpose |
|---|---|---|
| POST | `/products/` | Create a product |
| GET | `/stock/levels` | Live stock on hand per product/warehouse |
| GET | `/stock/low-stock` | Products below reorder level |
| POST | `/stock/movements` | Record stock in/out/adjustment |
| POST | `/quotations/` | Create a quotation |
| POST | `/quotations/{id}/revise` | Create a new versioned revision |
| POST | `/invoices/from-quotation/{id}` | Convert an accepted quotation to an invoice |
| POST | `/invoices/{id}/record-payment` | Log a payment against an invoice |
| GET | `/reports/stock-valuation` | Total stock value at cost |
| GET | `/reports/sales-summary` | Invoiced / collected / outstanding totals |
| GET | `/reports/top-products` | Best sellers by quantity |

## Deployment

Deployed on a BigRock VPS behind nginx + Let's Encrypt SSL, running as a
systemd service, reachable at `app.candelauae.com`. DNS (A record) is
managed in GoDaddy, pointing `app` to the VPS IP.

## Notes

- Stock levels are **computed** from the movement ledger (not a mutable counter),
  so every change is auditable.
- Quotation revisions create a new row rather than overwriting — full history preserved.
- Consider syncing finalized invoices to Zoho Books via its API rather than duplicating
  accounting/tax logic here, if Zoho Books remains the system of record for accounting.
