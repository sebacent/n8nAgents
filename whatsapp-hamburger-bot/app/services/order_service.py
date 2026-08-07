from datetime import datetime, date
from typing import Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.models.customer import Customer
from app.models.order import Order, OrderItem


VALID_STATUSES = ["pending", "confirmed", "preparing", "ready", "delivered", "cancelled"]


def create_order(
    db: Session,
    customer: Customer,
    cart_data: List[Dict],
    payment_method: str,
    address: str,
) -> Order:
    subtotal = sum(item["unit_price"] * item["quantity"] for item in cart_data)
    discount = 0.0
    total = subtotal - discount

    order = Order(
        customer_id=customer.id,
        status="pending",
        subtotal=subtotal,
        discount=discount,
        total=total,
        payment_method=payment_method,
        delivery_address=address,
    )
    db.add(order)
    db.flush()  # get order.id

    for cart_item in cart_data:
        order_item = OrderItem(
            order_id=order.id,
            menu_item_id=cart_item["item_id"],
            quantity=cart_item["quantity"],
            unit_price=cart_item["unit_price"],
            subtotal=cart_item["unit_price"] * cart_item["quantity"],
        )
        db.add(order_item)

    customer.total_orders = (customer.total_orders or 0) + 1
    if customer.total_orders >= 5:
        customer.is_vip = True

    db.commit()
    db.refresh(order)
    return order


def get_order(db: Session, order_id: int) -> Optional[Order]:
    return (
        db.query(Order)
        .options(joinedload(Order.items).joinedload(OrderItem.menu_item), joinedload(Order.customer))
        .filter(Order.id == order_id)
        .first()
    )


def get_orders(db: Session, status: Optional[str] = None, limit: int = 50) -> List[Order]:
    query = db.query(Order).options(
        joinedload(Order.customer),
        joinedload(Order.items).joinedload(OrderItem.menu_item),
    )
    if status:
        query = query.filter(Order.status == status)
    return query.order_by(Order.created_at.desc()).limit(limit).all()


def update_order_status(db: Session, order_id: int, status: str) -> Optional[Order]:
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        return None
    order.status = status
    order.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(order)
    return order


def add_rating(db: Session, order_id: int, rating: int) -> Optional[Order]:
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        return None
    order.rating = rating
    db.commit()
    db.refresh(order)
    return order


def get_daily_stats(db: Session) -> Dict:
    today = date.today()
    today_start = datetime.combine(today, datetime.min.time())
    today_end = datetime.combine(today, datetime.max.time())

    today_orders = (
        db.query(func.count(Order.id))
        .filter(Order.created_at >= today_start, Order.created_at <= today_end)
        .scalar()
        or 0
    )

    today_revenue = (
        db.query(func.sum(Order.total))
        .filter(
            Order.created_at >= today_start,
            Order.created_at <= today_end,
            Order.status != "cancelled",
        )
        .scalar()
        or 0.0
    )

    total_customers = db.query(func.count(Customer.id)).scalar() or 0
    vip_customers = (
        db.query(func.count(Customer.id)).filter(Customer.is_vip == True).scalar() or 0
    )

    pending_orders = (
        db.query(func.count(Order.id)).filter(Order.status == "pending").scalar() or 0
    )

    return {
        "today_orders": today_orders,
        "today_revenue": round(float(today_revenue), 2),
        "total_customers": total_customers,
        "vip_customers": vip_customers,
        "pending_orders": pending_orders,
    }
