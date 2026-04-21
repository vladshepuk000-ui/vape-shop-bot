import os
import re
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command

from bot.states.order_states import OrderForm
from database.queries import get_product_by_id
import aiosqlite

router = Router()
logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "vape_shop.db").replace("sqlite:///", "")
PHONE_RE = re.compile(r"^(\+?3?8?0\d{9}|0\d{9})$")


# ── Клавіатура підтвердження ──
def confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Підтвердити", callback_data="order_confirm")],
        [InlineKeyboardButton(text="❌ Скасувати",   callback_data="order_cancel")],
    ])


def skip_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Пропустити", callback_data="order_skip_notes")],
        [InlineKeyboardButton(text="❌ Скасувати", callback_data="order_cancel")],
    ])


def cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Скасувати замовлення", callback_data="order_cancel")],
    ])


def delivery_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚚 Нова Пошта",  callback_data="delivery_nova_poshta")],
        [InlineKeyboardButton(text="🏠 Самовивіз",   callback_data="delivery_pickup")],
        [InlineKeyboardButton(text="❌ Скасувати",   callback_data="order_cancel")],
    ])


def payment_method_keyboard(delivery: str = "nova_poshta") -> InlineKeyboardMarkup:
    if delivery == "pickup":
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Оплата на картку", callback_data="pay_method_card")],
            [InlineKeyboardButton(text="💵 Готівка",          callback_data="pay_method_cash")],
            [InlineKeyboardButton(text="❌ Скасувати",        callback_data="order_cancel")],
        ])
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Оплата на картку",  callback_data="pay_method_card")],
        [InlineKeyboardButton(text="📦 Накладений платіж", callback_data="pay_method_cod")],
        [InlineKeyboardButton(text="❌ Скасувати",         callback_data="order_cancel")],
    ])


# ── /cancel — скидає FSM ──
@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    from bot.handlers.start import main_menu
    await message.answer(
        "Замовлення скасовано. Повертайся коли захочеш 👋",
        reply_markup=main_menu
    )


STATUS_LABELS = {
    "awaiting_payment": "⏳ Очікує оплати",
    "new":              "🆕 Нове",
    "confirmed":        "✅ Підтверджено",
    "sent":             "🚚 Відправлено",
    "done":             "✔️ Виконано",
    "cancelled":        "❌ Скасовано",
}


# ── Мої замовлення ──
@router.message(F.text == "📊 Мої замовлення")
async def my_orders(message: Message):
    async with aiosqlite.connect(DATABASE_URL) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT o.id, o.status, o.total_price, o.created_at,
                   p.name as product_name, oi.quantity
            FROM orders o
            LEFT JOIN customers c ON o.customer_id = c.id
            LEFT JOIN order_items oi ON oi.order_id = o.id
            LEFT JOIN products p ON oi.product_id = p.id
            WHERE c.telegram_id = ?
            ORDER BY o.created_at DESC
            LIMIT 5
        """, (message.from_user.id,)) as cursor:
            orders = await cursor.fetchall()

    if not orders:
        await message.answer("У тебе ще немає замовлень.\nПерегляни 🛍 Каталог щоб зробити перше!")
        return

    text = "📊 <b>Твої останні замовлення:</b>\n\n"
    for o in orders:
        status = STATUS_LABELS.get(o['status'], o['status'])
        date = o['created_at'][:10] if o['created_at'] else "—"
        text += (
            f"#{o['id']} — {status}\n"
            f"{o['product_name']} x{o['quantity']} — {o['total_price']} грн\n"
            f"📅 {date}\n\n"
        )

    await message.answer(text)


# ── Старт замовлення з картки товару ──
@router.callback_query(F.data.startswith("buy_"))
async def order_from_catalog(callback: CallbackQuery, state: FSMContext):
    product_id = int(callback.data.replace("buy_", ""))
    product = await get_product_by_id(product_id)

    if not product:
        await callback.answer("Товар не знайдено", show_alert=True)
        return

    await state.update_data(
        product_id=product_id,
        product_name=product['name'],
        product_price=product['price']
    )
    await state.set_state(OrderForm.choosing_quantity)
    await callback.message.answer(
        f"Ти обрав: <b>{product['name']}</b> — {product['price']} грн\n\n"
        "Скільки штук хочеш замовити?",
        reply_markup=cancel_keyboard()
    )
    await callback.answer()


# ── Вибір товару з меню замовлення ──
@router.callback_query(F.data.startswith("ord_product_"))
async def choose_product(callback: CallbackQuery, state: FSMContext):
    product_id = int(callback.data.replace("ord_product_", ""))
    product = await get_product_by_id(product_id)

    if not product:
        await callback.answer("Товар не знайдено", show_alert=True)
        return

    await state.update_data(
        product_id=product_id,
        product_name=product['name'],
        product_price=product['price']
    )
    await state.set_state(OrderForm.choosing_quantity)
    await callback.message.answer(
        f"Ти обрав: <b>{product['name']}</b> — {product['price']} грн\n\n"
        "Скільки штук хочеш замовити?",
        reply_markup=cancel_keyboard()
    )
    await callback.answer()


# ── Кількість ──
@router.message(OrderForm.choosing_quantity)
async def choose_quantity(message: Message, state: FSMContext):
    if not message.text or not message.text.isdigit() or int(message.text) < 1:
        await message.answer("Введи кількість цифрами, наприклад: 1", reply_markup=cancel_keyboard())
        return

    quantity = int(message.text)
    data = await state.get_data()

    # Перевірити наявність
    product = await get_product_by_id(data['product_id'])
    if not product or product['stock'] < quantity:
        available = product['stock'] if product else 0
        await message.answer(
            f"На жаль, доступно лише <b>{available} шт</b>.\n"
            "Введи меншу кількість:",
            reply_markup=cancel_keyboard()
        )
        return

    total = quantity * data['product_price']

    await state.update_data(quantity=quantity, total=total)
    await state.set_state(OrderForm.entering_phone)
    await message.answer(
        f"Кількість: {quantity} шт — {total} грн\n\n"
        "Введи номер телефону:\n"
        "<i>0981234567 або +380981234567</i>",
        reply_markup=cancel_keyboard()
    )


# ── Адреса ──
@router.message(OrderForm.entering_address)
async def enter_address(message: Message, state: FSMContext):
    if not message.text or len(message.text.strip()) < 5:
        await message.answer("Введи повну адресу (місто + відділення НП)", reply_markup=cancel_keyboard())
        return

    await state.update_data(address=message.text.strip())
    await state.set_state(OrderForm.entering_notes)
    await message.answer(
        "Є коментар до замовлення? (наприклад: смак, міцність нікотину)\n"
        "Або натисни кнопку щоб пропустити.",
        reply_markup=skip_keyboard()
    )


# ── Телефон ──
@router.message(OrderForm.entering_phone)
async def enter_phone(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("Введи номер телефону текстом:", reply_markup=cancel_keyboard())
        return
    phone_raw = message.text.strip().replace(" ", "").replace("-", "")
    if not PHONE_RE.match(phone_raw):
        await message.answer(
            "Некоректний номер. Введи у одному з форматів:\n"
            "0981234567\n"
            "+380981234567",
            reply_markup=cancel_keyboard()
        )
        return

    await state.update_data(phone=phone_raw)
    await state.set_state(OrderForm.choosing_delivery)
    await message.answer(
        "Обери спосіб отримання:",
        reply_markup=delivery_keyboard()
    )


# ── Вибір доставки ──
@router.callback_query(F.data.startswith("delivery_"))
async def choose_delivery(callback: CallbackQuery, state: FSMContext):
    delivery = callback.data.replace("delivery_", "")
    await state.update_data(delivery=delivery)

    if delivery == "pickup":
        pickup_address = os.getenv("PICKUP_ADDRESS", "уточніть у продавця")
        await state.update_data(address="Самовивіз")
        await state.set_state(OrderForm.entering_notes)
        await callback.message.answer(
            f"🏠 <b>Самовивіз</b>\n"
            f"📍 Адреса: {pickup_address}\n\n"
            "Є коментар до замовлення?\n"
            "Або натисни кнопку щоб пропустити.",
            reply_markup=skip_keyboard()
        )
    else:
        await state.set_state(OrderForm.entering_address)
        await callback.message.answer(
            "Введи адресу доставки:\n"
            "<i>Місто + номер відділення Нової Пошти</i>\n"
            "Наприклад: Одеса, НП №12",
            reply_markup=cancel_keyboard()
        )
    await callback.answer()


# ── Пропустити коментар ──
@router.callback_query(F.data == "order_skip_notes")
async def skip_notes(callback: CallbackQuery, state: FSMContext):
    await state.update_data(notes="")
    data = await state.get_data()
    await state.set_state(OrderForm.choosing_payment)
    await callback.message.answer(
        "Обери спосіб оплати:",
        reply_markup=payment_method_keyboard(data.get('delivery', 'nova_poshta'))
    )
    await callback.answer()


# ── Коментар ──
@router.message(OrderForm.entering_notes)
async def enter_notes(message: Message, state: FSMContext):
    await state.update_data(notes=message.text.strip() if message.text else "")
    data = await state.get_data()
    await state.set_state(OrderForm.choosing_payment)
    await message.answer(
        "Обери спосіб оплати:",
        reply_markup=payment_method_keyboard(data.get('delivery', 'nova_poshta'))
    )


# ── Вибір способу оплати ──
@router.callback_query(F.data.startswith("pay_method_"))
async def choose_payment(callback: CallbackQuery, state: FSMContext):
    method = callback.data.replace("pay_method_", "")
    await state.update_data(payment_method=method)
    await state.set_state(OrderForm.confirmation)
    await show_confirmation(callback.message, state)
    await callback.answer()


# ── Показати підсумок ──
async def show_confirmation(message: Message, state: FSMContext):
    data = await state.get_data()
    method = data.get('payment_method', 'card')
    delivery = data.get('delivery', 'nova_poshta')

    if method == 'card':
        card = os.getenv("PAYMENT_CARD", "").strip()
        payment_name = os.getenv("PAYMENT_NAME", "").strip()
        payment_text = f"💳 Картка: <code>{card}</code>\nОтримувач: {payment_name}"
    elif method == 'cash':
        payment_text = "💵 Готівка при самовивізі"
    else:
        payment_text = "📦 Накладений платіж (оплата при отриманні)"

    delivery_text = "🏠 Самовивіз" if delivery == "pickup" else f"🚚 Нова Пошта: {data['address']}"

    text = (
        "📋 <b>Перевір замовлення:</b>\n\n"
        f"Товар: {data['product_name']}\n"
        f"Кількість: {data['quantity']} шт\n"
        f"Сума: {data['total']} грн\n"
        f"Доставка: {delivery_text}\n"
        f"Телефон: {data['phone']}\n"
    )
    if data.get('notes'):
        text += f"Коментар: {data['notes']}\n"

    text += f"\nОплата: {payment_text}\n\nПідтверджуєш замовлення?"

    await message.answer(text, reply_markup=confirm_keyboard())


PAYMENT_LABELS = {
    "card": "💳 Картка",
    "cod":  "📦 Накладений платіж",
    "cash": "💵 Готівка",
}


# ── Підтвердження ──
@router.callback_query(F.data == "order_confirm")
async def confirm_order(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    user = callback.from_user
    method = data.get('payment_method', 'card')

    async with aiosqlite.connect(DATABASE_URL) as db:
        # Знайти customer_id
        async with db.execute(
            "SELECT id FROM customers WHERE telegram_id = ?", (user.id,)
        ) as cursor:
            row = await cursor.fetchone()
            customer_id = row[0] if row else None

        # Картка — чекаємо скріншот, залишок не чіпаємо
        # Накладений / Готівка — одразу "new", залишок зменшуємо
        initial_status = "awaiting_payment" if method == "card" else "new"

        cursor = await db.execute(
            "INSERT INTO orders (customer_id, address, phone, notes, total_price, status) VALUES (?, ?, ?, ?, ?, ?)",
            (customer_id, data['address'], data['phone'], data.get('notes', ''), data['total'], initial_status)
        )
        order_id = cursor.lastrowid

        await db.execute(
            "INSERT INTO order_items (order_id, product_id, quantity, price_at_order) VALUES (?, ?, ?, ?)",
            (order_id, data['product_id'], data['quantity'], data['product_price'])
        )

        # Зменшуємо залишок для накладеного та готівки
        if method != "card":
            await db.execute(
                "UPDATE products SET stock = MAX(0, stock - ?) WHERE id = ?",
                (data['quantity'], data['product_id'])
            )

        await db.execute(
            "UPDATE customers SET total_orders = total_orders + 1, last_order = CURRENT_TIMESTAMP WHERE id = ?",
            (customer_id,)
        )
        await db.commit()

    await callback.message.edit_reply_markup(reply_markup=None)

    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚫 Скасувати замовлення", callback_data=f"cancel_order_{order_id}")]
    ])

    # Повідомлення адміну
    admin_ids = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x]
    payment_label = PAYMENT_LABELS.get(method, method)

    delivery = data.get('delivery', 'nova_poshta')
    delivery_label = "🏠 Самовивіз" if delivery == "pickup" else f"🚚 НП: {data['address']}"

    for admin_id in admin_ids:
        try:
            await callback.bot.send_message(
                admin_id,
                f"🛒 <b>НОВЕ ЗАМОВЛЕННЯ #{order_id}</b>\n\n"
                f"Товар: {data['product_name']}\n"
                f"Кількість: {data['quantity']} шт\n"
                f"Сума: {data['total']} грн\n"
                f"Доставка: {delivery_label}\n"
                f"Телефон: {data['phone']}\n"
                f"Коментар: {data.get('notes', '—')}\n"
                f"Оплата: {payment_label}\n"
                f"Клієнт: @{callback.from_user.username or '—'}"
            )
        except Exception as e:
            logger.error(f"Не вдалось надіслати адміну {admin_id}: {e}")

    if method == 'card':
        # Просимо скріншот оплати
        card = os.getenv("PAYMENT_CARD", "").strip()
        payment_name = os.getenv("PAYMENT_NAME", "").strip()
        await state.set_state(OrderForm.waiting_screenshot)
        await state.update_data(order_id=order_id)
        await callback.message.answer(
            f"✅ Замовлення #{order_id} зареєстровано!\n\n"
            f"💳 Переказ на картку:\n"
            f"<code>{card}</code>\n"
            f"Отримувач: {payment_name}\n"
            f"Сума: <b>{data['total']} грн</b>\n\n"
            "Після оплати надішли <b>скріншот</b> сюди 👇",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🚫 Скасувати замовлення", callback_data=f"cancel_order_{order_id}")]
            ])
        )
    elif method == 'cash':
        pickup_address = os.getenv("PICKUP_ADDRESS", "уточніть у продавця")
        await state.clear()
        await callback.message.answer(
            f"✅ Замовлення #{order_id} прийнято!\n\n"
            f"🏠 Самовивіз: {pickup_address}\n"
            "💵 Оплата готівкою при отриманні.\n"
            "Зв'яжемось для уточнення часу. Дякуємо! 🙏",
            reply_markup=cancel_kb
        )
    else:
        # Накладений платіж
        await state.clear()
        await callback.message.answer(
            f"✅ Замовлення #{order_id} прийнято!\n\n"
            "📦 Накладений платіж — оплатиш при отриманні.\n"
            "Ми зв'яжемось для підтвердження. Дякуємо! 🙏",
            reply_markup=cancel_kb
        )

    await callback.answer()


# ── Скріншот оплати ──
@router.message(OrderForm.waiting_screenshot, F.photo)
async def receive_screenshot(message: Message, state: FSMContext):
    data = await state.get_data()
    order_id = data.get('order_id')
    await state.clear()

    async with aiosqlite.connect(DATABASE_URL) as db:
        db.row_factory = aiosqlite.Row

        # Отримати позиції замовлення
        async with db.execute(
            "SELECT product_id, quantity FROM order_items WHERE order_id = ?", (order_id,)
        ) as cursor:
            items = await cursor.fetchall()

        # Зменшити залишок — оплата підтверджена скріншотом
        for item in items:
            await db.execute(
                "UPDATE products SET stock = MAX(0, stock - ?) WHERE id = ?",
                (item['quantity'], item['product_id'])
            )

        # Змінити статус замовлення на "new" (оплата надійшла, чекає обробки)
        await db.execute(
            "UPDATE orders SET status = 'new' WHERE id = ?", (order_id,)
        )
        await db.commit()

    # Переслати скріншот адміну
    admin_ids = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x]
    for admin_id in admin_ids:
        try:
            await message.forward(admin_id)
        except Exception as e:
            logger.error(f"Не вдалось переслати скріншот адміну {admin_id}: {e}")
        try:
            await message.bot.send_message(
                admin_id,
                f"💰 Скріншот оплати для замовлення #{order_id} "
                f"від @{message.from_user.username or '—'}\n\n"
                f"Щоб підтвердити: /setstatus {order_id} confirmed"
            )
        except Exception as e:
            logger.error(f"Не вдалось надіслати підказку адміну {admin_id}: {e}")

    await message.answer(
        f"✅ Скріншот отримано! Перевіримо оплату і підтвердимо замовлення #{order_id}.\n"
        "Дякуємо! 🙏",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🚫 Скасувати замовлення", callback_data=f"cancel_order_{order_id}")]
        ])
    )


# ── Якщо надіслали текст замість скріншоту ──
@router.message(OrderForm.waiting_screenshot)
async def screenshot_wrong_format(message: Message):
    await message.answer("Надішли <b>фото</b> (скріншот оплати), а не текст.")


# ── Скасування під час оформлення ──
@router.callback_query(F.data == "order_cancel")
async def cancel_order(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    from bot.handlers.start import main_menu
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        "Замовлення скасовано. Повертайся коли захочеш 👋",
        reply_markup=main_menu
    )
    await callback.answer()


# ── Скасування вже прийнятого замовлення ──
@router.callback_query(F.data.startswith("cancel_order_"))
async def cancel_placed_order(callback: CallbackQuery, state: FSMContext):
    order_id = int(callback.data.replace("cancel_order_", ""))

    async with aiosqlite.connect(DATABASE_URL) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT status FROM orders WHERE id = ?", (order_id,)
        ) as cursor:
            order = await cursor.fetchone()

        if not order:
            await callback.answer("Замовлення не знайдено", show_alert=True)
            return

        if order['status'] not in ("new", "awaiting_payment"):
            await callback.answer(
                "Замовлення вже в обробці — для скасування зв'яжіться з нами напряму.",
                show_alert=True
            )
            return

        # Отримати позиції замовлення
        async with db.execute(
            "SELECT product_id, quantity FROM order_items WHERE order_id = ?", (order_id,)
        ) as cursor:
            items = await cursor.fetchall()

        await db.execute(
            "UPDATE orders SET status = 'cancelled' WHERE id = ?", (order_id,)
        )

        # Повертаємо залишок лише якщо скріншот вже був надісланий (статус "new")
        # При "awaiting_payment" залишок ще не зменшувався — нічого повертати
        if order['status'] == "new":
            for item in items:
                await db.execute(
                    "UPDATE products SET stock = stock + ? WHERE id = ?",
                    (item['quantity'], item['product_id'])
                )

        await db.commit()

    # Скинути FSM-стан якщо клієнт скасував під час очікування скріншоту
    await state.clear()

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(f"🚫 Замовлення #{order_id} скасовано.")

    # Повідомити адміна
    admin_ids = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x]
    for admin_id in admin_ids:
        try:
            await callback.bot.send_message(
                admin_id,
                f"🚫 Замовлення #{order_id} скасовано клієнтом @{callback.from_user.username or '—'}"
            )
        except Exception:
            pass

    await callback.answer()
