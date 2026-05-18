import logging
import os
import asyncpg
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:jHInKjjHzgONUJeWLNNkoxIumLhqIjIs@tramway.proxy.rlwy.net:56512/railway"
)


async def send_monday_broadcast(bot: Bot):
    """Авторозсилка щопонеділка — береться шаблон з БД."""
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        # Вибрати шаблон який найдавніше використовувався
        template = await conn.fetchrow("""
            SELECT * FROM broadcast_templates
            ORDER BY last_used ASC NULLS FIRST
            LIMIT 1
        """)

        if not template:
            logger.info("Авторозсилка: немає шаблонів у БД.")
            return

        # Отримати всіх підписаних клієнтів
        customers = await conn.fetch(
            "SELECT telegram_id FROM customers WHERE is_subscribed = TRUE"
        )

        sent = 0
        errors = 0
        for c in customers:
            try:
                await bot.send_message(c['telegram_id'], template['text'])
                sent += 1
            except Exception:
                errors += 1

        # Оновити статистику шаблону
        await conn.execute("""
            UPDATE broadcast_templates
            SET used_count = used_count + 1, last_used = CURRENT_TIMESTAMP
            WHERE id = $1
        """, template['id'])

        # Записати в лог розсилок
        await conn.execute(
            "INSERT INTO broadcasts (text, sent_count, error_count) VALUES ($1, $2, $3)",
            template['text'], sent, errors
        )
    finally:
        await conn.close()

    logger.info(f"Авторозсилка: надіслано {sent}, помилок {errors}")


async def send_21day_reminders(bot: Bot):
    """Нагадування клієнтам які не замовляли 21+ днів."""
    cutoff = datetime.now() - timedelta(days=18)

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        customers = await conn.fetch("""
            SELECT telegram_id, username FROM customers
            WHERE is_subscribed = TRUE
              AND last_order IS NOT NULL
              AND last_order < $1
              AND total_orders > 0
        """, cutoff)
    finally:
        await conn.close()

    sent = 0
    notified = []
    log_conn = await asyncpg.connect(DATABASE_URL)
    try:
        for c in customers:
            try:
                await bot.send_message(
                    c['telegram_id'],
                    "👋 Давно не бачились!\n\n"
                    "Завітай до нашого магазину — можливо вже є щось нове 👉 /start"
                )
                await log_conn.execute(
                    "INSERT INTO reminder_logs (telegram_id, username) VALUES ($1, $2)",
                    c['telegram_id'], c.get('username')
                )
                notified.append(c)
                sent += 1
            except Exception:
                pass
    finally:
        await log_conn.close()

    if sent:
        logger.info(f"Нагадування 18 днів: надіслано {sent} клієнтам")
        admin_ids = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x]
        usernames = [f"@{c['username']}" if c['username'] else f"id:{c['telegram_id']}" for c in notified]
        report = f"📩 Нагадування відправлено {sent} клієнтам:\n" + "\n".join(usernames)
        for admin_id in admin_ids:
            try:
                await bot.send_message(admin_id, report)
            except Exception:
                pass


async def send_weekly_report(bot: Bot):
    """Щотижневий розширений звіт адміну."""
    admin_ids = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x]
    if not admin_ids:
        return

    week_ago = datetime.now() - timedelta(days=7)
    prev_start = datetime.now() - timedelta(days=14)

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        week = await conn.fetchrow("""
            SELECT
                COUNT(*) FILTER (WHERE status != 'cancelled') as total_orders,
                COUNT(*) FILTER (WHERE status = 'cancelled') as cancelled,
                COALESCE(SUM(total_price) FILTER (WHERE status != 'cancelled'), 0) as revenue,
                COALESCE(AVG(total_price) FILTER (WHERE status != 'cancelled'), 0) as avg_order
            FROM orders WHERE created_at >= $1
        """, week_ago)

        prev = await conn.fetchrow("""
            SELECT
                COUNT(*) FILTER (WHERE status != 'cancelled') as total_orders,
                COALESCE(SUM(total_price) FILTER (WHERE status != 'cancelled'), 0) as revenue,
                COALESCE(AVG(total_price) FILTER (WHERE status != 'cancelled'), 0) as avg_order
            FROM orders WHERE created_at >= $1 AND created_at < $2
        """, prev_start, week_ago)

        top_week = await conn.fetch("""
            SELECT p.name, SUM(oi.quantity) as sold, SUM(oi.quantity * oi.price_at_order) as revenue
            FROM order_items oi
            JOIN products p ON oi.product_id = p.id
            JOIN orders o ON oi.order_id = o.id
            WHERE o.created_at >= $1 AND o.status != 'cancelled'
            GROUP BY p.name ORDER BY sold DESC LIMIT 3
        """, week_ago)

        new_customers = await conn.fetchval(
            "SELECT COUNT(*) FROM customers WHERE first_seen >= $1", week_ago)
        prev_new_customers = await conn.fetchval(
            "SELECT COUNT(*) FROM customers WHERE first_seen >= $1 AND first_seen < $2",
            prev_start, week_ago)

        repeat_orders = await conn.fetchval("""
            SELECT COUNT(DISTINCT o.customer_id) FROM orders o
            WHERE o.created_at >= $1 AND o.status != 'cancelled'
              AND (SELECT COUNT(*) FROM orders o2
                   WHERE o2.customer_id = o.customer_id
                     AND o2.created_at < $1) > 0
        """, week_ago)

        low_stock = await conn.fetch("""
            SELECT name, stock FROM products
            WHERE is_active = TRUE AND stock <= 3 ORDER BY stock
        """)
    finally:
        await conn.close()

    def diff_str(curr, prev):
        if prev == 0:
            return ""
        d = ((curr - prev) / prev) * 100
        icon = "📈" if d >= 0 else "📉"
        return f" {icon} {d:+.0f}%"

    curr_rev = float(week['revenue'])
    prev_rev = float(prev['revenue'])
    curr_orders = int(week['total_orders'])
    prev_orders = int(prev['total_orders'])
    curr_avg = float(week['avg_order'])
    prev_avg = float(prev['avg_order'])

    text = f"📊 <b>Звіт за 7 днів</b>\n{'─' * 28}\n\n"
    text += f"💰 <b>Виручка:</b> {curr_rev:.0f} грн{diff_str(curr_rev, prev_rev)}\n"
    text += f"   Минулий тиждень: {prev_rev:.0f} грн\n\n"
    text += f"🛒 <b>Замовлень:</b> {curr_orders}{diff_str(curr_orders, prev_orders)}\n"
    text += f"   Минулий тиждень: {prev_orders}\n"
    if week['cancelled']:
        text += f"   Скасовано: {week['cancelled']}\n"
    text += "\n"
    text += f"💳 <b>Середній чек:</b> {curr_avg:.0f} грн{diff_str(curr_avg, prev_avg)}\n"
    text += f"   Минулий тиждень: {prev_avg:.0f} грн\n\n"
    text += f"👤 <b>Нових клієнтів:</b> {new_customers}{diff_str(new_customers, prev_new_customers)}\n"
    if repeat_orders:
        text += f"🔄 <b>Повторних покупців:</b> {repeat_orders}\n"
    text += "\n"

    if top_week:
        text += "🏆 <b>Топ товари:</b>\n"
        for i, p in enumerate(top_week, 1):
            text += f"   {i}. {p['name']} — {p['sold']} шт ({p['revenue']:.0f} грн)\n"
        text += "\n"

    text += "🔍 <b>Аналіз:</b>\n"
    if curr_rev > prev_rev:
        text += f"   ✅ Виручка зросла на {curr_rev - prev_rev:.0f} грн\n"
    elif curr_rev < prev_rev:
        text += f"   ⚠️ Виручка впала на {prev_rev - curr_rev:.0f} грн\n"
    if new_customers > prev_new_customers:
        text += f"   ✅ Більше нових клієнтів ніж минулого тижня\n"
    elif new_customers < prev_new_customers:
        text += f"   ⚠️ Менше нових клієнтів ніж минулого тижня\n"
    if curr_avg < prev_avg:
        text += f"   ⚠️ Середній чек впав\n"
    text += "\n"

    tips = []
    if curr_rev < prev_rev and curr_orders < prev_orders:
        tips.append("Падіння — варто зробити розсилку або акцію")
    if curr_avg < prev_avg:
        tips.append("Середній чек впав — пропонуй картридж + жижа разом")
    if any(p['stock'] == 0 for p in low_stock):
        tips.append("Є товари з нульовим залишком — поповни")
    if not tips:
        tips.append("Все стабільно — продовжуй в тому ж темпі")

    text += "💡 <b>Поради:</b>\n"
    for tip in tips:
        text += f"   • {tip}\n"

    if low_stock:
        text += "\n⚠️ <b>Закінчується:</b>\n"
        for p in low_stock:
            icon = "🔴" if p['stock'] == 0 else "🟡"
            text += f"   {icon} {p['name']} — {p['stock']} шт\n"

    for admin_id in admin_ids:
        try:
            await bot.send_message(admin_id, text, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Не вдалось надіслати звіт адміну {admin_id}: {e}")


async def send_daily_site_report(bot: Bot):
    """Щоденний звіт по сайту о 23:00."""
    admin_ids = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x]
    if not admin_ids:
        return

    from datetime import date
    today = date.today().isoformat()

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        row = await conn.fetchrow(
            "SELECT visits, bot_clicks FROM site_stats WHERE date = $1", today
        )
    finally:
        await conn.close()

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

    # Нагадування 18 днів — щодня о 10:00
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
