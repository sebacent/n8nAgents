# WhatsApp Agent — Gastos & Comidas

Agente personal de WhatsApp conectado a tu número con Evolution API, n8n, OpenAI y Supabase. Registra gastos y comidas con lenguaje natural, sin ninguna API oficial de Meta.

---

## Arquitectura

```
WhatsApp personal
      ↓
Evolution API  (WhatsApp Web session)
      ↓ webhook POST
n8n Workflow
      ↓
OpenAI gpt-4o-mini  (detectar intención + extraer datos)
      ↓
Switch por intent
  ├── registrar_gasto  → Supabase (gastos)
  ├── registrar_comida → Supabase (comidas)
  ├── comando          → consultar Supabase y formatear
  └── fallback         → mensaje de ayuda
      ↓
Evolution API  (sendText → respuesta al usuario)
```

---

## Stack

| Componente     | Rol                                      |
|----------------|------------------------------------------|
| Evolution API  | Puente WhatsApp Web ↔ HTTP               |
| n8n            | Orquestador del workflow                 |
| OpenAI         | Parser de intenciones (gpt-4o-mini)      |
| Supabase       | Base de datos + REST API                 |
| Docker         | Contenedores para n8n y Evolution API    |

---

## Prerrequisitos

- Docker y Docker Compose instalados
- Cuenta OpenAI con crédito (gpt-4o-mini es muy barato)
- Proyecto Supabase creado (plan free alcanza)
- Un número de WhatsApp disponible para conectar (puede ser el personal)

---

## Instalación paso a paso

### 1. Clonar y configurar variables

```bash
git clone <este-repo>
cd whatsapp-agent

cp .env.example .env
# Editar .env con tus valores reales
```

### 2. Configurar Supabase

En el dashboard de Supabase → SQL Editor, ejecutar todo el contenido de `database.sql`:

```sql
-- Esto crea tablas, índices, vistas y funciones
-- Ver archivo database.sql
```

Copiar las credenciales:
- `SUPABASE_URL` → Settings → API → Project URL
- `SUPABASE_KEY` → Settings → API → **service_role** key (no la anon!)

### 3. Levantar los servicios

```bash
docker-compose up -d
```

Verificar que estén corriendo:
```bash
docker-compose ps
docker-compose logs -f
```

### 4. Crear instancia en Evolution API

```bash
# Crear la instancia (usar el mismo nombre que EVOLUTION_INSTANCE en .env)
curl -X POST http://localhost:8080/instance/create \
  -H "apikey: TU_EVOLUTION_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "instanceName": "personal",
    "qrcode": true,
    "integration": "WHATSAPP-BAILEYS"
  }'
```

### 5. Conectar WhatsApp con QR

```bash
# Obtener el QR code
curl http://localhost:8080/instance/fetchInstances \
  -H "apikey: TU_EVOLUTION_API_KEY"

# O abrir en el navegador para ver QR visual:
# http://localhost:8080/instance/qrcode/personal
```

Escanear el QR desde WhatsApp → Dispositivos Vinculados → Vincular dispositivo.

Verificar que la instancia quedó conectada:
```bash
curl http://localhost:8080/instance/connectionState/personal \
  -H "apikey: TU_EVOLUTION_API_KEY"
# Debe devolver: "state": "open"
```

### 6. Importar el workflow en n8n

1. Abrir n8n en `http://localhost:5678`
2. Menú lateral → **Workflows** → botón **Import from file**
3. Seleccionar `n8n-workflow.json`
4. El workflow se importa con todos sus nodos ya configurados

### 7. Activar el workflow

En n8n, abrir el workflow importado y hacer clic en el toggle **Active** (esquina superior derecha).

El webhook queda disponible en:
```
http://localhost:5678/webhook/whatsapp-agent
```

### 8. Configurar el webhook en Evolution API

```bash
curl -X POST http://localhost:8080/webhook/set/personal \
  -H "apikey: TU_EVOLUTION_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "http://n8n:5678/webhook/whatsapp-agent",
    "webhook_by_events": false,
    "webhook_base64": false,
    "events": ["MESSAGES_UPSERT"]
  }'
```

> Si n8n y Evolution API corren en Docker Compose juntos, usar `http://n8n:5678`.
> Si n8n está en un host externo, usar la URL pública.

---

## Variables de entorno requeridas

| Variable             | Descripción                                     |
|----------------------|-------------------------------------------------|
| `OPENAI_API_KEY`     | API key de OpenAI                               |
| `SUPABASE_URL`       | URL del proyecto Supabase                       |
| `SUPABASE_KEY`       | Service role key de Supabase                    |
| `EVOLUTION_API_URL`  | URL base de Evolution API                       |
| `EVOLUTION_API_KEY`  | API key de Evolution API                        |
| `EVOLUTION_INSTANCE` | Nombre de la instancia (ej: `personal`)         |

En n8n, estas variables se configuran en **Settings → Environment Variables** o se pasan vía Docker Compose en el bloque `environment:`.

---

## Nodos del workflow — Explicación detallada

### 1. `Webhook Evolution API`
**Tipo:** n8n-nodes-base.webhook  
Recibe el POST de Evolution API con cada mensaje nuevo. Responde `200 OK` de inmediato (modo `onReceived`) y procesa de forma asíncrona. Path: `/whatsapp-agent`.

### 2. `Extract and Filter Message`
**Tipo:** Code  
Extrae el texto del mensaje y el número de teléfono del payload de Evolution API. Filtra automáticamente:
- Mensajes vacíos
- Mensajes enviados por el propio bot (`fromMe: true`)
- Mensajes de grupos

Si el mensaje no es válido, retorna `[]` y el workflow se detiene sin error.

**Payload que maneja:**
```json
{
  "data": {
    "message": { "conversation": "cafe 120" },
    "key": { "remoteJid": "59899123456@s.whatsapp.net", "fromMe": false }
  }
}
```

### 3. `Prepare OpenAI Request`
**Tipo:** Code  
Construye el body para la API de OpenAI con el system prompt optimizado. Pasa al nodo siguiente el `phone`, `usuario`, `message` y el body de OpenAI listo para enviar.

### 4. `Call OpenAI API`
**Tipo:** HTTP Request  
Llama a `POST https://api.openai.com/v1/chat/completions` con `gpt-4o-mini`. Usa `response_format: { type: "json_object" }` para forzar JSON válido. Máximo 120 tokens, temperatura 0 (determinista).

### 5. `Parse AI Response`
**Tipo:** Code  
Parsea la respuesta de OpenAI y valida la estructura del JSON. Si hay error de parseo o intent inválido, normaliza a `fallback`. Combina los datos de OpenAI con el `phone` y `usuario` del nodo 3.

**Salida estándar:**
```json
{
  "phone": "59899123456",
  "usuario": "59899123456",
  "message": "cafe 120",
  "intent": "registrar_gasto",
  "data": { "descripcion": "Café", "categoria": "comida", "monto": 120 }
}
```

### 6. `Route by Intent`
**Tipo:** Switch  
Enruta según `$json.intent`:
- Output 0 → `registrar_gasto`
- Output 1 → `registrar_comida`
- Output 2 → `comando`
- Output 3 (fallback) → cualquier otra cosa

### 7. `Save Gasto Supabase`
**Tipo:** HTTP Request  
`POST {SUPABASE_URL}/rest/v1/gastos` con los campos `usuario`, `descripcion`, `categoria`, `monto`. Usa la service role key para bypasear RLS.

### 8. `Format Gasto Response`
**Tipo:** Code  
Formatea la respuesta de texto para WhatsApp. Referencia el nodo `Parse AI Response` para obtener los datos originales. Salida: `{ phone, responseText }`.

### 9. `Save Comida Supabase`
**Tipo:** HTTP Request  
`POST {SUPABASE_URL}/rest/v1/comidas` con `usuario`, `alimento`, `cantidad`, `calorias`.

### 10. `Format Comida Response`
**Tipo:** Code  
Formatea la respuesta de texto para WhatsApp. Incluye las calorías estimadas por OpenAI.

### 11. `Route Command`
**Tipo:** Switch  
Sub-switch para comandos:
- Output 0 → `resumen`
- Output 1 → `gastos_hoy`
- Output 2 → `calorias_hoy`
- Output 3 (fallback) → lista de comandos disponibles

### 12. `Resumen Handler`
**Tipo:** Code  
Consulta Supabase en paralelo (`Promise.all`) para obtener gastos y comidas del día. Calcula totales y formatea el resumen completo.

### 13. `Gastos Hoy Handler`
**Tipo:** Code  
Consulta la tabla `gastos` del día actual y formatea lista detallada con total.

### 14. `Calorias Handler`
**Tipo:** Code  
Consulta la tabla `comidas` del día actual, calcula calorías totales y muestra diferencia con meta de 2000 kcal.

### 15. `Format Fallback`
**Tipo:** Code  
Respuesta de ayuda con ejemplos de uso cuando el mensaje no es reconocido.

### 16. `Send WhatsApp Message`
**Tipo:** HTTP Request  
`POST {EVOLUTION_API_URL}/message/sendText/{EVOLUTION_INSTANCE}`. Recibe conexiones de TODOS los nodos de formato. Envía el `responseText` al `phone` correspondiente. Configurado con `neverError: true` para no interrumpir el workflow si hay un fallo de envío.

---

## Ejemplos de uso

### Registrar gastos
```
cafe 120
uber 350
supermercado 2500
gasté 400 en nafta
compré medicamentos 800
almuerzo 250
```

### Registrar comidas
```
pizza 2 porciones
desayuno cafe y tostadas
manzana
almuerzo pollo con arroz
cena ensalada y pollo grillado
yogur con granola
```

### Comandos
```
resumen
gastos hoy
calorias hoy
```

---

## Respuestas del agente

**Gasto registrado:**
```
💸 Gasto registrado
Café (comida)
$ 120 UYU
```

**Comida registrada:**
```
🍽 Comida registrada
Pizza (2 porciones)
560 kcal
```

**Resumen del día:**
```
📊 Resumen del día
lunes, 26 de mayo

💸 Gastos: $970 UYU
  • Café: $120
  • Uber: $350
  • Nafta: $400

🍽 Calorías: 700 kcal
  • Pizza (2 porciones): 560 kcal
  • Manzana (1 unidad): 80 kcal
  • Café con leche (1 taza): 60 kcal
```

---

## Evolution API — Referencia de endpoints

### Autenticación
Todos los endpoints requieren el header:
```
apikey: TU_EVOLUTION_API_KEY
```

### Crear instancia
```bash
POST /instance/create
{
  "instanceName": "personal",
  "qrcode": true,
  "integration": "WHATSAPP-BAILEYS"
}
```

### Ver estado de conexión
```bash
GET /instance/connectionState/personal
```

### Enviar mensaje de texto
```bash
POST /message/sendText/personal
Content-Type: application/json
apikey: TU_EVOLUTION_API_KEY

{
  "number": "59899123456",
  "text": "Hola desde el bot!"
}
```

### Configurar webhook
```bash
POST /webhook/set/personal
{
  "url": "http://n8n:5678/webhook/whatsapp-agent",
  "events": ["MESSAGES_UPSERT"]
}
```

### Ver instancias activas
```bash
GET /instance/fetchInstances
```

---

## Manejo de errores

| Situación                    | Comportamiento                                           |
|------------------------------|----------------------------------------------------------|
| Mensaje vacío                | Filtrado en `Extract and Filter Message`, no procesa     |
| Mensaje propio (fromMe)      | Filtrado en `Extract and Filter Message`, no procesa     |
| Mensaje de grupo             | Filtrado en `Extract and Filter Message`, no procesa     |
| OpenAI devuelve JSON inválido | Normaliza a `fallback` en `Parse AI Response`            |
| Supabase falla al guardar    | El workflow continúa y responde igualmente               |
| Evolution API no envía       | `neverError: true` evita romper el workflow              |
| Intent desconocido           | Switch fallback → mensaje de ayuda                       |
| Timeout OpenAI (>30s)        | n8n retorna error, no responde al usuario                |

---

## Multi-usuario

El workflow ya está preparado para múltiples usuarios. Cada registro en Supabase incluye el campo `usuario` (número de teléfono), lo que permite:

- Múltiples personas enviando mensajes al mismo número bot
- Reportes separados por usuario
- Dashboard con filtro por usuario

Para un bot personal (1 usuario), el campo `usuario` siempre será tu número y puedes ignorarlo en las consultas.

---

## Extensiones futuras (preparadas)

### Reportes automáticos quincenales
La función `get_reporte_quincenal(usuario)` en Supabase ya está implementada. Para activar el envío automático:
1. Agregar nodo **Schedule Trigger** en n8n (cron: `0 8 1,16 * *`)
2. Consultar la función RPC de Supabase
3. Formatear y enviar por WhatsApp

### Dashboard
La vista `dashboard_diario` en Supabase está lista para conectar con:
- Metabase (self-hosted, gratis)
- Grafana
- Retool
- Supabase Dashboard + Chart.js

### Estadísticas mensuales
Usar la vista `top_categorias_mensual` para análisis de categorías.

### Tracking nutricional avanzado
Agregar campos a la tabla `comidas`:
```sql
alter table comidas add column proteinas numeric;
alter table comidas add column carbohidratos numeric;
alter table comidas add column grasas numeric;
```
Y extender el prompt de OpenAI para extraer macros.

### Categorías automáticas inteligentes
El campo `categoria` ya es asignado automáticamente por gpt-4o-mini. Se puede mejorar con ejemplos en el system prompt.

### Memoria diaria
Agregar tabla `contexto_diario` que guarda el historial del día para incluirlo en el prompt de OpenAI.

---

## Costos estimados (referencia)

| Servicio     | Estimación                                     |
|--------------|------------------------------------------------|
| OpenAI       | ~$0.001 por mensaje (gpt-4o-mini, ~130 tokens) |
| Supabase     | Free tier: 500MB DB, 2GB storage               |
| Evolution API| Auto-hosted, sin costo                          |
| n8n          | Auto-hosted, sin costo (cloud desde $20/mes)   |

Para uso personal (50-100 mensajes/día): **< $2/mes** en OpenAI.

---

## Troubleshooting

**El webhook no recibe mensajes:**
- Verificar que Evolution API puede alcanzar n8n: `curl http://n8n:5678/healthz`
- Verificar que el webhook está configurado: `GET /webhook/find/personal`
- Revisar logs de Evolution API: `docker-compose logs evolution-api`

**OpenAI devuelve error 401:**
- Verificar `OPENAI_API_KEY` en las variables de entorno de n8n
- En n8n: Settings → Environment Variables

**Supabase devuelve error 401/403:**
- Asegurarse de usar la **service_role** key, no la anon key
- Verificar que RLS permite inserts desde service role

**El bot responde pero no guarda en Supabase:**
- Revisar los logs de ejecución en n8n → Executions
- Verificar que las tablas existen: ejecutar `database.sql` en Supabase

**QR de Evolution API no aparece:**
```bash
curl http://localhost:8080/instance/connect/personal \
  -H "apikey: TU_KEY"
```
