from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import products, stock, customers, quotations, invoices, reports

app = FastAPI(title="Candela Inventory & Quotation System", version="0.1.0")

# CORS - tighten allow_origins to your actual frontend domain(s) before production use
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(products.router)
app.include_router(stock.router)
app.include_router(customers.router)
app.include_router(quotations.router)
app.include_router(invoices.router)
app.include_router(reports.router)


@app.get("/")
def root():
    return {"status": "ok", "service": "candela-inventory-app"}


@app.get("/health")
def health():
    return {"status": "healthy"}
