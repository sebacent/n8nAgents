from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.menu import Category, MenuItem
from app.models.customer import Customer
from app.services import order_service, menu_service
from app.services.ticket_service import generate_ticket_data

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory="templates")

VALID_STATUSES = ["pending", "confirmed", "preparing", "ready", "delivered", "cancelled"]


@router.get("/", response_class=RedirectResponse)
def admin_root():
    return RedirectResponse(url="/admin/dashboard")


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    stats = order_service.get_daily_stats(db)
    recent_orders = order_service.get_orders(db, limit=10)
    return templates.TemplateResponse(
        "admin/dashboard.html",
        {"request": request, "stats": stats, "recent_orders": recent_orders},
    )


@router.get("/orders", response_class=HTMLResponse)
def orders_page(request: Request, status: str = None, db: Session = Depends(get_db)):
    orders = order_service.get_orders(db, status=status, limit=100)
    return templates.TemplateResponse(
        "admin/orders.html",
        {
            "request": request,
            "orders": orders,
            "current_status": status,
            "valid_statuses": VALID_STATUSES,
        },
    )


@router.get("/orders/{order_id}/ticket", response_class=HTMLResponse)
def order_ticket(request: Request, order_id: int, db: Session = Depends(get_db)):
    order = order_service.get_order(db, order_id)
    if not order:
        return HTMLResponse("<h1>Pedido no encontrado</h1>", status_code=404)
    ticket = generate_ticket_data(order)
    return templates.TemplateResponse(
        "admin/ticket.html",
        {"request": request, "ticket": ticket},
    )


@router.get("/menu", response_class=HTMLResponse)
def menu_page(request: Request, db: Session = Depends(get_db)):
    categories = db.query(Category).order_by(Category.display_order).all()
    items = (
        db.query(MenuItem)
        .join(Category)
        .order_by(Category.display_order, MenuItem.name)
        .all()
    )
    return templates.TemplateResponse(
        "admin/menu.html",
        {"request": request, "categories": categories, "items": items},
    )


@router.post("/menu/categories")
async def create_category(
    request: Request,
    name: str = Form(...),
    emoji: str = Form("🍔"),
    description: str = Form(""),
    db: Session = Depends(get_db),
):
    cat = Category(name=name, emoji=emoji, description=description)
    db.add(cat)
    db.commit()
    return RedirectResponse(url="/admin/menu", status_code=303)


@router.post("/menu/categories/{cat_id}/toggle")
def toggle_category(cat_id: int, db: Session = Depends(get_db)):
    cat = db.query(Category).filter(Category.id == cat_id).first()
    if cat:
        cat.is_active = not cat.is_active
        db.commit()
    return RedirectResponse(url="/admin/menu", status_code=303)


@router.post("/menu/items")
async def create_item(
    request: Request,
    category_id: int = Form(...),
    name: str = Form(...),
    description: str = Form(""),
    price: float = Form(...),
    price_vip: str = Form(""),
    is_special: str = Form(""),
    db: Session = Depends(get_db),
):
    item = MenuItem(
        category_id=category_id,
        name=name,
        description=description or None,
        price=price,
        price_vip=float(price_vip) if price_vip.strip() else None,
        is_special=bool(is_special),
    )
    db.add(item)
    db.commit()
    return RedirectResponse(url="/admin/menu", status_code=303)


@router.post("/menu/items/{item_id}/toggle")
def toggle_item(item_id: int, db: Session = Depends(get_db)):
    item = db.query(MenuItem).filter(MenuItem.id == item_id).first()
    if item:
        item.is_available = not item.is_available
        db.commit()
    return RedirectResponse(url="/admin/menu", status_code=303)


@router.get("/customers", response_class=HTMLResponse)
def customers_page(request: Request, db: Session = Depends(get_db)):
    customers = db.query(Customer).order_by(Customer.created_at.desc()).all()
    return templates.TemplateResponse(
        "admin/customers.html",
        {"request": request, "customers": customers},
    )


@router.post("/customers/{customer_id}/vip")
def toggle_vip(customer_id: int, db: Session = Depends(get_db)):
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if customer:
        customer.is_vip = not customer.is_vip
        db.commit()
    return RedirectResponse(url="/admin/customers", status_code=303)
