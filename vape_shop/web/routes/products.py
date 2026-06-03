import os
import aiohttp
import asyncpg
from fastapi import APIRouter, Request, Depends, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from web.auth_utils import verify_session

BASE_DIR = os.path.join(os.path.dirname(__file__), "..", "templates")
templates = Jinja2Templates(directory=BASE_DIR)
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:jHInKjjHzgONUJeWLNNkoxIumLhqIjIs@tramway.proxy.rlwy.net:56512/railway"
)
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
_admin_ids_raw = os.getenv("ADMIN_IDS", os.getenv("ADMIN_TG_ID", ""))
ADMIN_TG_ID = _admin_ids_raw.split(",")[0].strip() if _admin_ids_raw else ""

CATEGORIES = {
    "liquids":    "Рідини",
    "cartridges": "Картриджі",
    "systems":    "Системи (поди)",
}

router = APIRouter(prefix="/products")


async def upload_photo_to_telegram(photo_bytes: bytes, filename: str) -> tuple[str | None, str | None]:
    """Upload photo to admin chat, get file_id. Returns (file_id, error)."""
    if not BOT_TOKEN:
        return None, "BOT_TOKEN не налаштований"
    if not ADMIN_TG_ID:
        return None, "ADMIN_TG_ID не налаштований"
    try:
        form = aiohttp.FormData()
        form.add_field("chat_id", ADMIN_TG_ID)
        form.add_field("photo", photo_bytes, filename=filename, content_type="image/jpeg")
        async with aiohttp.ClientSession() as http:
            async with http.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto", data=form
            ) as resp:
                data = await resp.json()
            if not data.get("ok"):
                return None, data.get("description", "Telegram error")
            file_id = data["result"]["photo"][-1]["file_id"]
            message_id = data["result"]["message_id"]
            try:
                async with http.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/deleteMessage",
                    json={"chat_id": ADMIN_TG_ID, "message_id": message_id},
                ) as _:
                    pass
            except Exception:
                pass
        return file_id, None
    except Exception as e:
        return None, str(e)


@router.get("", response_class=HTMLResponse)
async def products_list(request: Request, session: str = Depends(verify_session)):
    if not session:
        return RedirectResponse(url="/login")

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        products = await conn.fetch(
            "SELECT * FROM products ORDER BY is_active DESC, category, name"
        )
    finally:
        await conn.close()

    return templates.TemplateResponse(request, "products.html", {
        "products": products,
        "categories": CATEGORIES,
    })


@router.post("/upload-photo", response_class=JSONResponse)
async def upload_photo(
    photo: UploadFile = File(...),
    session: str = Depends(verify_session),
):
    if not session:
        return JSONResponse({"error": "Не авторизований"}, status_code=401)
    photo_bytes = await photo.read()
    file_id, error = await upload_photo_to_telegram(photo_bytes, photo.filename)
    if error:
        return JSONResponse({"error": error})
    return JSONResponse({"file_id": file_id})


@router.post("/add")
async def add_product(
    name: str = Form(...),
    brand: str = Form(""),
    description: str = Form(""),
    category: str = Form("liquids"),
    price: float = Form(...),
    old_price: str = Form(""),
    stock: int = Form(...),
    photo_id: str = Form(""),
    session: str = Depends(verify_session),
):
    if not session:
        return RedirectResponse(url="/login")

    try:
        old_price_val = float(old_price) if old_price.strip() else None
    except ValueError:
        old_price_val = None

    brand_val = brand.strip() if brand.strip() else None
    photo_id_val = photo_id.strip() if photo_id.strip() else None

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.execute(
            """INSERT INTO products (name, brand, description, category, price, old_price, stock, photo_id, is_active)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, TRUE)""",
            name, brand_val, description, category, price, old_price_val, stock, photo_id_val
        )
    finally:
        await conn.close()

    return RedirectResponse(url="/products", status_code=302)


@router.post("/{product_id}/edit")
async def edit_product(
    product_id: int,
    name: str = Form(...),
    brand: str = Form(""),
    description: str = Form(""),
    price: float = Form(...),
    stock: int = Form(...),
    old_price: str = Form(""),
    is_new: str = Form(""),
    is_hit: str = Form(""),
    photo_id: str = Form(""),
    session: str = Depends(verify_session),
):
    if not session:
        return RedirectResponse(url="/login")

    try:
        old_price_val = float(old_price) if old_price.strip() else None
    except ValueError:
        old_price_val = None

    brand_val = brand.strip() if brand.strip() else None
    photo_id_val = photo_id.strip() if photo_id.strip() else None

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        if photo_id_val:
            await conn.execute(
                """UPDATE products SET name=$1, brand=$2, description=$3, price=$4, stock=$5,
                   old_price=$6, is_new=$7, is_hit=$8, photo_id=$9 WHERE id=$10""",
                name, brand_val, description, price, stock, old_price_val,
                1 if is_new else 0, 1 if is_hit else 0, photo_id_val, product_id
            )
        else:
            await conn.execute(
                """UPDATE products SET name=$1, brand=$2, description=$3, price=$4, stock=$5,
                   old_price=$6, is_new=$7, is_hit=$8 WHERE id=$9""",
                name, brand_val, description, price, stock, old_price_val,
                1 if is_new else 0, 1 if is_hit else 0, product_id
            )
    finally:
        await conn.close()

    return RedirectResponse(url="/products", status_code=302)


@router.post("/{product_id}/toggle")
async def toggle_product(product_id: int, session: str = Depends(verify_session)):
    if not session:
        return RedirectResponse(url="/login")

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.execute(
            "UPDATE products SET is_active = NOT is_active WHERE id = $1", product_id
        )
    finally:
        await conn.close()

    return RedirectResponse(url="/products", status_code=302)


@router.post("/{product_id}/restock")
async def restock_product(product_id: int, quantity: int = Form(...), session: str = Depends(verify_session)):
    if not session:
        return RedirectResponse(url="/login")

    product = None
    waitlist = []
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.execute(
            "UPDATE products SET stock = stock + $1 WHERE id = $2", quantity, product_id
        )
        product = await conn.fetchrow("SELECT name FROM products WHERE id = $1", product_id)
        waitlist = await conn.fetch("""
            SELECT c.telegram_id FROM waitlist w
            JOIN customers c ON w.customer_id = c.id
            WHERE w.product_id = $1
        """, product_id)
        if waitlist:
            await conn.execute("DELETE FROM waitlist WHERE product_id = $1", product_id)
    finally:
        await conn.close()

    if waitlist and BOT_TOKEN and product:
        async with aiohttp.ClientSession() as http:
            for row in waitlist:
                try:
                    async with http.post(
                        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                        json={
                            "chat_id": row["telegram_id"],
                            "text": f"🔔 Товар <b>{product['name']}</b> знову є в наявності!\nПоспішай замовити 👉 /start",
                            "parse_mode": "HTML",
                        }
                    ) as _:
                        pass
                except Exception:
                    pass

    return RedirectResponse(url="/products", status_code=302)
