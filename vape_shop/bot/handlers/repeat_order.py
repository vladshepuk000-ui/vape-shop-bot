import os
import logging
import aiosqlite
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

router = Router()
logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "vape_shop.db").replace("sqlite:///", "")


def confirm_repeat_keyboard(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Підтвердити", callback_data=f"repeat_confirm_{order_id}")],
        [InlineKeyboardButton(text="❌ Скасувати",   callback_data="repeat_cancel")],
    ])


@router.message(F.text == "🔄 Повторити замовлення")
async def repeat_order(message: Message):
    async with aiosqlite.connect(DATABASE_URL) as db:
        db.row_factory = aiosqlite.Row

        # Знайти останнє замовлення клієнта
        async with db.execute("""
            SELECT o.id, o.total_price, o.address, o.phone,
                   p.name as product_name, oi.quantity, oi.price_at_order
            FROM orders o
            LEFT JOIN customers c ON o.customer_id = c.id
            LEFT JOIN order_items oi ON oi.order_id = o.id
            LEFT JOIN products p ON oi.product_id = p.id
            WHERE c.telegram_id = ?
            ORDER BY o.created_at DESC
            LIMIT 1
        """, (message.from_user.id,)) as cursor:
            order = await cursor.fetchone()

    if not order:
        await message.answer(
            "У тебе ще немає замовлень.\n"
            "Зроби перше замовлення через 📦 Замовити"
        )
        return

    await message.answer(
        f"🔄 <b>Повторити останнє замовлення?</b>\n\n"
        f"Товар: {order['product_name']}\n"
        f"Кількість: {order['quantity']} шт\n"
        f"Сума: {order['total_price']} грн\n"
        f"Адреса: {order['address']}\n"
        f"Телефон: {order['phone']}",
        reply_markup=confirm_repeat_keyboard(order['id'])
    )


@router.callback_query(F.data.startswith("repeat_confirm_"))
async def confirm_repeat(callback: CallbackQuery):
    original_id = int(callback.data.replace("repeat_confirm_", ""))

    async with aiosqlite.connect(DATABASE_URL) as db:
        db.row_factory = aiosqlite.Row

        # Отримати дані оригінального замовлення
        async with db.execute("""
            SELECT o.customer_id, o.address, o.phone, o.notes,
                   oi.product_id, oi.quantity, oi.price_at_order,
                   p.price as current_price, p.stock, p.name, p.is_active
            FROM orders o
            LEFT JOIN order_items oi ON oi.order_id = o.id
            LEFT JOIN products p ON oi.product_id = p.id
            WHERE o.id = ?
        """, (original_id,)) as cursor:
            orig = await cursor.fetchone()

        if not orig:
            await callback.answer("Замовлення не знайдено", show_alert=True)
            return

        if orig['is_active'] == 0:
            await callback.answer(
                f"На жаль, {orig['name']} більше не доступний.",
                show_alert=True
            )
            return

        if orig['stock'] == 0:
            await callback.answer(
                f"На жаль, {orig['name']} зараз немає в наявності.",
                show_alert=True
            )
            return

        # Використовуємо поточну ціну товару
        total = orig['quantity'] * orig['current_price']

        # Створити нове замовлення
        cursor = await db.execute(
            "INSERT INTO orders (customer_id, address, phone, notes, total_price) VALUES (?, ?, ?, ?, ?)",
            (orig['customer_id'], orig['address'], orig['phone'], orig['notes'], total)
        )
        new_order_id = cursor.lastrowid

        await db.execute(
            "INSERT INTO order_items (order_id, product_id, quantity, price_at_order) VALUES (?, ?, ?, ?)",
            (new_order_id, orig['product_id'], orig['quantity'], orig['current_price'])
        )
        await db.execute(
            "UPDATE customers SET total_orders = total_orders + 1, last_order = CURRENT_TIMESTAMP WHERE id = ?",
            (orig['customer_id'],)
        )
        await db.commit()

    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        f"✅ Замовлення #{new_order_id} створено!\n\n"
        f"Сума: {total} грн\n"
        "Ми зв'яжемось з тобою найближчим часом. Дякуємо! 🙏\n\n"
        "<i>Якщо замовлення було зроблено випадково — скасуй нижче.</i>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="🚫 Скасувати замовлення",
                callback_data=f"cancel_order_{new_order_id}"
            )]
        ])
    )

    # Повідомити адміна
    admin_ids = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x]
    for admin_id in admin_ids:
        try:
            await callback.bot.send_message(
                admin_id,
                f"🔄 <b>ПОВТОРНЕ ЗАМОВЛЕННЯ #{new_order_id}</b>\n\n"
                f"Товар: {orig['name']}\n"
                f"Кількість: {orig['quantity']} шт\n"
                f"Сума: {total} грн\n"
                f"Адреса: {orig['address']}\n"
                f"Телефон: {orig['phone']}\n"
                f"Клієнт: @{callback.from_user.username or '—'}"
            )
        except Exception as e:
            logger.error(f"Не вдалось надіслати адміну: {e}")

    await callback.answer()


@router.callback_query(F.data == "repeat_cancel")
async def cancel_repeat(callback: CallbackQuery):
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Скасовано.")
    await callback.answer()
