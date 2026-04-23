import os
import sqlite3
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "vape_shop.db").replace("sqlite:///", "")

con = sqlite3.connect(DATABASE_URL)
for col_sql in [
    "ALTER TABLE products ADD COLUMN old_price REAL DEFAULT NULL",
    "ALTER TABLE products ADD COLUMN is_new INTEGER DEFAULT 0",
    "ALTER TABLE products ADD COLUMN is_hit INTEGER DEFAULT 0",
]:
    try:
        con.execute(col_sql)
        con.commit()
    except Exception:
        pass

try:
    con.execute("""
        CREATE TABLE IF NOT EXISTS site_stats (
            date TEXT PRIMARY KEY,
            visits INTEGER DEFAULT 0,
            bot_clicks INTEGER DEFAULT 0
        )
    """)
    con.commit()
except Exception:
    pass

try:
    con.execute("""
        CREATE TABLE IF NOT EXISTS web_orders (
            id TEXT PRIMARY KEY,
            name TEXT,
            phone TEXT,
            cart_json TEXT,
            status TEXT DEFAULT 'new',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    con.commit()
except Exception:
    pass
finally:
    con.close()

app = FastAPI(title="Vape Shop Admin")

BASE_DIR = os.path.dirname(__file__)
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

from web.routes import auth, dashboard, orders, products, customers, broadcasts, site
app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(orders.router)
app.include_router(products.router)
app.include_router(customers.router)
app.include_router(broadcasts.router)
app.include_router(site.router)
