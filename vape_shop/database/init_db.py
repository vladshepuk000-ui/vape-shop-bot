import asyncpg
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:jHInKjjHzgONUJeWLNNkoxIumLhqIjIs@tramway.proxy.rlwy.net:56512/railway")


async def create_tables():
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        # Товари
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id          SERIAL PRIMARY KEY,
                name        TEXT NOT NULL,
                category    TEXT NOT NULL,
                description TEXT,
                price       REAL NOT NULL,
                stock       INTEGER DEFAULT 0,
                photo_id    TEXT,
                photo_url   TEXT,
                is_active   BOOLEAN DEFAULT TRUE,
                created_at  TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Клієнти
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS customers (
                id            SERIAL PRIMARY KEY,
                telegram_id   BIGINT UNIQUE NOT NULL,
                username      TEXT,
                phone         TEXT,
                is_subscribed BOOLEAN DEFAULT TRUE,
                first_seen    TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                last_order    TIMESTAMPTZ,
                total_orders  INTEGER DEFAULT 0
            )
        """)

        # Замовлення
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id          SERIAL PRIMARY KEY,
                customer_id INTEGER REFERENCES customers(id),
                address     TEXT,
                phone       TEXT,
                notes       TEXT,
                total_price REAL,
                status      TEXT DEFAULT 'new',
                created_at  TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Позиції замовлення
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS order_items (
                id             SERIAL PRIMARY KEY,
                order_id       INTEGER REFERENCES orders(id),
                product_id     INTEGER REFERENCES products(id),
                quantity       INTEGER NOT NULL,
                price_at_order REAL NOT NULL
            )
        """)

        # Фото товарів (кілька фото на товар)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS product_photos (
                id         SERIAL PRIMARY KEY,
                product_id INTEGER REFERENCES products(id),
                photo_id   TEXT NOT NULL,
                position   INTEGER DEFAULT 0
            )
        """)

        # Список очікування товару
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS waitlist (
                id          SERIAL PRIMARY KEY,
                customer_id INTEGER REFERENCES customers(id),
                product_id  INTEGER REFERENCES products(id),
                created_at  TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Відгуки
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS reviews (
                id          SERIAL PRIMARY KEY,
                customer_id INTEGER REFERENCES customers(id),
                order_id    INTEGER REFERENCES orders(id),
                rating      INTEGER NOT NULL,
                text        TEXT,
                created_at  TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Шаблони авторозсилок
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS broadcast_templates (
                id         SERIAL PRIMARY KEY,
                text       TEXT NOT NULL,
                used_count INTEGER DEFAULT 0,
                last_used  TIMESTAMPTZ
            )
        """)

        # Логування розсилок
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS broadcasts (
                id          SERIAL PRIMARY KEY,
                text        TEXT NOT NULL,
                sent_count  INTEGER DEFAULT 0,
                error_count INTEGER DEFAULT 0,
                created_at  TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Контекст AI розмов
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS ai_chat_history (
                id          SERIAL PRIMARY KEY,
                customer_id INTEGER REFERENCES customers(id),
                role        TEXT NOT NULL,
                content     TEXT NOT NULL,
                created_at  TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Лічильник AI запитів
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS ai_usage (
                id          SERIAL PRIMARY KEY,
                customer_id INTEGER REFERENCES customers(id),
                date        DATE NOT NULL,
                count       INTEGER DEFAULT 0,
                UNIQUE(customer_id, date)
            )
        """)

        # Лог нагадувань клієнтам
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS reminder_logs (
                id          SERIAL PRIMARY KEY,
                telegram_id BIGINT NOT NULL,
                username    TEXT,
                sent_at     TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Статистика сайту
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS site_stats (
                date      TEXT PRIMARY KEY,
                visits    INTEGER DEFAULT 0,
                bot_clicks INTEGER DEFAULT 0
            )
        """)

        # Замовлення з сайту
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS web_orders (
                id         TEXT PRIMARY KEY,
                name       TEXT,
                phone      TEXT,
                cart_json  TEXT,
                status     TEXT DEFAULT 'new',
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Власники магазинів (для SaaS / email-входу)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS shop_owners (
                id         SERIAL PRIMARY KEY,
                email      VARCHAR(255) UNIQUE NOT NULL,
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # OTP-коди для входу через email
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS otp_codes (
                id         SERIAL PRIMARY KEY,
                email      VARCHAR(255) NOT NULL,
                code       VARCHAR(6) NOT NULL,
                expires_at TIMESTAMPTZ NOT NULL,
                used       BOOLEAN DEFAULT FALSE
            )
        """)

        # Сесії (замість статичного токена)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                token         VARCHAR(64) PRIMARY KEY,
                shop_owner_id INTEGER REFERENCES shop_owners(id),
                expires_at    TIMESTAMPTZ NOT NULL
            )
        """)

        # Додаткові колонки до products (якщо ще не існують)
        for col_sql in [
            "ALTER TABLE products ADD COLUMN IF NOT EXISTS old_price REAL DEFAULT NULL",
            "ALTER TABLE products ADD COLUMN IF NOT EXISTS is_new INTEGER DEFAULT 0",
            "ALTER TABLE products ADD COLUMN IF NOT EXISTS is_hit INTEGER DEFAULT 0",
            "ALTER TABLE products ADD COLUMN IF NOT EXISTS brand TEXT DEFAULT NULL",
        ]:
            await conn.execute(col_sql)

        # Мультитенантність — shop_id до всіх таблиць
        for col_sql in [
            "ALTER TABLE products ADD COLUMN IF NOT EXISTS shop_id INTEGER DEFAULT 1",
            "ALTER TABLE orders ADD COLUMN IF NOT EXISTS shop_id INTEGER DEFAULT 1",
            "ALTER TABLE broadcasts ADD COLUMN IF NOT EXISTS shop_id INTEGER DEFAULT 1",
            "ALTER TABLE broadcast_templates ADD COLUMN IF NOT EXISTS shop_id INTEGER DEFAULT 1",
            "ALTER TABLE web_orders ADD COLUMN IF NOT EXISTS shop_id TEXT DEFAULT '1'",
            "ALTER TABLE customers ADD COLUMN IF NOT EXISTS shop_id INTEGER DEFAULT 1",
        ]:
            await conn.execute(col_sql)

        # Міняємо унікальний ключ customers: telegram_id → (telegram_id, shop_id)
        await conn.execute("""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM pg_constraint
                    WHERE conname = 'customers_telegram_id_key'
                ) THEN
                    ALTER TABLE customers DROP CONSTRAINT customers_telegram_id_key;
                    ALTER TABLE customers ADD CONSTRAINT customers_telegram_id_shop_id_key
                        UNIQUE(telegram_id, shop_id);
                END IF;
            END$$;
        """)

        print("OK: Всі таблиці створено успішно")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(create_tables())
