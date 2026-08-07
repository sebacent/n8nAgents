from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.menu import Category, MenuItem, Promotion


def get_active_categories(db: Session) -> List[Category]:
    return (
        db.query(Category)
        .filter(Category.is_active == True)
        .order_by(Category.display_order)
        .all()
    )


def get_items_by_category(db: Session, category_id: int) -> List[MenuItem]:
    return (
        db.query(MenuItem)
        .filter(
            MenuItem.category_id == category_id,
            MenuItem.is_available == True,
        )
        .all()
    )


def get_menu_item(db: Session, item_id: int) -> Optional[MenuItem]:
    return db.query(MenuItem).filter(MenuItem.id == item_id).first()


def get_active_promotions(db: Session) -> List[Promotion]:
    now = datetime.utcnow()
    return (
        db.query(Promotion)
        .filter(
            Promotion.is_active == True,
            Promotion.start_date <= now,
            Promotion.end_date >= now,
        )
        .all()
    )


def get_price_for_customer(item: MenuItem, customer: Customer) -> float:
    if customer.is_vip and item.price_vip is not None:
        return item.price_vip
    return item.price
