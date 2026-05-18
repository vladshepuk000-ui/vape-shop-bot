import os
import logging
import asyncpg
from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database.queries import get_waitlist_for_product, clear_waitlist_for_product
from bot.handlers.review import send_review_request

router = Router()
logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:jHInKjjHzgONUJeWLNNkoxIumLhqIjIs@tramway.proxy.rlwy.net:56512/railway"
)
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x]

STATUS_MAP = {
    "awaiting_payment": "⏳ Очікує оплати",
    "new":              "🆕 Нове",
    "confirmed":        "✅ Підтверджено",
    "sent":             "🚚 Відправлено",
    "done":             "✔️ Виконано",
    "cancelled":        "❌ Скасовано",
}


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


# ── FSM для додавання товару ──
class AddProduct(StatesGroup):
    name        = State()
    category    = State()
    description = State()
    price       = State()
    stock       = State()
    photo       = State()


# ── /orders — список останніх замовлень ──
@router.message(Command("orders"))
async def cmd_orders(message: Message):
    if not is_admin(message.from_user.id):
        return

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        rows = await conn.fetch("""
            SELECT o.id, o.status, o.total_price, o.created_at,
                   c.telegram_id, c.username,
                   p.name as product_name, oi.quantity
            FROM orders o
            LEFT JOIN customers c ON o.customer_id = c.id
            LEFT JOIN order_items oi ON oi.order_id = o.id
            LEFT JOIN products p ON oi.product_id = p.id
            ORDER BY o.created_at DESC
            LIMIT 10
        """)
    finally:
        await conn.close()

    if not rows:
        await message.answer("Замовлень ще немає.")
        return

    # Групуємо по order_id щоб не дублювати при кількох товарах
    seen = {}
    for r in rows:
        oid = r['id']
        if oid not in seen:
            seen[oid] = dict(r)
            seen[oid]['items'] = []
        if r['product_name']:
            seen[oid]['items'].append(f"{r['product_name']} x{r['quantity']}")

    text = "📋 <b>Останні замовлення:</b>\n\n"
    for r in seen.values():
        status = STATUS_MAP.get(r['status'], r['status'])
        username = f"@{r['username']}" if r['username'] else f"id:{r['telegram_id']}"
        items_str = ", ".join(r['items']) if r['items'] else "—"
        text += (
            f"#{r['id']} | {status}\n"
            f"{items_str} — {r['total_price']} грн\n"
            f"Клієнт: {username}\n"
            f"Дата: {str(r['created_at'])[:16]}\n\n"
        )

    await message.answer(text)


# ── /setstatus — змінити статус замовлення ──
@router.message(Command("setstatus"))
async def cmd_setstatus(message: Message):
    if not is_admin(message.from_user.id):
        return

    args = message.text.split()
    if len(args) != 3 or args[2] not in STATUS_MAP:
        statuses = " | ".join(STATUS_MAP.keys())
        await message.answer(
            f"Формат: /setstatus [id] [статус]\n"
            f"Статуси: {statuses}\n\n"
            f"Приклад: /setstatus 5 sent"
        )
        return

    order_id = int(args[1])
    new_status = args[2]

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        order = await conn.fetchrow(
            "SELECT o.*, c.telegram_id FROM orders o LEFT JOIN customers c ON o.customer_id = c.id WHERE o.id = $1",
            order_id
        )

        if not order:
            await message.answer(f"Замовлення #{order_id} не знайдено.")
            return

        await conn.execute(
            "UPDATE orders SET status = $1 WHERE id = $2",
            new_status, order_id
        )
    finally:
        await conn.close()

    status_text = STATUS_MAP[new_status]
    await message.answer(f"✅ Замовлення #{order_id} → {status_text}")

    # Повідомити клієнта
    if order['telegram_id']:
        try:
            await message.bot.send_message(
                order['telegram_id'],
                f"📦 Статус вашого замовлення #{order_id} змінено:\n"
                f"{status_text}"
            )
        except Exception as e:
            logger.error(f"Не вдалось надіслати клієнту: {e}")

        # Запит відгуку при статусі "done"
        if new_status == "done":
            try:
                review_text, review_kb = send_review_request(order_id)
                await message.bot.send_message(
                    order['telegram_id'],
                    review_text,
                    reply_markup=review_kb
                )
            except Exception as e:
                logger.error(f"Не вдалось надіслати запит відгуку: {e}")


# ── /addproduct — додати товар ──
@router.message(Command("addproduct"))
async def cmd_addproduct(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    await state.set_state(AddProduct.name)
    await message.answer(
        "Додавання нового товару.\n\n"
        "Введи назву товару:\n"
        "(або /cancel щоб скасувати)"
    )


@router.message(AddProduct.name)
async def add_name(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("Введи назву товару текстом:")
        return
    await state.update_data(name=message.text.strip())
    await state.set_state(AddProduct.category)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Рідини",         callback_data="addcat_liquids")],
        [InlineKeyboardButton(text="Картриджі",      callback_data="addcat_cartridges")],
        [InlineKeyboardButton(text="Системи (поди)", callback_data="addcat_systems")],
    ])
    await message.answer("Обери категорію:", reply_markup=kb)


@router.callback_query(F.data.startswith("addcat_"))
async def add_category(callback: CallbackQuery, state: FSMContext):
    category = callback.data.replace("addcat_", "")
    await state.update_data(category=category)
    await state.set_state(AddProduct.description)
    await callback.message.answer("Введи опис товару (смак, міцність тощо):")
    await callback.answer()


@router.message(AddProduct.description)
async def add_description(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("Введи опис товару текстом:")
        return
    await state.update_data(description=message.text.strip())
    await state.set_state(AddProduct.price)
    await message.answer("Введи ціну (тільки число, наприклад: 120):")


@router.message(AddProduct.price)
async def add_price(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("Введи ціну числом, наприклад: 120")
        return
    try:
        price = float(message.text.replace(",", "."))
    except ValueError:
        await message.answer("Введи числову ціну, наприклад: 120")
        return

    await state.update_data(price=price)
    await state.set_state(AddProduct.stock)
    await message.answer("Скільки одиниць в наявності?")


@router.message(AddProduct.stock)
async def add_stock(message: Message, state: FSMContext):
    if not message.text or not message.text.isdigit():
        await message.answer("Введи ціле число, наприклад: 10")
        return

    await state.update_data(stock=int(message.text), photos=[])
    await state.set_state(AddProduct.photo)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Пропустити фото", callback_data="addphoto_skip")]
    ])
    await message.answer("Надішли фото товару (можна кілька по черзі) або пропусти:", reply_markup=kb)


def photos_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Додати ще фото", callback_data="addphoto_more")],
        [InlineKeyboardButton(text="✅ Готово",          callback_data="addphoto_done")],
    ])


@router.callback_query(F.data == "addphoto_skip")
async def skip_photo(callback: CallbackQuery, state: FSMContext):
    await save_product(callback.message, state, photos=[])
    await callback.answer()


@router.callback_query(F.data == "addphoto_more")
async def add_more_photo(callback: CallbackQuery):
    await callback.message.answer("Надішли наступне фото:")
    await callback.answer()


@router.callback_query(F.data == "addphoto_done")
async def done_photos(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await save_product(callback.message, state, photos=data.get('photos', []))
    await callback.answer()


@router.message(AddProduct.photo, ~F.photo)
async def add_photo_wrong_type(message: Message):
    await message.answer("Надішли фото або натисни 'Пропустити фото'.")


@router.message(AddProduct.photo, F.photo)
async def add_photo(message: Message, state: FSMContext):
    photo_id = message.photo[-1].file_id
    data = await state.get_data()
    photos = data.get('photos', [])

    if len(photos) >= 10:
        await message.answer("Максимум 10 фото на товар. Натисни ✅ Готово.")
        return

    photos.append(photo_id)
    await state.update_data(photos=photos)
    await message.answer(
        f"Фото {len(photos)} додано ✅\nДодай ще або натисни Готово:",
        reply_markup=photos_keyboard()
    )


async def save_product(message: Message, state: FSMContext, photos: list):
    data = await state.get_data()
    await state.clear()

    main_photo = photos[0] if photos else None

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        product_id = await conn.fetchval("""
            INSERT INTO products (name, category, description, price, stock, photo_id)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id
        """, data['name'], data['category'], data['description'],
            data['price'], data['stock'], main_photo)

        for i, pid in enumerate(photos):
            await conn.execute(
                "INSERT INTO product_photos (product_id, photo_id, position) VALUES ($1, $2, $3)",
                product_id, pid, i
            )
    finally:
        await conn.close()

    photo_info = f"{len(photos)} фото" if photos else "без фото"
    await message.answer(
        f"✅ Товар <b>{data['name']}</b> додано!\n"
        f"Ціна: {data['price']} грн | Залишок: {data['stock']} шт | {photo_info}"
    )


# ── /restock — поповнити залишок і сповістити waitlist ──
@router.message(Command("restock"))
async def cmd_restock(message: Message):
    if not is_admin(message.from_user.id):
        return

    args = message.text.split()
    if len(args) != 3 or not args[1].isdigit() or not args[2].isdigit():
        await message.answer(
            "Формат: /restock [id_товару] [кількість]\n"
            "Приклад: /restock 3 10"
        )
        return

    product_id = int(args[1])
    quantity = int(args[2])

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        product = await conn.fetchrow(
            "SELECT name FROM products WHERE id = $1", product_id
        )

        if not product:
            await message.answer(f"Товар #{product_id} не знайдено.")
            return

        await conn.execute(
            "UPDATE products SET stock = stock + $1 WHERE id = $2",
            quantity, product_id
        )
    finally:
        await conn.close()

    await message.answer(
        f"✅ Залишок товару <b>{product['name']}</b> поповнено на {quantity} шт."
    )

    # Сповістити всіх з waitlist
    waitlist = await get_waitlist_for_product(product_id)
    if waitlist:
        sent = 0
        for entry in waitlist:
            try:
                await message.bot.send_message(
                    entry['telegram_id'],
                    f"🔔 Товар <b>{product['name']}</b> знову є в наявності!\n"
                    "Поспішай замовити 👉 /start"
                )
                sent += 1
            except Exception:
                pass
        await clear_waitlist_for_product(product_id)
        await message.answer(f"Сповіщено {sent} клієнтів з листа очікування.")


# ── /zvit — тижневий звіт з аналізом ──
@router.message(Command("zvit"))
async def cmd_report(message: Message):
    if not is_admin(message.from_user.id):
        return

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        # Цей тиждень
        week = await conn.fetchrow("""
            SELECT
                COUNT(*) FILTER (WHERE status != 'cancelled') as total_orders,
                COUNT(*) FILTER (WHERE status = 'cancelled') as cancelled,
                COALESCE(SUM(total_price) FILTER (WHERE status != 'cancelled'), 0) as revenue,
                COALESCE(AVG(total_price) FILTER (WHERE status != 'cancelled'), 0) as avg_order
            FROM orders
            WHERE created_at >= NOW() - INTERVAL '7 days'
        """)

        # Минулий тиждень
        prev = await conn.fetchrow("""
            SELECT
                COUNT(*) FILTER (WHERE status != 'cancelled') as total_orders,
                COALESCE(SUM(total_price) FILTER (WHERE status != 'cancelled'), 0) as revenue,
                COALESCE(AVG(total_price) FILTER (WHERE status != 'cancelled'), 0) as avg_order
            FROM orders
            WHERE created_at >= NOW() - INTERVAL '14 days'
              AND created_at < NOW() - INTERVAL '7 days'
        """)

        # Топ-3 цього тижня
        top_week = await conn.fetch("""
            SELECT p.name, SUM(oi.quantity) as sold, SUM(oi.quantity * oi.price_at_order) as revenue
            FROM order_items oi
            JOIN products p ON oi.product_id = p.id
            JOIN orders o ON oi.order_id = o.id
            WHERE o.created_at >= NOW() - INTERVAL '7 days'
              AND o.status != 'cancelled'
            GROUP BY p.name ORDER BY sold DESC LIMIT 3
        """)

        # Топ-3 минулого тижня (для порівняння)
        top_prev = await conn.fetch("""
            SELECT p.name, SUM(oi.quantity) as sold
            FROM order_items oi
            JOIN products p ON oi.product_id = p.id
            JOIN orders o ON oi.order_id = o.id
            WHERE o.created_at >= NOW() - INTERVAL '14 days'
              AND o.created_at < NOW() - INTERVAL '7 days'
              AND o.status != 'cancelled'
            GROUP BY p.name ORDER BY sold DESC LIMIT 1
        """)

        # Нові клієнти
        new_customers = await conn.fetchval("""
            SELECT COUNT(*) FROM customers WHERE first_seen >= NOW() - INTERVAL '7 days'
        """)
        prev_new_customers = await conn.fetchval("""
            SELECT COUNT(*) FROM customers
            WHERE first_seen >= NOW() - INTERVAL '14 days'
              AND first_seen < NOW() - INTERVAL '7 days'
        """)

        # Повторні замовлення цього тижня
        repeat_orders = await conn.fetchval("""
            SELECT COUNT(DISTINCT o.customer_id)
            FROM orders o
            WHERE o.created_at >= NOW() - INTERVAL '7 days'
              AND o.status != 'cancelled'
              AND (SELECT COUNT(*) FROM orders o2
                   WHERE o2.customer_id = o.customer_id
                     AND o2.created_at < NOW() - INTERVAL '7 days') > 0
        """)

        # Товари що закінчуються
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

    # Виручка
    text += f"💰 <b>Виручка:</b> {curr_rev:.0f} грн{diff_str(curr_rev, prev_rev)}\n"
    text += f"   Минулий тиждень: {prev_rev:.0f} грн\n\n"

    # Замовлення
    text += f"🛒 <b>Замовлень:</b> {curr_orders}{diff_str(curr_orders, prev_orders)}\n"
    text += f"   Минулий тиждень: {prev_orders}\n"
    if week['cancelled']:
        text += f"   Скасовано: {week['cancelled']}\n"
    text += "\n"

    # Середній чек
    text += f"💳 <b>Середній чек:</b> {curr_avg:.0f} грн{diff_str(curr_avg, prev_avg)}\n"
    text += f"   Минулий тиждень: {prev_avg:.0f} грн\n\n"

    # Клієнти
    text += f"👤 <b>Нових клієнтів:</b> {new_customers}{diff_str(new_customers, prev_new_customers)}\n"
    if repeat_orders:
        text += f"🔄 <b>Повторних покупців:</b> {repeat_orders}\n"
    text += "\n"

    # Топ товари
    if top_week:
        prev_top_name = top_prev[0]['name'] if top_prev else None
        text += "🏆 <b>Топ товари:</b>\n"
        for i, p in enumerate(top_week, 1):
            leader = " 👑" if i == 1 and prev_top_name and p['name'] != prev_top_name else ""
            text += f"   {i}. {p['name']} — {p['sold']} шт ({p['revenue']:.0f} грн){leader}\n"
        if prev_top_name:
            text += f"   Лідер минулого тижня: {prev_top_name}\n"
        text += "\n"

    # Аналіз
    text += "🔍 <b>Аналіз:</b>\n"
    if curr_rev > prev_rev:
        text += f"   ✅ Виручка зросла на {curr_rev - prev_rev:.0f} грн\n"
    elif curr_rev < prev_rev:
        text += f"   ⚠️ Виручка впала на {prev_rev - curr_rev:.0f} грн\n"
    if new_customers > prev_new_customers:
        text += f"   ✅ Більше нових клієнтів ніж минулого тижня\n"
    elif new_customers < prev_new_customers:
        text += f"   ⚠️ Менше нових клієнтів ніж минулого тижня\n"
    if curr_avg > prev_avg:
        text += f"   ✅ Середній чек виріс\n"
    elif curr_avg < prev_avg:
        text += f"   ⚠️ Середній чек впав\n"
    text += "\n"

    # Залишки
    if low_stock:
        text += "⚠️ <b>Закінчується:</b>\n"
        for p in low_stock:
            icon = "🔴" if p['stock'] == 0 else "🟡"
            text += f"   {icon} {p['name']} — {p['stock']} шт\n"
        text += "\n"

    # Поради
    tips = []
    if curr_rev < prev_rev and curr_orders < prev_orders:
        tips.append("Падіння виручки і замовлень — варто зробити розсилку або акцію")
    if curr_avg < prev_avg:
        tips.append("Середній чек впав — спробуй запропонувати додаток до замовлення (картридж + жижа)")
    if new_customers < prev_new_customers:
        tips.append("Менше нових клієнтів — підштовхни існуючих поділитися посиланням на бот")
    if any(p['stock'] == 0 for p in low_stock):
        tips.append("Є товари з нульовим залишком — поповни щоб не втрачати замовлення")
    if repeat_orders and curr_orders > 0 and (repeat_orders / curr_orders) >= 0.7:
        tips.append("70%+ замовлень від постійних — добре утримання, але варто залучати нових")
    if not tips:
        tips.append("Все стабільно — продовжуй в тому ж темпі")

    text += "💡 <b>Поради:</b>\n"
    for tip in tips:
        text += f"   • {tip}\n"

    await message.answer(text)


# ── /removeproduct — видалити товар ──
@router.message(Command("removeproduct"))
async def cmd_removeproduct(message: Message):
    if not is_admin(message.from_user.id):
        return

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        products = await conn.fetch(
            "SELECT id, name, price FROM products WHERE is_active = TRUE"
        )
    finally:
        await conn.close()

    if not products:
        await message.answer("Немає активних товарів.")
        return

    buttons = [
        [InlineKeyboardButton(
            text=f"{p['name']} — {p['price']} грн",
            callback_data=f"remove_{p['id']}"
        )]
        for p in products
    ]
    await message.answer(
        "Який товар видалити?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )


@router.callback_query(F.data.startswith("remove_"))
async def confirm_remove(callback: CallbackQuery):
    product_id = int(callback.data.replace("remove_", ""))

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        product = await conn.fetchrow(
            "SELECT name FROM products WHERE id = $1", product_id
        )

        await conn.execute(
            "UPDATE products SET is_active = FALSE WHERE id = $1", product_id
        )
    finally:
        await conn.close()

    await callback.message.edit_text(
        f"✅ Товар <b>{product['name']}</b> прибрано з каталогу."
    )
    await callback.answer()
