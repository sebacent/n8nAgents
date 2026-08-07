# WhatsApp Hamburger Order Bot

Bot de pedidos por WhatsApp para una hamburguesería, con panel de administración web.

**Stack:** FastAPI · Twilio · SQLAlchemy (SQLite) · Jinja2 · Bootstrap 5

> Nota: esta es una implementación en Python/FastAPI, distinta del agente
> basado en n8n que vive en `../whatsapp-agent/`.

## Características

- **Bot conversacional de 11 estados**
  `idle → welcome → main_menu → category → item_detail → cart → confirm → payment → address → placed → rating`
  - Mensajes en español con emojis y opciones numeradas
  - Carrito persistido en `Customer.conv_data` (JSON)
  - Métodos de pago: efectivo / tarjeta / transferencia
  - Entrega a domicilio o retiro en local (`RETIRO`)
  - Flujo de calificación (1–5 ⭐) al finalizar
- **Modelos SQLAlchemy:** Customer (VIP automático a los 5 pedidos), Category,
  MenuItem (`price_vip`, `is_special`), Order, OrderItem, Promotion
- **Webhook de Twilio** (`POST /webhook/twilio`) con respuestas TwiML XML
- **Panel admin Bootstrap 5:** dashboard, pedidos (con actualización AJAX de
  estado), menú (ABM con modales), clientes (toggle VIP), ticket imprimible
- **API JSON** en `/api/orders`
- **Seed** con menú completo (5 categorías, 19 productos, 1 promoción)

## Estructura

```
whatsapp-hamburger-bot/
├── app/
│   ├── config.py · database.py · main.py
│   ├── models/    customer.py · menu.py · order.py
│   ├── routes/    webhook.py · orders.py · admin.py
│   └── services/  bot.py · menu_service.py · order_service.py · ticket_service.py
├── templates/admin/  base · dashboard · orders · menu · customers · ticket
├── static/css/admin.css
├── seed_menu.py
├── requirements.txt
└── .env.example
```

## Puesta en marcha

```bash
cd whatsapp-hamburger-bot
pip install -r requirements.txt
cp .env.example .env          # completá tus credenciales de Twilio
python seed_menu.py           # carga el menú
uvicorn app.main:app --reload # http://localhost:8000/admin
```

### Configurar el webhook de Twilio

En la consola de Twilio (WhatsApp Sandbox o número productivo), apuntá el
webhook de mensajes entrantes a:

```
https://TU_DOMINIO/webhook/twilio    (POST)
```

Para desarrollo local podés exponer el puerto con un túnel (ngrok, cloudflared, etc.).

## Estados de un pedido

`pending → confirmed → preparing → ready → delivered` (o `cancelled`)

Se gestionan desde el panel de **Pedidos**, con actualización en vivo vía AJAX.
