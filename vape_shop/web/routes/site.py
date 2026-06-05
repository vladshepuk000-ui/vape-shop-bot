import os
import json
import uuid
import asyncpg
import aiohttp
import logging
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

logger = logging.getLogger(__name__)

BASE_DIR = os.path.join(os.path.dirname(__file__), "..", "templates")
templates = Jinja2Templates(directory=BASE_DIR)
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:jHInKjjHzgONUJeWLNNkoxIumLhqIjIs@tramway.proxy.rlwy.net:56512/railway"
)

router = APIRouter()

from datetime import datetime, timedelta
online_sessions: dict[str, datetime] = {}


@router.get("/site", response_class=HTMLResponse)
async def landing(request: Request):
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        reviews = await conn.fetch("""
            SELECT r.rating, r.text, r.created_at, c.username
            FROM reviews r
            LEFT JOIN customers c ON r.customer_id = c.id
            WHERE r.text IS NOT NULL AND r.text != ''
            ORDER BY r.created_at DESC
            LIMIT 6
        """)

        products_count = await conn.fetchval(
            "SELECT COUNT(*) FROM products WHERE is_active = TRUE AND stock > 0"
        )

        products = await conn.fetch("""
            SELECT id, name, category, description, price, old_price, stock, photo_id, is_new, is_hit
            FROM products WHERE is_active = TRUE
            ORDER BY category, (stock > 0) DESC, name
        """)

        customers_count = await conn.fetchval("SELECT COUNT(*) FROM customers")
    finally:
        await conn.close()

    # Рахуємо відвідування
    await increment_stat("visits")

    bot_username = os.getenv("BOT_USERNAME", "your_bot")

    return templates.TemplateResponse(request, "site.html", {
        "reviews": reviews,
        "products": products,
        "products_count": products_count,
        "customers_count": customers_count,
        "bot_username": bot_username,
        "contact_username": os.getenv("CONTACT_USERNAME", "Vlad_shepuk"),
        "contact_phone": os.getenv("CONTACT_PHONE", "+380981256254"),
        "pickup_address": os.getenv("PICKUP_ADDRESS", "Велика Михайлівка"),
    })


async def increment_stat(column: str):
    from datetime import date
    today = date.today().isoformat()
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.execute(f"""
            INSERT INTO site_stats (date, {column}) VALUES ($1, 1)
            ON CONFLICT(date) DO UPDATE SET {column} = site_stats.{column} + 1
        """, today)
    finally:
        await conn.close()


async def notify_admin(text: str):
    bot_token = os.getenv("BOT_TOKEN", "")
    admin_ids = [x for x in os.getenv("ADMIN_IDS", "").split(",") if x]
    if not bot_token or not admin_ids:
        return
    async with aiohttp.ClientSession() as session:
        for admin_id in admin_ids:
            try:
                await session.post(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage",
                    json={"chat_id": admin_id.strip(), "text": text}
                )
            except Exception as e:
                logger.error(f"Notify error: {e}")


@router.post("/api/notify-order-click")
async def notify_order_click(request: Request):
    data = await request.json()
    product_name = data.get("product", "невідомий")
    ip = request.client.host if request.client else "невідомо"
    await increment_stat("bot_clicks")
    await notify_admin(f"🛒 Клієнт натиснув 'Замовити в Telegram'\nТовар: {product_name}\nIP: {ip}")
    return JSONResponse({"ok": True})


@router.post("/api/order")
async def web_order(request: Request):
    data = await request.json()
    name = data.get("name", "")
    phone = data.get("phone", "")
    delivery = data.get("delivery", "")
    city = data.get("city", "")
    comment = data.get("comment", "")
    cart = data.get("cart", [])
    total = data.get("total", 0)

    tg = data.get("tg", "")
    delivery_str = "Нова Пошта" if delivery == "nova_poshta" else "Самовивіз"
    lines = "\n".join([f"• {i['name']} — {i['qty']} шт ({round(i['price'] * i['qty'])} грн)" for i in cart])
    city_str = f"\nМісто/відділення: {city}" if city else ""
    tg_str = f"\nTelegram: @{tg.lstrip('@')}" if tg else ""
    comment_str = f"\nКоментар: {comment}" if comment else ""

    text = (
        f"🛒 <b>Нове замовлення з сайту!</b>\n\n"
        f"👤 Ім'я: {name}\n"
        f"📞 Телефон: {phone}{tg_str}\n"
        f"🚚 Доставка: {delivery_str}{city_str}{comment_str}\n\n"
        f"<b>Товари:</b>\n{lines}\n\n"
        f"💰 <b>Разом: {total} грн</b>"
    )

    # Зберігаємо замовлення і зменшуємо залишок
    order_id = str(uuid.uuid4())[:8]
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.execute(
            "INSERT INTO web_orders (id, name, phone, cart_json) VALUES ($1, $2, $3, $4)",
            order_id, name, phone, json.dumps(cart)
        )
        for item in cart:
            await conn.execute(
                "UPDATE products SET stock = GREATEST(0, stock - $1) WHERE id = $2",
                item.get("qty", 1), item.get("id")
            )
    finally:
        await conn.close()

    bot_token = os.getenv("BOT_TOKEN", "")
    admin_ids = [x for x in os.getenv("ADMIN_IDS", "").split(",") if x]
    timeout = aiohttp.ClientTimeout(total=10)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        for admin_id in admin_ids:
            try:
                await session.post(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage",
                    json={"chat_id": admin_id.strip(), "text": text, "parse_mode": "HTML"}
                )
            except Exception as e:
                logger.error(f"Order notify error: {e}")

    return JSONResponse({"ok": True, "order_id": order_id})


@router.post("/api/order/{order_id}/cancel")
async def cancel_order(order_id: str):
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        order = await conn.fetchrow("SELECT * FROM web_orders WHERE id = $1", order_id)

        if not order or order["status"] == "cancelled":
            return JSONResponse({"ok": False, "error": "not found"}, status_code=404)

        cart = json.loads(order["cart_json"])
        await conn.execute("UPDATE web_orders SET status = 'cancelled' WHERE id = $1", order_id)
        for item in cart:
            await conn.execute(
                "UPDATE products SET stock = stock + $1 WHERE id = $2",
                item.get("qty", 1), item.get("id")
            )
    finally:
        await conn.close()

    await notify_admin(f"❌ Замовлення #{order_id} скасовано клієнтом\n👤 {order['name']}\n📞 {order['phone']}")
    return JSONResponse({"ok": True})


@router.get("/api/online-count")
async def online_count(request: Request):
    ip = request.client.host if request.client else "unknown"
    now = datetime.now()
    online_sessions[ip] = now
    cutoff = now - timedelta(minutes=5)
    for k in [k for k, v in online_sessions.items() if v < cutoff]:
        del online_sessions[k]
    return JSONResponse({"count": len(online_sessions)})


@router.get("/api/products-stock")
async def products_stock():
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        rows = await conn.fetch(
            "SELECT id, stock FROM products WHERE is_active = TRUE"
        )
    finally:
        await conn.close()
    return JSONResponse([{"id": r["id"], "stock": r["stock"]} for r in rows])


@router.get("/api/product/{product_id}")
async def product_detail(product_id: int):
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        p = await conn.fetchrow(
            "SELECT id, name, category, description, price, old_price, stock, photo_id FROM products WHERE id = $1 AND is_active = TRUE",
            product_id
        )
        if not p:
            return JSONResponse({"error": "not found"}, status_code=404)

        photo_rows = await conn.fetch(
            "SELECT photo_id FROM product_photos WHERE product_id = $1 ORDER BY position",
            product_id
        )
    finally:
        await conn.close()

    photos = [r["photo_id"] for r in photo_rows]
    if not photos and p["photo_id"]:
        photos = [p["photo_id"]]

    return JSONResponse({
        "id": p["id"], "name": p["name"], "category": p["category"],
        "description": p["description"] or "", "price": p["price"],
        "old_price": p["old_price"], "stock": p["stock"], "photos": photos,
    })


@router.get("/api/photo/{file_id:path}")
async def product_photo(file_id: str):
    bot_token = os.getenv("BOT_TOKEN", "")
    timeout = aiohttp.ClientTimeout(total=10)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(
                f"https://api.telegram.org/bot{bot_token}/getFile?file_id={file_id}"
            ) as resp:
                data = await resp.json()
            if not data.get("ok"):
                return JSONResponse({"error": "telegram error"}, status_code=404)
            file_path = data["result"]["file_path"]
            async with session.get(
                f"https://api.telegram.org/file/bot{bot_token}/{file_path}"
            ) as img_resp:
                content = await img_resp.read()
                content_type = img_resp.headers.get("Content-Type", "image/jpeg")
        return StreamingResponse(iter([content]), media_type=content_type)
    except Exception:
        return JSONResponse({"error": "photo unavailable"}, status_code=504)
