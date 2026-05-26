import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv
from database.init_db import create_tables

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_tables()
    yield


app = FastAPI(title="Vape Shop Admin", lifespan=lifespan)

BASE_DIR = os.path.dirname(__file__)
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

from web.routes import auth, dashboard, orders, products, customers, broadcasts, site, content_manager
app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(orders.router)
app.include_router(products.router)
app.include_router(customers.router)
app.include_router(broadcasts.router)
app.include_router(site.router)
app.include_router(content_manager.router)
