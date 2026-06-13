import os
import asyncpg
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from web.auth_utils import get_current_shop_id

BASE_DIR = os.path.join(os.path.dirname(__file__), "..", "templates")
templates = Jinja2Templates(directory=BASE_DIR)
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:jHInKjjHzgONUJeWLNNkoxIumLhqIjIs@tramway.proxy.rlwy.net:56512/railway"
)

STATUS_MAP = {
    "awaiting_payment": "Очікує оплати",
    "new":              "Нове",
    "confirmed":        "Підтверджено",
    "sent":             "Відправлено",
    "done":             "Виконано",
    "cancelled":        "Скасовано",
}

router = APIRouter(prefix="/orders")


@router.get("", response_class=HTMLResponse)
async def orders_list(request: Request, status: str = "", shop_id: int = Depends(get_current_shop_id)):
    if not shop_id:
        return RedirectResponse(url="/login")

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        if status and status in STATUS_MAP:
            orders = await conn.fetch("""
                SELECT o.id, o.status, o.total_price, o.created_at, o.address, o.phone,
                       c.username, c.telegram_id
                FROM orders o LEFT JOIN customers c ON o.customer_id = c.id
                WHERE o.status = $1 AND o.shop_id = $2
                ORDER BY o.created_at DESC
            """, status, shop_id)
        else:
            orders = await conn.fetch("""
                SELECT o.id, o.status, o.total_price, o.created_at, o.address, o.phone,
                       c.username, c.telegram_id
                FROM orders o LEFT JOIN customers c ON o.customer_id = c.id
                WHERE o.shop_id = $1
                ORDER BY o.created_at DESC
            """, shop_id)
    finally:
        await conn.close()

    return templates.TemplateResponse(request, "orders.html", {
        "orders": orders,
        "status_map": STATUS_MAP,
        "current_status": status,
    })


@router.get("/{order_id}", response_class=HTMLResponse)
async def order_detail(request: Request, order_id: int, shop_id: int = Depends(get_current_shop_id)):
    if not shop_id:
        return RedirectResponse(url="/login")

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        order = await conn.fetchrow("""
            SELECT o.*, c.username, c.telegram_id, c.phone as customer_phone
            FROM orders o LEFT JOIN customers c ON o.customer_id = c.id
            WHERE o.id = $1 AND o.shop_id = $2
        """, order_id, shop_id)

        if not order:
            return RedirectResponse(url="/orders")

        items = await conn.fetch("""
            SELECT oi.quantity, oi.price_at_order, p.name
            FROM order_items oi LEFT JOIN products p ON oi.product_id = p.id
            WHERE oi.order_id = $1
        """, order_id)
    finally:
        await conn.close()

    return templates.TemplateResponse(request, "order_detail.html", {
        "order": order,
        "items": items,
        "status_map": STATUS_MAP,
    })


@router.post("/{order_id}/status")
async def update_status(
    order_id: int,
    new_status: str = Form(...),
    shop_id: int = Depends(get_current_shop_id),
):
    if not shop_id:
        return RedirectResponse(url="/login")

    if new_status not in STATUS_MAP:
        return RedirectResponse(url=f"/orders/{order_id}")

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.execute(
            "UPDATE orders SET status = $1 WHERE id = $2 AND shop_id = $3",
            new_status, order_id, shop_id
        )
    finally:
        await conn.close()

    return RedirectResponse(url=f"/orders/{order_id}", status_code=302)
