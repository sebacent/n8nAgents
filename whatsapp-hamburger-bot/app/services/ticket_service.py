from typing import Dict, List

from app.models.order import Order


def generate_ticket_data(order: Order) -> Dict:
    order_number = f"#{order.id:04d}"

    items: List[Dict] = []
    for item in order.items:
        items.append(
            {
                "name": item.menu_item.name if item.menu_item else f"Item #{item.menu_item_id}",
                "quantity": item.quantity,
                "unit_price": item.unit_price,
                "subtotal": item.subtotal,
            }
        )

    customer_name = order.customer.name if order.customer and order.customer.name else "Cliente"
    phone = order.customer.phone if order.customer else ""

    payment_labels = {
        "cash": "Efectivo",
        "card": "Tarjeta",
        "transfer": "Transferencia",
    }
    payment_label = payment_labels.get(order.payment_method or "", order.payment_method or "N/A")

    return {
        "order_number": order_number,
        "customer_name": customer_name,
        "phone": phone,
        "items": items,
        "subtotal": round(order.subtotal, 2),
        "discount": round(order.discount, 2),
        "total": round(order.total, 2),
        "payment_method": payment_label,
        "address": order.delivery_address or "N/A",
        "notes": order.notes or "",
        "created_at": order.created_at,
    }
