from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.routers import products, stock, customers, quotations, projects, ui

app = FastAPI(title="Candela Inventory, Stock & Project Tracker", version="0.3.0")

# CORS - tighten allow_origins to your actual frontend domain(s) before production use
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

# JSON API routers
app.include_router(products.router)
app.include_router(stock.router)
app.include_router(customers.router)
app.include_router(quotations.router)
app.include_router(projects.router)

# Server-rendered UI (dashboard, forms) - mounted last so it doesn't shadow API paths
app.include_router(ui.router)


@app.get("/health")
def health():
    return {"status": "healthy"}
