from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app import models

router = APIRouter(tags=["UI"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/")
def ui_dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request, "active": "dashboard"})


@router.get("/products")
def ui_products(request: Request):
    return templates.TemplateResponse("products.html", {"request": request, "active": "products"})


@router.get("/products/view/{product_id}")
def ui_product_detail(product_id: int, request: Request, db: Session = Depends(get_db)):
    product = db.query(models.Product).get(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return templates.TemplateResponse(
        "product_detail.html",
        {"request": request, "active": "products", "product_id": product_id},
    )


@router.get("/stock")
def ui_stock(request: Request):
    return templates.TemplateResponse("stock.html", {"request": request, "active": "stock"})


@router.get("/customers")
def ui_customers(request: Request):
    return templates.TemplateResponse("customers.html", {"request": request, "active": "customers"})


@router.get("/datasheets")
def ui_datasheets(request: Request):
    return templates.TemplateResponse("datasheets.html", {"request": request, "active": "datasheets"})


@router.get("/activity")
def ui_activity(request: Request):
    return templates.TemplateResponse("activity.html", {"request": request, "active": "activity"})


@router.get("/quotations")
def ui_quotations(request: Request):
    return templates.TemplateResponse("quotations.html", {"request": request, "active": "quotations"})


@router.get("/projects")
def ui_projects(request: Request):
    return templates.TemplateResponse("projects.html", {"request": request, "active": "projects"})


@router.get("/projects/view/{project_id}")
def ui_project_detail(project_id: int, request: Request, db: Session = Depends(get_db)):
    project = db.query(models.Project).get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return templates.TemplateResponse(
        "project_detail.html",
        {"request": request, "active": "projects", "project_id": project_id},
    )
