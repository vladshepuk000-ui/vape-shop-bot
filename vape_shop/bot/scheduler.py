import logging
import os
import aiosqlite
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "vape_shop.db").replace("sqlite:///", "")


async def send_monday_broadcast(bot: Bot):
    """Авторозсилка щопонеділка — береться шаблон з БД."""
    async with aiosqlite.connect(DATABASE_URL) as db:
        db.row_factory = aiosqlite.Row

        # Вибрати шаблон який найдавніше використовувався
        async with db.execute("""
            SELECT * FROM broadcast_templates
            ORDER BY last_used ASC NULLS FIRST
            LIMIT 1
        """) as cursor:
            template = await cursor.fetchone()

        if not template:
            logger.info("Авторозсилка: немає шаблонів у БД.")
            return

        # Отримати всіх підписаних клієнтів
        async with db.execute(
            "SELECT telegram_id FROM customers WHERE is_subscribed = 1"
        ) as cursor:
            customers = await cursor.fetchall()

        sent = 0
        errors = 0
        for c in customers:
            try:
                await bot.send_message(c['telegram_id'], template['text'])
                sent += 1
            except Exception:
                errors += 1

        # Оновити статистику шаблону
        await db.execute("""
            UPDATE broadcast_templates
            SET used_count = used_count + 1, last_used = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (template['id'],))

        # Записати в лог розсилок
        await db.execute(
            "INSERT INTO broadcasts (text, sent_count, error_count) VALUES (?, ?, ?)",
            (template['text'], sent, errors)
        )
        await db.commit()

    logger.info(f"Авторозсилка: надіслано {sent}, помилок {errors}")


async def send_21day_reminders(bot: Bot):
    """Нагадування клієнтам які не замовляли 21+ днів."""
    cutoff = (datetime.now() - timedelta(days=21)).strftime("%Y-%m-%d %H:%M:%S")

    async with aiosqlite.connect(DATABASE_URL) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT telegram_id FROM customers
            WHERE is_subscribed = 1
              AND last_order IS NOT NULL
              AND last_order < ?
              AND total_orders > 0
        """, (cutoff,)) as cursor:
            customers = await cursor.fetchall()

    sent = 0
    for c in customers:
        try:
            await bot.send_message(
                c['telegram_id'],
                "👋 Давно не бачились!\n\n"
                "Завітай до нашого магазину — можливо вже є щось нове 👉 /start"
            )
            sent += 1
        except Exception:
            pass

    if sent:
        logger.info(f"Нагадування 21 день: надіслано {sent} клієнтам")


async def send_weekly_report(bot: Bot):
    """Щотижневий звіт адміну."""
    admin_ids = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x]
    if not admin_ids:
        return

    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")

    async with aiosqlite.connect(DATABASE_URL) as db:
        db.row_factory = aiosqlite.Row

        # Замовлення за тиждень
        async with db.execute("""
            SELECT COUNT(*) as cnt, COALESCE(SUM(total_price), 0) as total
            FROM orders
            WHERE created_at >= ? AND status != 'cancelled'
        """, (week_ago,)) as cursor:
            stats = await cursor.fetchone()

        # Нові клієнти за тиждень
        async with db.execute("""
            SELECT COUNT(*) as cnt FROM customers WHERE first_seen >= ?
        """, (week_ago,)) as cursor:
            new_clients = await cursor.fetchone()

        # Топ товар за тиждень
        async with db.execute("""
            SELECT p.name, SUM(oi.quantity) as sold
            FROM order_items oi
            JOIN products p ON oi.product_id = p.id
            JOIN orders o ON oi.order_id = o.id
            WHERE o.created_at >= ? AND o.status != 'cancelled'
            GROUP BY p.id
            ORDER BY sold DESC
            LIMIT 1
        """, (week_ago,)) as cursor:
            top_product = await cursor.fetchone()

    top_text = f"{top_product['name']} ({top_product['sold']} шт)" if top_product else "—"

    report = (
        f"📊 <b>Тижневий звіт</b>\n\n"
        f"Замовлень: {stats['cnt']}\n"
        f"Сума: {stats['total']:.0f} грн\n"
        f"Нових клієнтів: {new_clients['cnt']}\n"
        f"Топ товар: {top_text}"
    )

    for admin_id in admin_ids:
        try:
            await bot.send_message(admin_id, report)
        except Exception as e:
            logger.error(f"Не вдалось надіслати звіт адміну {admin_id}: {e}")


async def send_daily_site_report(bot: Bot):
    """Щоденний звіт по сайту о 23:00."""
    admin_ids = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x]
    if not admin_ids:
        return

    from datetime import date
    today = date.today().isoformat()

    async with aiosqlite.connect(DATABASE_URL) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT visits, bot_clicks FROM site_stats WHERE date = ?", (today,)
        ) as cursor:
            row = await cursor.fetchone()

    visits = row["visits"] if row else 0
    bot_clicks = row["bot_clicks"] if row else 0

    report = (
        f"🌐 <b>Звіт по сайту за сьогодні</b>\n\n"
        f"👁 Відвідувань: <b>{visits}</b>\n"
        f"🛒 Перейшли в бот: <b>{bot_clicks}</b>"
    )

    for admin_id in admin_ids:
        try:
            await bot.send_message(admin_id, report, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Помилка надсилання звіту: {e}")


def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="Europe/Kiev")

    # Авторозсилка — щопонеділка о 12:00
    scheduler.add_job(
        send_monday_broadcast,
        trigger="cron",
        day_of_week="mon",
        hour=12,
        minute=0,
        args=[bot],
        id="monday_broadcast"
    )

    # Нагадування 21 день — щодня о 10:00
    scheduler.add_job(
        send_21day_reminders,
        trigger="cron",
        hour=10,
        minute=0,
        args=[bot],
        id="reminders_21day"
    )

    # Тижневий звіт — щонеділі о 20:00
    scheduler.add_job(
        send_weekly_report,
        trigger="cron",
        day_of_week="sun",
        hour=20,
        minute=0,
        args=[bot],
        id="weekly_report"
    )

    # Щоденний звіт по сайту — о 23:00
    scheduler.add_job(
        send_daily_site_report,
        trigger="cron",
        hour=23,
        minute=0,
        args=[bot],
        id="daily_site_report"
    )

    return scheduler
