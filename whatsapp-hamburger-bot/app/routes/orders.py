from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.services import order_service

router = APIRouter(prefix="/api/orders", tags=["orders"])

VALID_STATUSES = ["pending", "confirmed", "preparing", "ready", "delivered", "cancelled"]


class StatusUpdate(BaseModel):
    status: str


@router.get("/stats/daily")
def daily_stats(db: Session = Depends(get_db)):
    return order_service.get_daily_stats(db)


@router.get("/")
def list_orders(
    status: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    if status and status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
    orders = order_service.get_orders(db, status=status, limit=limit)
    result = []
    for order in orders:
        result.append({
            "id": order.id,
            "customer_name": order.customer.name if order.customer else None,
            "customer_phone": order.customer.phone if order.customer else None,
            "status": order.status,
            "total": order.total,
            "subtotal": order.subtotal,
            "discount": order.discount,
            "payment_method": order.payment_method,
            "delivery_address": order.delivery_address,
            "notes": order.notes,
            "rating": order.rating,
            "items_count": len(order.items),
            "created_at": order.created_at.isoformat() if order.created_at else None,
            "updated_at": order.updated_at.isoformat() if order.updated_at else None,
        })
    return result


@router.get("/{order_id}")
def get_order(order_id: int, db: Session = Depends(get_db)):
    order = order_service.get_order(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return {
        "id": order.id,
        "customer_name": order.customer.name if order.customer else None,
        "customer_phone": order.customer.phone if order.customer else None,
        "status": order.status,
        "total": order.total,
        "subtotal": order.subtotal,
        "discount": order.discount,
        "payment_method": order.payment_method,
        "delivery_address": order.delivery_address,
        "notes": order.notes,
        "rating": order.rating,
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "updated_at": order.updated_at.isoformat() if order.updated_at else None,
        "items": [
            {
                "id": item.id,
                "menu_item_id": item.menu_item_id,
                "name": item.menu_item.name if item.menu_item else None,
                "quantity": item.quantity,
                "unit_price": item.unit_price,
                "subtotal": item.subtotal,
                "notes": item.notes,
            }
            for item in order.items
        ],
    }


@router.patch("/{order_id}/status")
def update_status(
    order_id: int,
    body: StatusUpdate,
    db: Session = Depends(get_db),
):
    if body.status not in VALID_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status '{body.status}'. Must be one of: {VALID_STATUSES}",
        )
    order = order_service.update_order_status(db, order_id, body.status)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return {"id": order.id, "status": order.status}
