"""CRUD-функції для роботи з БД. Кожна функція отримує відкрите з'єднання."""
import aiosqlite
from typing import Optional


# ---------------------------------------------------------------------------
# Клієнти
# ---------------------------------------------------------------------------

async def get_or_create_client(db: aiosqlite.Connection, telegram_id: int) -> dict:
    """Повертає клієнта або створює новий запис."""
    async with db.execute(
        "SELECT * FROM clients WHERE telegram_id = ?", (telegram_id,)
    ) as cur:
        row = await cur.fetchone()
    if row:
        return dict(row)
    await db.execute(
        "INSERT INTO clients (telegram_id) VALUES (?)", (telegram_id,)
    )
    await db.commit()
    return {"telegram_id": telegram_id, "consent_given": 0}


async def set_consent(db: aiosqlite.Connection, telegram_id: int) -> None:
    """Відмічає згоду клієнта на обробку персональних даних."""
    await db.execute(
        "UPDATE clients SET consent_given = 1 WHERE telegram_id = ?", (telegram_id,)
    )
    await db.commit()


async def has_consent(db: aiosqlite.Connection, telegram_id: int) -> bool:
    async with db.execute(
        "SELECT consent_given FROM clients WHERE telegram_id = ?", (telegram_id,)
    ) as cur:
        row = await cur.fetchone()
    return bool(row and row["consent_given"])


# ---------------------------------------------------------------------------
# Каталог — послуги
# ---------------------------------------------------------------------------

async def get_services(db: aiosqlite.Connection) -> list[dict]:
    async with db.execute(
        "SELECT * FROM services WHERE is_active = 1 ORDER BY id"
    ) as cur:
        return [dict(r) for r in await cur.fetchall()]


async def get_service(db: aiosqlite.Connection, service_id: int) -> Optional[dict]:
    async with db.execute(
        "SELECT * FROM services WHERE id = ? AND is_active = 1", (service_id,)
    ) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Каталог — категорії та товари
# ---------------------------------------------------------------------------

async def get_categories(db: aiosqlite.Connection) -> list[dict]:
    async with db.execute("SELECT * FROM categories ORDER BY id") as cur:
        return [dict(r) for r in await cur.fetchall()]


async def get_products_by_category(
    db: aiosqlite.Connection, category_id: int
) -> list[dict]:
    async with db.execute(
        "SELECT * FROM products WHERE category_id = ? AND is_active = 1 ORDER BY id",
        (category_id,),
    ) as cur:
        return [dict(r) for r in await cur.fetchall()]


async def get_product(db: aiosqlite.Connection, product_id: int) -> Optional[dict]:
    async with db.execute(
        "SELECT * FROM products WHERE id = ? AND is_active = 1", (product_id,)
    ) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Каталог — пакети
# ---------------------------------------------------------------------------

async def get_packages(db: aiosqlite.Connection) -> list[dict]:
    async with db.execute(
        "SELECT * FROM packages WHERE is_active = 1 ORDER BY price"
    ) as cur:
        return [dict(r) for r in await cur.fetchall()]


async def get_package(db: aiosqlite.Connection, package_id: int) -> Optional[dict]:
    async with db.execute(
        "SELECT * FROM packages WHERE id = ? AND is_active = 1", (package_id,)
    ) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Замовлення
# ---------------------------------------------------------------------------

async def create_order(
    db: aiosqlite.Connection,
    *,
    client_id: int,
    client_name: str,
    client_phone: str,
    client_city: str,
    service_id: Optional[int] = None,
    product_id: Optional[int] = None,
    package_id: Optional[int] = None,
) -> int:
    """Створює нову заявку і повертає її ID."""
    async with db.execute(
        """
        INSERT INTO orders
            (client_id, client_name, client_phone, client_city,
             service_id, product_id, package_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (client_id, client_name, client_phone, client_city,
         service_id, product_id, package_id),
    ) as cur:
        order_id = cur.lastrowid
    await db.commit()
    return order_id


async def get_order(db: aiosqlite.Connection, order_id: int) -> Optional[dict]:
    async with db.execute(
        "SELECT * FROM orders WHERE id = ?", (order_id,)
    ) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


async def get_client_orders(
    db: aiosqlite.Connection, telegram_id: int
) -> list[dict]:
    async with db.execute(
        "SELECT * FROM orders WHERE client_id = ? ORDER BY created_at DESC",
        (telegram_id,),
    ) as cur:
        return [dict(r) for r in await cur.fetchall()]


async def cancel_order(
    db: aiosqlite.Connection, order_id: int, client_id: int
) -> bool:
    """Скасовує заявку. Повертає True якщо скасування вдалося."""
    async with db.execute(
        "SELECT status FROM orders WHERE id = ? AND client_id = ?",
        (order_id, client_id),
    ) as cur:
        row = await cur.fetchone()
    if not row or row["status"] not in ("pending", "confirmed"):
        return False
    await db.execute(
        "UPDATE orders SET status = 'cancelled', updated_at = datetime('now') WHERE id = ?",
        (order_id,),
    )
    await _log_status_change(db, order_id, row["status"], "cancelled")
    await db.commit()
    return True


async def update_order_status(
    db: aiosqlite.Connection,
    order_id: int,
    new_status: str,
    changed_by: Optional[int] = None,
    note: Optional[str] = None,
) -> Optional[str]:
    """Оновлює статус заявки. Повертає старий статус або None якщо не знайдено."""
    async with db.execute(
        "SELECT status FROM orders WHERE id = ?", (order_id,)
    ) as cur:
        row = await cur.fetchone()
    if not row:
        return None
    old_status = row["status"]
    await db.execute(
        "UPDATE orders SET status = ?, updated_at = datetime('now') WHERE id = ?",
        (new_status, order_id),
    )
    await _log_status_change(db, order_id, old_status, new_status, changed_by, note)
    await db.commit()
    return old_status


async def _log_status_change(
    db: aiosqlite.Connection,
    order_id: int,
    old_status: Optional[str],
    new_status: str,
    changed_by: Optional[int] = None,
    note: Optional[str] = None,
) -> None:
    await db.execute(
        """
        INSERT INTO order_status_log (order_id, old_status, new_status, changed_by, note)
        VALUES (?, ?, ?, ?, ?)
        """,
        (order_id, old_status, new_status, changed_by, note),
    )
