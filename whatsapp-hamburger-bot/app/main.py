from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.database import engine, Base
import app.models  # noqa: F401 — registers all models with Base

from app.routes.webhook import router as webhook_router
from app.routes.orders import router as orders_router
from app.routes.admin import router as admin_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Hamburger Bot API",
    description="WhatsApp order bot for a hamburger restaurant",
    version="1.0.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")

app.include_router(webhook_router)
app.include_router(orders_router)
app.include_router(admin_router)


@app.get("/")
def root():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/admin/dashboard")
