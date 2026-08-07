"""Seed script — populates the database with a complete hamburger restaurant menu."""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from datetime import datetime, timedelta
from app.config import settings
from app.database import Base, engine, SessionLocal
from app.models.customer import Customer  # noqa
from app.models.menu import Category, MenuItem, Promotion
from app.models.order import Order, OrderItem  # noqa


def seed():
    print("🌱 Seeding database …")
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        # ── Categories ────────────────────────────────────────────────────────
        categories_data = [
            {"name": "Hamburguesas Clásicas",  "emoji": "🍔", "display_order": 1, "description": "Nuestras hamburguesas clásicas de siempre"},
            {"name": "Hamburguesas Especiales", "emoji": "🔥", "display_order": 2, "description": "Creaciones premium de nuestro chef"},
            {"name": "Papas y Acompañamientos", "emoji": "🍟", "display_order": 3, "description": "El complemento perfecto"},
            {"name": "Bebidas",                 "emoji": "🥤", "display_order": 4, "description": "Refrescantes opciones para tu pedido"},
            {"name": "Postres",                 "emoji": "🍰", "display_order": 5, "description": "El dulce final de tu experiencia"},
        ]

        cats = {}
        for cd in categories_data:
            cat = Category(**cd)
            db.add(cat)
            db.flush()
            cats[cd["name"]] = cat

        # ── Menu items ────────────────────────────────────────────────────────
        items_data = [
            # Hamburguesas Clásicas
            {"category": "Hamburguesas Clásicas", "name": "Classic Burger", "description": "Carne 180g, lechuga, tomate, cebolla, ketchup, mostaza", "price": 8.99, "price_vip": 7.99},
            {"category": "Hamburguesas Clásicas", "name": "Double Classic", "description": "Doble carne 360g, lechuga, tomate, cebolla, salsa especial", "price": 11.99, "price_vip": 10.49},
            {"category": "Hamburguesas Clásicas", "name": "Cheese Burger", "description": "Carne 180g, doble cheddar, pepinillos, mostaza, ketchup", "price": 9.99, "price_vip": 8.99},

            # Hamburguesas Especiales
            {"category": "Hamburguesas Especiales", "name": "BBQ Bacon Burger", "description": "Carne 200g, bacon crujiente, cheddar, cebolla caramelizada, salsa BBQ", "price": 14.99, "price_vip": 13.49, "is_special": True},
            {"category": "Hamburguesas Especiales", "name": "Mushroom Swiss", "description": "Carne 200g, hongos salteados, queso suizo, mayonesa de trufa", "price": 13.99, "price_vip": 12.49, "is_special": True},
            {"category": "Hamburguesas Especiales", "name": "Jalapeño Inferno", "description": "Carne 200g, jalapeños, pepper jack, sriracha, salsa de aguacate", "price": 12.99, "price_vip": 11.49, "is_special": True},
            {"category": "Hamburguesas Especiales", "name": "The Monster", "description": "Triple carne 540g, triple queso, triple bacon — para los valientes", "price": 18.99, "price_vip": 16.99, "is_special": True},

            # Papas y Acompañamientos
            {"category": "Papas y Acompañamientos", "name": "Papas Fritas Chicas", "description": "Crujientes papas fritas, sal marina", "price": 3.99},
            {"category": "Papas y Acompañamientos", "name": "Papas Fritas Grandes", "description": "Porción grande de papas fritas crujientes", "price": 5.49},
            {"category": "Papas y Acompañamientos", "name": "Papas con Cheddar", "description": "Papas fritas bañadas en salsa cheddar caliente", "price": 6.99},
            {"category": "Papas y Acompañamientos", "name": "Aros de Cebolla", "description": "Aros de cebolla crocantes con salsa dipping", "price": 5.99},

            # Bebidas
            {"category": "Bebidas", "name": "Coca-Cola", "description": "Coca-Cola fría 500ml", "price": 2.99},
            {"category": "Bebidas", "name": "Agua Mineral", "description": "Agua mineral sin gas 500ml", "price": 1.99},
            {"category": "Bebidas", "name": "Jugo de Naranja", "description": "Jugo de naranja natural 400ml", "price": 3.99},
            {"category": "Bebidas", "name": "Milkshake Vainilla", "description": "Milkshake cremoso de vainilla 450ml", "price": 5.99},
            {"category": "Bebidas", "name": "Milkshake Chocolate", "description": "Milkshake de chocolate belga 450ml", "price": 5.99},

            # Postres
            {"category": "Postres", "name": "Brownie con Helado", "description": "Brownie tibio de chocolate con bola de helado de vainilla", "price": 5.99},
            {"category": "Postres", "name": "Cheesecake", "description": "Cheesecake de frutos rojos con base de galleta", "price": 4.99},
            {"category": "Postres", "name": "Cookie", "description": "Cookie de chips de chocolate recién horneada", "price": 2.99},
        ]

        for item_data in items_data:
            cat_name = item_data.pop("category")
            item = MenuItem(
                category_id=cats[cat_name].id,
                is_special=item_data.pop("is_special", False),
                **item_data,
            )
            db.add(item)

        # ── Promotion ─────────────────────────────────────────────────────────
        promo = Promotion(
            title="Combo VIP Weekend",
            description="15% de descuento en pedidos mayores a $30 durante el fin de semana",
            discount_type="percentage",
            discount_value=15.0,
            min_order_value=30.0,
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=365),
            is_active=True,
        )
        db.add(promo)

        db.commit()
        print("✅ Seed complete! Database populated with:")
        print(f"   • {len(categories_data)} categories")
        print(f"   • {len(items_data)} menu items")
        print("   • 1 promotion")
    except Exception as e:
        db.rollback()
        print(f"❌ Error: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
