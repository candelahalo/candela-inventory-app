from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.routers import (products, stock, customers, quotations, projects,
                         datasheets, activity, auth_router, backup,
                         reports_router, ui)

app = FastAPI(title="Candela Inventory, Stock & Project Tracker", version="0.4.0")

# CORS - tighten allow_origins to your actual frontend domain(s) before production use
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.middleware("http")
async def no_cache_html(request, call_next):
    """Stop browsers caching page HTML.

    Static files are versioned with ?v=N, but the pages themselves aren't -
    so a cached page could keep running old inline JavaScript against a
    newer API, which is exactly how the PDF download kept failing after
    the endpoints changed.
    """
    response = await call_next(request)
    if response.headers.get("content-type", "").startswith("text/html"):
        response.headers["Cache-Control"] = "no-store, must-revalidate"
    return response

# JSON API routers
app.include_router(products.router)
app.include_router(stock.router)
app.include_router(customers.router)
app.include_router(quotations.download_router)
app.include_router(quotations.router)
app.include_router(projects.router)
app.include_router(datasheets.public_router)
app.include_router(datasheets.router)
app.include_router(activity.router)
app.include_router(auth_router.router)
app.include_router(backup.router)
app.include_router(reports_router.router)

# Server-rendered UI (dashboard, forms) - mounted last so it doesn't shadow API paths
app.include_router(ui.router)


@app.get("/health")
def health():
    return {"status": "healthy"}
