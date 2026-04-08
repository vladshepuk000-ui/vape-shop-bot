"""Ініціалізація бази даних та хелпери для виконання запитів."""
import aiosqlite
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from config import settings

# Одне спільне з'єднання на весь процес (singleton)
_db_connection: Optional[aiosqlite.Connection] = None


async def get_db() -> aiosqlite.Connection:
    global _db_connection
    if _db_connection is None:
        _db_connection = await aiosqlite.connect(settings.DB_NAME)
        _db_connection.row_factory = aiosqlite.Row
        await _db_connection.execute("PRAGMA foreign_keys = ON")
    return _db_connection


@asynccontextmanager
async def get_connection() -> AsyncGenerator[aiosqlite.Connection, None]:
    """Async context manager для роботи з БД.

    Використання:
        async with get_connection() as db:
            await models.some_function(db, ...)
    """
    db = await get_db()
    yield db


# ---------------------------------------------------------------------------
# Схема БД
# ---------------------------------------------------------------------------

_SCHEMA = """
-- Клієнти
CREATE TABLE IF NOT EXISTS clients (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id   INTEGER UNIQUE NOT NULL,
    consent_given INTEGER NOT NULL DEFAULT 0,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Послуги агентства
CREATE TABLE IF NOT EXISTS services (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    description TEXT    NOT NULL DEFAULT '',
    price       REAL    NOT NULL DEFAULT 0,
    is_active   INTEGER NOT NULL DEFAULT 1
);

-- Категорії товарів
CREATE TABLE IF NOT EXISTS categories (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT    NOT NULL UNIQUE
);

-- Товари каталогу
CREATE TABLE IF NOT EXISTS products (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id   INTEGER NOT NULL REFERENCES categories(id),
    name          TEXT    NOT NULL,
    description   TEXT    NOT NULL DEFAULT '',
    price         REAL    NOT NULL DEFAULT 0,
    is_custom     INTEGER NOT NULL DEFAULT 0,
    lead_days     INTEGER,
    photo_file_id TEXT,
    is_active     INTEGER NOT NULL DEFAULT 1
);

-- Готові пакети
CREATE TABLE IF NOT EXISTS packages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    description TEXT    NOT NULL DEFAULT '',
    price       REAL    NOT NULL DEFAULT 0,
    is_active   INTEGER NOT NULL DEFAULT 1
);

-- Заявки
CREATE TABLE IF NOT EXISTS orders (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id    INTEGER NOT NULL,
    client_name  TEXT    NOT NULL,
    client_phone TEXT    NOT NULL,
    client_city  TEXT    NOT NULL,
    service_id   INTEGER,
    product_id   INTEGER,
    package_id   INTEGER,
    status       TEXT    NOT NULL DEFAULT 'pending',
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Лог зміни статусів
CREATE TABLE IF NOT EXISTS order_status_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id   INTEGER NOT NULL REFERENCES orders(id),
    old_status TEXT,
    new_status TEXT    NOT NULL,
    changed_by INTEGER,
    note       TEXT,
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

# Міграції: додаємо колонки, яких може не бути в існуючій БД
_MIGRATIONS = [
    # orders
    ("orders", "client_name",  "TEXT NOT NULL DEFAULT ''"),
    ("orders", "client_phone", "TEXT NOT NULL DEFAULT ''"),
    ("orders", "client_city",  "TEXT NOT NULL DEFAULT ''"),
    ("orders", "service_id",   "INTEGER"),
    ("orders", "product_id",   "INTEGER"),
    ("orders", "package_id",   "INTEGER"),
    ("orders", "updated_at",   "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
    # clients
    ("clients", "consent_given", "INTEGER NOT NULL DEFAULT 0"),
    # services / packages
    ("services", "is_active", "INTEGER NOT NULL DEFAULT 1"),
    ("packages", "is_active", "INTEGER NOT NULL DEFAULT 1"),
]

_SEED = [
    ("INSERT OR IGNORE INTO services (id, name, description, price) "
     "VALUES (1, 'Організація похорону', 'Повний комплекс ритуальних послуг', 15000)"),
    ("INSERT OR IGNORE INTO services (id, name, description, price) "
     "VALUES (2, 'Кремація', 'Послуга кремації з урною', 8000)"),
    ("INSERT OR IGNORE INTO services (id, name, description, price) "
     "VALUES (3, 'Транспортування', 'Транспортування по місту та регіону', 2500)"),
    ("INSERT OR IGNORE INTO packages (id, name, description, price) "
     "VALUES (1, 'Економ', 'Базовий набір послуг та товарів', 12000)"),
    ("INSERT OR IGNORE INTO packages (id, name, description, price) "
     "VALUES (2, 'Стандарт', 'Стандартний пакет з розширеним асортиментом', 22000)"),
    ("INSERT OR IGNORE INTO packages (id, name, description, price) "
     "VALUES (3, 'Преміум', 'Повний пакет преміум-класу', 40000)"),
]


async def _add_column_if_missing(
    db: aiosqlite.Connection, table: str, column: str, definition: str
) -> None:
    """Додає колонку, якщо вона ще не існує (ігнорує помилку якщо є)."""
    try:
        await db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    except Exception:
        pass  # колонка вже є — нічого не робимо


async def init_db() -> None:
    """Створює таблиці, запускає міграції, додає тестові дані."""
    db = await get_db()

    # Створюємо таблиці
    await db.executescript(_SCHEMA)

    # Міграції для існуючих БД
    for table, column, definition in _MIGRATIONS:
        await _add_column_if_missing(db, table, column, definition)

    # Тестові дані (лише якщо таблиці порожні)
    for sql in _SEED:
        await db.execute(sql)

    await db.commit()
