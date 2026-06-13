import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:jHInKjjHzgONUJeWLNNkoxIumLhqIjIs@tramway.proxy.rlwy.net:56512/railway")
SHOP_ID = int(os.getenv("SHOP_ID", "1"))


async def _connect() -> asyncpg.Connection:
    return await asyncpg.connect(DATABASE_URL)


def _row_to_dict(row) -> dict:
    """Перетворює asyncpg Record у dict."""
    return dict(row) if row else None


def _rows_to_dicts(rows) -> list[dict]:
    return [dict(r) for r in rows]


# ─────────────────────────────────────────
# КЛІЄНТИ
# ─────────────────────────────────────────

async def add_customer(telegram_id: int, username: str = None) -> None:
    conn = await _connect()
    try:
        await conn.execute("""
            INSERT INTO customers (telegram_id, username, shop_id)
            VALUES ($1, $2, $3)
            ON CONFLICT(telegram_id, shop_id) DO UPDATE SET username = EXCLUDED.username
        """, telegram_id, username, SHOP_ID)
    finally:
        await conn.close()


async def get_customer(telegram_id: int) -> dict | None:
    conn = await _connect()
    try:
        row = await conn.fetchrow(
            "SELECT * FROM customers WHERE telegram_id = $1 AND shop_id = $2", telegram_id, SHOP_ID
        )
        return _row_to_dict(row)
    finally:
        await conn.close()


async def get_all_subscribed_customers() -> list[dict]:
    conn = await _connect()
    try:
        rows = await conn.fetch(
            "SELECT * FROM customers WHERE is_subscribed = TRUE AND shop_id = $1", SHOP_ID
        )
        return _rows_to_dicts(rows)
    finally:
        await conn.close()


async def set_subscribed(telegram_id: int, value: bool) -> None:
    conn = await _connect()
    try:
        await conn.execute(
            "UPDATE customers SET is_subscribed = $1 WHERE telegram_id = $2",
            value, telegram_id
        )
    finally:
        await conn.close()


# ─────────────────────────────────────────
# ТОВАРИ
# ─────────────────────────────────────────

async def get_all_products(only_active: bool = True) -> list[dict]:
    conn = await _connect()
    try:
        if only_active:
            rows = await conn.fetch(
                "SELECT * FROM products WHERE is_active = TRUE AND shop_id = $1", SHOP_ID
            )
        else:
            rows = await conn.fetch(
                "SELECT * FROM products WHERE shop_id = $1", SHOP_ID
            )
        return _rows_to_dicts(rows)
    finally:
        await conn.close()


async def get_products_by_category(category: str) -> list[dict]:
    conn = await _connect()
    try:
        rows = await conn.fetch(
            "SELECT * FROM products WHERE category = $1 AND is_active = TRUE AND shop_id = $2",
            category, SHOP_ID
        )
        return _rows_to_dicts(rows)
    finally:
        await conn.close()


async def get_product_by_id(product_id: int) -> dict | None:
    conn = await _connect()
    try:
        row = await conn.fetchrow(
            "SELECT * FROM products WHERE id = $1 AND shop_id = $2", product_id, SHOP_ID
        )
        return _row_to_dict(row)
    finally:
        await conn.close()


async def update_stock(product_id: int, new_stock: int) -> None:
    conn = await _connect()
    try:
        await conn.execute(
            "UPDATE products SET stock = $1 WHERE id = $2", new_stock, product_id
        )
    finally:
        await conn.close()


# ─────────────────────────────────────────
# РОЗСИЛКИ
# ─────────────────────────────────────────

async def get_next_broadcast_template() -> dict | None:
    """Повертає шаблон який найдавніше використовувався"""
    conn = await _connect()
    try:
        row = await conn.fetchrow("""
            SELECT * FROM broadcast_templates
            ORDER BY last_used ASC NULLS FIRST
            LIMIT 1
        """)
        return _row_to_dict(row)
    finally:
        await conn.close()


async def mark_template_used(template_id: int) -> None:
    conn = await _connect()
    try:
        await conn.execute("""
            UPDATE broadcast_templates
            SET used_count = used_count + 1,
                last_used = CURRENT_TIMESTAMP
            WHERE id = $1
        """, template_id)
    finally:
        await conn.close()


async def log_broadcast(text: str, sent: int, errors: int) -> None:
    conn = await _connect()
    try:
        await conn.execute(
            "INSERT INTO broadcasts (text, sent_count, error_count) VALUES ($1, $2, $3)",
            text, sent, errors
        )
    finally:
        await conn.close()


async def add_broadcast_template(text: str) -> None:
    conn = await _connect()
    try:
        await conn.execute(
            "INSERT INTO broadcast_templates (text) VALUES ($1)", text
        )
    finally:
        await conn.close()


async def get_waitlist_for_product(product_id: int) -> list[dict]:
    """Повертає список telegram_id клієнтів що чекають на товар"""
    conn = await _connect()
    try:
        rows = await conn.fetch("""
            SELECT c.telegram_id, w.id as waitlist_id
            FROM waitlist w
            JOIN customers c ON w.customer_id = c.id
            WHERE w.product_id = $1
        """, product_id)
        return _rows_to_dicts(rows)
    finally:
        await conn.close()


async def clear_waitlist_for_product(product_id: int) -> None:
    """Видаляє всіх з waitlist після сповіщення"""
    conn = await _connect()
    try:
        await conn.execute(
            "DELETE FROM waitlist WHERE product_id = $1", product_id
        )
    finally:
        await conn.close()
