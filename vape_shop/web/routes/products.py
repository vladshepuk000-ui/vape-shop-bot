import os
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import aiosqlite
from web.auth_utils import verify_session

BASE_DIR = os.path.join(os.path.dirname(__file__), "..", "templates")
templates = Jinja2Templates(directory=BASE_DIR)
DATABASE_URL = os.getenv("DATABASE_URL", "vape_shop.db").replace("sqlite:///", "")

CATEGORIES = {
    "liquids":    "Рідини",
    "cartridges": "Картриджі",
    "systems":    "Системи (поди)",
}

router = APIRouter(prefix="/products")


@router.get("", response_class=HTMLResponse)
async def products_list(request: Request, session: str = Depends(verify_session)):
    if not session:
        return RedirectResponse(url="/login")

    async with aiosqlite.connect(DATABASE_URL) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM products ORDER BY is_active DESC, category, name"
        ) as cur:
            products = await cur.fetchall()

    return templates.TemplateResponse(request, "products.html", {
        "products": products,
        "categories": CATEGORIES,
    })


@router.post("/add")
async def add_product(
    name: str = Form(...),
    description: str = Form(""),
    category: str = Form("liquids"),
    price: float = Form(...),
    old_price: str = Form(""),
    stock: int = Form(...),
    session: str = Depends(verify_session),
):
    if not session:
        return RedirectResponse(url="/login")

    try:
        old_price_val = float(old_price) if old_price.strip() else None
    except ValueError:
        old_price_val = None

    async with aiosqlite.connect(DATABASE_URL) as db:
        await db.execute(
            "INSERT INTO products (name, description, category, price, old_price, stock, is_active) VALUES (?, ?, ?, ?, ?, ?, 1)",
            (name, description, category, price, old_price_val, stock)
        )
        await db.commit()

    return RedirectResponse(url="/products", status_code=302)


@router.post("/{product_id}/edit")
async def edit_product(
    product_id: int,
    name: str = Form(...),
    description: str = Form(""),
    price: float = Form(...),
    stock: int = Form(...),
    old_price: str = Form(""),
    is_new: str = Form(""),
    is_hit: str = Form(""),
    session: str = Depends(verify_session),
):
    if not session:
        return RedirectResponse(url="/login")

    try:
        old_price_val = float(old_price) if old_price.strip() else None
    except ValueError:
        old_price_val = None

    async with aiosqlite.connect(DATABASE_URL) as db:
        await db.execute(
            "UPDATE products SET name=?, description=?, price=?, stock=?, old_price=?, is_new=?, is_hit=? WHERE id=?",
            (name, description, price, stock, old_price_val, 1 if is_new else 0, 1 if is_hit else 0, product_id)
        )
        await db.commit()

    return RedirectResponse(url="/products", status_code=302)


@router.post("/{product_id}/toggle")
async def toggle_product(product_id: int, session: str = Depends(verify_session)):
    if not session:
        return RedirectResponse(url="/login")

    async with aiosqlite.connect(DATABASE_URL) as db:
        await db.execute(
            "UPDATE products SET is_active = NOT is_active WHERE id = ?", (product_id,)
        )
        await db.commit()

    return RedirectResponse(url="/products", status_code=302)


@router.post("/{product_id}/restock")
async def restock_product(product_id: int, quantity: int = Form(...), session: str = Depends(verify_session)):
    if not session:
        return RedirectResponse(url="/login")

    async with aiosqlite.connect(DATABASE_URL) as db:
        await db.execute(
            "UPDATE products SET stock = stock + ? WHERE id = ?", (quantity, product_id)
        )
        await db.commit()

    return RedirectResponse(url="/products", status_code=302)
