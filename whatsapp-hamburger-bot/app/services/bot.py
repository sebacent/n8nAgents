import copy
from typing import Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.models.customer import Customer, ConvState
from app.models.menu import Category, MenuItem
from app.services import menu_service, order_service


class ConversationBot:
    def handle_message(self, phone: str, message: str, db: Session) -> str:
        message = message.strip()
        customer = self._get_or_create_customer(db, phone)
        state = customer.conv_state

        if state == ConvState.idle.value:
            return self._handle_idle(customer, db)
        elif state == ConvState.welcome.value:
            return self._handle_welcome(customer, message, db)
        elif state == ConvState.main_menu.value:
            return self._handle_main_menu(customer, message, db)
        elif state == ConvState.category.value:
            return self._handle_category(customer, message, db)
        elif state == ConvState.item_detail.value:
            return self._handle_item_detail(customer, message, db)
        elif state == ConvState.cart.value:
            return self._handle_cart(customer, message, db)
        elif state == ConvState.confirm.value:
            return self._handle_confirm(customer, message, db)
        elif state == ConvState.payment.value:
            return self._handle_payment(customer, message, db)
        elif state == ConvState.address.value:
            return self._handle_address(customer, message, db)
        elif state == ConvState.placed.value:
            return self._handle_placed(customer, message, db)
        elif state == ConvState.rating.value:
            return self._handle_rating(customer, message, db)
        else:
            return self._handle_idle(customer, db)

    # -------------------------------------------------------------------------
    # State handlers
    # -------------------------------------------------------------------------

    def _handle_idle(self, customer: Customer, db: Session) -> str:
        self._set_state(customer, ConvState.welcome, {}, db)
        return (
            f"🍔 ¡Bienvenido a *{settings.RESTAURANT_NAME}*! 🍔\n\n"
            "Estamos felices de atenderte. ¿Cómo te llamas?"
        )

    def _handle_welcome(self, customer: Customer, message: str, db: Session) -> str:
        name = message.strip().title()
        if not name:
            return "Por favor, dime tu nombre para continuar 😊"
        data = copy.deepcopy(customer.conv_data or {})
        data["cart"] = data.get("cart", [])
        self._set_state(customer, ConvState.main_menu, data, db)
        customer.name = name
        db.commit()
        categories = menu_service.get_active_categories(db)
        menu_text = self._format_categories(categories)
        return (
            f"¡Mucho gusto, *{name}*! 🍔\n\n"
            f"Aquí está nuestro menú:\n\n{menu_text}\n\n"
            "Elige una categoría con su número 👆"
        )

    def _handle_main_menu(self, customer: Customer, message: str, db: Session) -> str:
        categories = menu_service.get_active_categories(db)
        data = copy.deepcopy(customer.conv_data or {})
        cart = data.get("cart", [])

        if message == "0":
            if not cart:
                return (
                    "🛒 Tu carrito está vacío.\n\n"
                    + self._format_categories(categories)
                    + "\n\nElige una categoría:"
                )
            self._set_state(customer, ConvState.cart, data, db)
            return self._show_cart(cart, customer)

        try:
            idx = int(message) - 1
            if idx < 0 or idx >= len(categories):
                raise ValueError
        except ValueError:
            menu_text = self._format_categories(categories)
            extra = '\n0️⃣ Ver carrito' if cart else ''
            return f"Opción no válida. Elige una categoría:\n\n{menu_text}{extra}"

        category = categories[idx]
        items = menu_service.get_items_by_category(db, category.id)
        data["category_id"] = category.id
        self._set_state(customer, ConvState.category, data, db)
        items_text = self._format_items(items, customer)
        return (
            f"{category.emoji} *{category.name}*\n\n"
            f"{items_text}\n\n"
            "0️⃣ Volver al menú principal"
        )

    def _handle_category(self, customer: Customer, message: str, db: Session) -> str:
        data = copy.deepcopy(customer.conv_data or {})
        cart = data.get("cart", [])
        category_id = data.get("category_id")

        if message == "0":
            self._set_state(customer, ConvState.main_menu, data, db)
            categories = menu_service.get_active_categories(db)
            menu_text = self._format_categories(categories)
            extra = '\n0️⃣ Ver carrito' if cart else ''
            return f"🏠 Menú principal:\n\n{menu_text}{extra}\n\nElige una categoría:"

        items = menu_service.get_items_by_category(db, category_id) if category_id else []
        try:
            idx = int(message) - 1
            if idx < 0 or idx >= len(items):
                raise ValueError
        except ValueError:
            items_text = self._format_items(items, customer)
            return f"Opción no válida. Elige un item:\n\n{items_text}\n\n0️⃣ Volver al menú"

        item = items[idx]
        data["item_id"] = item.id
        self._set_state(customer, ConvState.item_detail, data, db)
        price = menu_service.get_price_for_customer(item, customer)
        vip_note = " 🌟 *Precio VIP*" if customer.is_vip and item.price_vip is not None else ""
        special_note = " ⭐ *Especial*" if item.is_special else ""
        return (
            f"{'⭐ ' if item.is_special else ''}*{item.name}*{special_note}\n\n"
            f"📝 {item.description or 'Deliciosa opción de nuestra carta.'}\n\n"
            f"💰 Precio: *${price:.2f}*{vip_note}\n\n"
            "¿Cuántas unidades deseas? (1-10)\n"
            "0️⃣ Volver"
        )

    def _handle_item_detail(self, customer: Customer, message: str, db: Session) -> str:
        data = copy.deepcopy(customer.conv_data or {})
        item_id = data.get("item_id")

        if message == "0":
            self._set_state(customer, ConvState.category, data, db)
            category_id = data.get("category_id")
            items = menu_service.get_items_by_category(db, category_id) if category_id else []
            items_text = self._format_items(items, customer)
            return f"{items_text}\n\n0️⃣ Volver al menú principal"

        try:
            qty = int(message)
            if qty < 1 or qty > 10:
                raise ValueError
        except ValueError:
            return "Por favor, ingresa un número del 1 al 10 (o 0 para volver) 🔢"

        item = menu_service.get_menu_item(db, item_id) if item_id else None
        if not item:
            return "❌ Item no encontrado. Volviendo al menú..."

        price = menu_service.get_price_for_customer(item, customer)
        cart = data.get("cart", [])

        # Check if item already in cart - update quantity
        found = False
        for cart_item in cart:
            if cart_item["item_id"] == item.id:
                cart_item["quantity"] += qty
                found = True
                break
        if not found:
            cart.append({
                "item_id": item.id,
                "quantity": qty,
                "unit_price": price,
                "name": item.name,
            })

        data["cart"] = cart
        self._set_state(customer, ConvState.cart, data, db)
        return (
            f"✅ *{qty}x {item.name}* agregado al carrito!\n\n"
            + self._show_cart(cart, customer)
        )

    def _handle_cart(self, customer: Customer, message: str, db: Session) -> str:
        data = copy.deepcopy(customer.conv_data or {})
        cart = data.get("cart", [])

        if not cart:
            self._set_state(customer, ConvState.main_menu, data, db)
            categories = menu_service.get_active_categories(db)
            menu_text = self._format_categories(categories)
            return f"🛒 Tu carrito está vacío.\n\n{menu_text}\n\nElige una categoría:"

        if message == "1":
            self._set_state(customer, ConvState.main_menu, data, db)
            categories = menu_service.get_active_categories(db)
            menu_text = self._format_categories(categories)
            extra = '\n0️⃣ Ver carrito' if cart else ''
            return f"🏠 Menú principal:\n\n{menu_text}{extra}\n\nElige una categoría:"
        elif message == "2":
            self._set_state(customer, ConvState.confirm, data, db)
            return self._show_order_summary(cart, customer)
        elif message == "3":
            data["cart"] = []
            self._set_state(customer, ConvState.main_menu, data, db)
            categories = menu_service.get_active_categories(db)
            menu_text = self._format_categories(categories)
            return f"🗑️ Carrito vaciado.\n\n{menu_text}\n\nElige una categoría:"
        else:
            return self._show_cart(cart, customer)

    def _handle_confirm(self, customer: Customer, message: str, db: Session) -> str:
        data = copy.deepcopy(customer.conv_data or {})
        cart = data.get("cart", [])
        msg_lower = message.lower().strip()

        if msg_lower in ("s", "si", "sí", "y", "yes"):
            self._set_state(customer, ConvState.payment, data, db)
            return (
                "💳 *Método de pago*\n\n"
                "1️⃣ Efectivo 💵\n"
                "2️⃣ Tarjeta 💳\n"
                "3️⃣ Transferencia 🏦\n\n"
                "Elige una opción:"
            )
        elif msg_lower in ("n", "no"):
            self._set_state(customer, ConvState.cart, data, db)
            return self._show_cart(cart, customer)
        else:
            return (
                "Por favor responde *S* para confirmar o *N* para volver al carrito.\n\n"
                + self._show_order_summary(cart, customer)
            )

    def _handle_payment(self, customer: Customer, message: str, db: Session) -> str:
        data = copy.deepcopy(customer.conv_data or {})

        if message == "1":
            data["payment_method"] = "cash"
            self._set_state(customer, ConvState.address, data, db)
            return (
                "📍 *¿Cuál es tu dirección de entrega?*\n\n"
                "Escribe tu dirección completa o *RETIRO* para retirar en el local."
            )
        elif message == "2":
            data["payment_method"] = "card"
            self._set_state(customer, ConvState.address, data, db)
            return (
                "📍 *¿Cuál es tu dirección de entrega?*\n\n"
                "Escribe tu dirección completa o *RETIRO* para retirar en el local."
            )
        elif message == "3":
            data["payment_method"] = "transfer"
            self._set_state(customer, ConvState.address, data, db)
            return (
                "🏦 *Datos para transferencia:*\n"
                "Banco: Banco Nacional\n"
                "CBU: 0000 0000 0000 0000 0001\n"
                "Alias: BURGER.PALACE\n\n"
                "📍 *¿Cuál es tu dirección de entrega?*\n\n"
                "Escribe tu dirección completa o *RETIRO* para retirar en el local."
            )
        else:
            return (
                "Opción no válida. Elige tu método de pago:\n\n"
                "1️⃣ Efectivo 💵\n"
                "2️⃣ Tarjeta 💳\n"
                "3️⃣ Transferencia 🏦"
            )

    def _handle_address(self, customer: Customer, message: str, db: Session) -> str:
        data = copy.deepcopy(customer.conv_data or {})
        cart = data.get("cart", [])
        payment_method = data.get("payment_method", "cash")

        if message.upper().strip() == "RETIRO":
            address = "Retiro en local"
        else:
            address = message.strip()
            if not address:
                return "Por favor, escribe tu dirección de entrega 📍"

        order = order_service.create_order(
            db=db,
            customer=customer,
            cart_data=cart,
            payment_method=payment_method,
            address=address,
        )

        data["order_id"] = order.id
        data["cart"] = []
        self._set_state(customer, ConvState.placed, data, db)

        payment_labels = {"cash": "Efectivo 💵", "card": "Tarjeta 💳", "transfer": "Transferencia 🏦"}
        payment_label = payment_labels.get(payment_method, payment_method)

        return (
            f"🎉 *¡Pedido #{order.id:04d} confirmado!*\n\n"
            f"📍 {address}\n"
            f"💳 {payment_label}\n"
            f"💰 Total: *${order.total:.2f}*\n\n"
            f"⏱️ Estamos preparando tu pedido. Te avisaremos cuando esté listo.\n\n"
            f"¿Deseas hacer otro pedido? (S/N)"
        )

    def _handle_placed(self, customer: Customer, message: str, db: Session) -> str:
        data = copy.deepcopy(customer.conv_data or {})
        order_id = data.get("order_id")
        msg_lower = message.lower().strip()

        if msg_lower in ("s", "si", "sí", "y", "yes"):
            data["cart"] = []
            data.pop("order_id", None)
            self._set_state(customer, ConvState.main_menu, data, db)
            categories = menu_service.get_active_categories(db)
            menu_text = self._format_categories(categories)
            return (
                f"¡Genial! 🍔 Aquí está nuestro menú:\n\n{menu_text}\n\n"
                "Elige una categoría:"
            )
        elif msg_lower in ("n", "no"):
            self._set_state(customer, ConvState.rating, data, db)
            order_num = f"#{order_id:04d}" if order_id else "#----"
            return (
                f"¡Gracias por tu pedido {order_num}! 🙏\n\n"
                "⭐ *¿Cómo calificarías tu experiencia?*\n"
                "Responde con un número del 1 al 5\n"
                "1️⃣ 2️⃣ 3️⃣ 4️⃣ 5️⃣"
            )
        else:
            order_num = f"#{order_id:04d}" if order_id else "#----"
            return (
                f"Tu pedido *{order_num}* está siendo preparado. 🍳\n\n"
                "¿Deseas hacer otro pedido? (S/N)"
            )

    def _handle_rating(self, customer: Customer, message: str, db: Session) -> str:
        data = copy.deepcopy(customer.conv_data or {})
        order_id = data.get("order_id")

        try:
            rating = int(message.strip())
            if rating < 1 or rating > 5:
                raise ValueError
        except ValueError:
            return (
                "Por favor, responde con un número del 1 al 5 ⭐\n"
                "1️⃣ 2️⃣ 3️⃣ 4️⃣ 5️⃣"
            )

        if order_id:
            order_service.add_rating(db, order_id, rating)

        stars = "⭐" * rating
        messages = {
            1: "Lamentamos tu experiencia. Trabajaremos para mejorar.",
            2: "Gracias por tu comentario. Seguiremos mejorando.",
            3: "¡Gracias! Esperamos verte pronto.",
            4: "¡Genial! Nos alegra que hayas disfrutado tu pedido. 😊",
            5: "¡Increíble! ¡Muchas gracias por tu valoración! 🎉",
        }
        self._set_state(customer, ConvState.idle, {}, db)
        return (
            f"{stars} ¡Gracias por calificarnos con {rating}/5!\n\n"
            f"{messages.get(rating, '')}\n\n"
            f"¡Hasta la próxima en *{settings.RESTAURANT_NAME}*! 🍔"
        )

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _get_or_create_customer(self, db: Session, phone: str) -> Customer:
        customer = db.query(Customer).filter(Customer.phone == phone).first()
        if not customer:
            customer = Customer(
                phone=phone,
                conv_state=ConvState.idle.value,
                conv_data={},
            )
            db.add(customer)
            db.commit()
            db.refresh(customer)
        return customer

    def _set_state(
        self,
        customer: Customer,
        state: ConvState,
        data: dict,
        db: Session,
    ) -> None:
        customer.conv_state = state.value
        customer.conv_data = data
        db.add(customer)
        db.commit()

    def _cart_total(self, cart: list) -> float:
        return sum(item["unit_price"] * item["quantity"] for item in cart)

    def _format_cart(self, cart: list, customer: Optional[Customer] = None) -> str:
        if not cart:
            return "🛒 Tu carrito está vacío."
        lines = []
        for item in cart:
            subtotal = item["unit_price"] * item["quantity"]
            lines.append(
                f"  • {item['quantity']}x *{item['name']}* — ${subtotal:.2f}"
            )
        total = self._cart_total(cart)
        lines.append(f"\n💰 *Subtotal: ${total:.2f}*")
        return "\n".join(lines)

    def _format_categories(self, categories: list) -> str:
        if not categories:
            return "No hay categorías disponibles."
        lines = []
        for i, cat in enumerate(categories, 1):
            lines.append(f"{i}️⃣ {cat.emoji} {cat.name}")
        return "\n".join(lines)

    def _format_items(self, items: list, customer: Customer) -> str:
        if not items:
            return "No hay items disponibles en esta categoría."
        lines = []
        for i, item in enumerate(items, 1):
            price = menu_service.get_price_for_customer(item, customer)
            special_mark = " ⭐" if item.is_special else ""
            vip_mark = " 🌟" if customer.is_vip and item.price_vip is not None else ""
            lines.append(f"{i}️⃣ *{item.name}*{special_mark} — ${price:.2f}{vip_mark}")
        return "\n".join(lines)

    def _show_cart(self, cart: list, customer: Customer) -> str:
        cart_text = self._format_cart(cart, customer)
        return (
            f"🛒 *Tu carrito:*\n\n{cart_text}\n\n"
            "1️⃣ Seguir comprando\n"
            "2️⃣ Confirmar pedido ✅\n"
            "3️⃣ Vaciar carrito 🗑️\n\n"
            "Elige una opción:"
        )

    def _show_order_summary(self, cart: list, customer: Customer) -> str:
        cart_text = self._format_cart(cart, customer)
        total = self._cart_total(cart)
        return (
            f"📋 *Resumen de tu pedido:*\n\n{cart_text}\n\n"
            f"💰 *Total a pagar: ${total:.2f}*\n\n"
            "¿Confirmas tu pedido? (*S* / *N*)"
        )
