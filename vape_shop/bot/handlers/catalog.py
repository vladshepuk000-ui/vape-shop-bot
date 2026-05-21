import os
import asyncpg
from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from database.queries import get_all_products, get_products_by_category, get_product_by_id

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:jHInKjjHzgONUJeWLNNkoxIumLhqIjIs@tramway.proxy.rlwy.net:56512/railway"
)

router = Router()

CATEGORIES = {
    "liquids":     "Рідини",
    "cartridges":  "Картриджі",
    "systems":     "Системи (поди)",
}


def categories_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=name, callback_data=f"cat_{key}")]
        for key, name in CATEGORIES.items()
    ]
    buttons.append([InlineKeyboardButton(text="Всі товари", callback_data="cat_all")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def brands_keyboard(brands: list) -> InlineKeyboardMarkup:
    buttons = []
    for b in brands:
        brand = b["brand"] if isinstance(b, dict) else b
        in_stock = b.get("in_stock", 1) if isinstance(b, dict) else 1
        name = "Інші рідини" if brand == "__no_brand__" else brand
        label = f"✅ {name}" if in_stock else f"❌ {name} — немає в наявності"
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"lbrand_{brand}")])
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="cat_back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def products_keyboard(products: list, list_back: str, item_back: str = None) -> InlineKeyboardMarkup:
    if item_back is None:
        item_back = list_back
    buttons = [
        [InlineKeyboardButton(text=f"{p['name']} — {p['price']} грн", callback_data=f"product_{p['id']}_{item_back}")]
        for p in products
    ]
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=list_back)])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def product_keyboard(product_id: int, back_callback: str, in_stock: bool = True) -> InlineKeyboardMarkup:
    if in_stock:
        buttons = [
            [InlineKeyboardButton(text="🛒 Замовити", callback_data=f"buy_{product_id}")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data=back_callback)],
        ]
    else:
        buttons = [
            [InlineKeyboardButton(text="🔔 Сповісти коли з'явиться", callback_data=f"waitlist_{product_id}")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data=back_callback)],
        ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def get_liquid_brands() -> list:
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        rows = await conn.fetch("""
            SELECT brand,
                   COUNT(*) FILTER (WHERE stock > 0) as in_stock
            FROM products
            WHERE category = 'liquids' AND is_active = TRUE AND brand IS NOT NULL
            GROUP BY brand
            ORDER BY brand
        """)
        brands = [{"brand": r["brand"], "in_stock": r["in_stock"]} for r in rows]

        no_brand = await conn.fetchrow("""
            SELECT COUNT(*) FILTER (WHERE stock > 0) as in_stock,
                   COUNT(*) as total
            FROM products
            WHERE category = 'liquids' AND is_active = TRUE AND brand IS NULL
        """)
        if no_brand and no_brand["total"]:
            brands.append({"brand": "__no_brand__", "in_stock": no_brand["in_stock"]})
        return brands
    finally:
        await conn.close()


async def get_products_by_brand(brand: str) -> list:
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        if brand == "__no_brand__":
            rows = await conn.fetch("""
                SELECT * FROM products
                WHERE category = 'liquids' AND brand IS NULL AND is_active = TRUE
                ORDER BY name
            """)
        else:
            rows = await conn.fetch("""
                SELECT * FROM products
                WHERE category = 'liquids' AND brand = $1 AND is_active = TRUE
                ORDER BY name
            """, brand)
        return [dict(r) for r in rows]
    finally:
        await conn.close()


# ── Кнопка "Каталог" з головного меню ──
@router.message(F.text == "🛍 Каталог")
async def show_catalog(message: Message):
    await message.answer(
        "Оберіть категорію:",
        reply_markup=categories_keyboard()
    )


# ── Вибір категорії ──
@router.callback_query(F.data.startswith("cat_"))
async def show_category(callback):
    category = callback.data.replace("cat_", "")

    if category == "back":
        try:
            await callback.message.edit_text(
                "Оберіть категорію:",
                reply_markup=categories_keyboard()
            )
        except Exception:
            await callback.message.answer(
                "Оберіть категорію:",
                reply_markup=categories_keyboard()
            )
        await callback.answer()
        return

    if category == "all":
        products = await get_all_products()
        if not products:
            await callback.answer("Товарів немає", show_alert=True)
            return
        try:
            await callback.message.edit_text(
                "📦 Всі товари:",
                reply_markup=products_keyboard(products, "cat_back", "cat_back")
            )
        except Exception:
            await callback.message.answer(
                "📦 Всі товари:",
                reply_markup=products_keyboard(products, "cat_back", "cat_back")
            )
        await callback.answer()
        return

    # Рідини — показуємо бренди
    if category == "liquids":
        brands = await get_liquid_brands()
        if brands:
            try:
                await callback.message.edit_text(
                    "🧴 Оберіть виробника:",
                    reply_markup=brands_keyboard(brands)
                )
            except Exception:
                await callback.message.answer(
                    "🧴 Оберіть виробника:",
                    reply_markup=brands_keyboard(brands)
                )
            await callback.answer()
            return
        # Якщо брендів немає — показуємо всі рідини напряму
        products = await get_products_by_category(category)
        if not products:
            await callback.answer("Товарів в цій категорії немає", show_alert=True)
            return
        try:
            await callback.message.edit_text(
                "📦 Рідини:",
                reply_markup=products_keyboard(products, "cat_back", "cat_liquids")
            )
        except Exception:
            await callback.message.answer(
                "📦 Рідини:",
                reply_markup=products_keyboard(products, "cat_back", "cat_liquids")
            )
        await callback.answer()
        return

    # Інші категорії — одразу список товарів
    products = await get_products_by_category(category)
    title = CATEGORIES.get(category, category)

    if not products:
        await callback.answer("Товарів в цій категорії немає", show_alert=True)
        return

    try:
        await callback.message.edit_text(
            f"📦 {title}:",
            reply_markup=products_keyboard(products, "cat_back", f"cat_{category}")
        )
    except Exception:
        await callback.message.answer(
            f"📦 {title}:",
            reply_markup=products_keyboard(products, "cat_back", f"cat_{category}")
        )
    await callback.answer()


# ── Вибір бренду рідин ──
@router.callback_query(F.data.startswith("lbrand_"))
async def show_brand_products(callback):
    brand = callback.data.replace("lbrand_", "")
    products = await get_products_by_brand(brand)

    if not products:
        await callback.answer("Товарів цього виробника немає", show_alert=True)
        return

    label = "Інші рідини" if brand == "__no_brand__" else brand
    item_back = f"lbrand_{brand}"
    try:
        await callback.message.edit_text(
            f"🧴 {label}:",
            reply_markup=products_keyboard(products, "back_to_brands", item_back)
        )
    except Exception:
        await callback.message.answer(
            f"🧴 {label}:",
            reply_markup=products_keyboard(products, "back_to_brands", item_back)
        )
    await callback.answer()


# ── Назад з вкусів до списку брендів ──
@router.callback_query(F.data == "back_to_brands")
async def back_to_brands(callback):
    brands = await get_liquid_brands()
    try:
        await callback.message.edit_text(
            "🧴 Оберіть виробника:",
            reply_markup=brands_keyboard(brands)
        )
    except Exception:
        await callback.message.answer(
            "🧴 Оберіть виробника:",
            reply_markup=brands_keyboard(brands)
        )
    await callback.answer()


# ── Картка товару ──
@router.callback_query(F.data.startswith("product_"))
async def show_product(callback):
    # format: product_{id}_{back_callback}
    data = callback.data[len("product_"):]
    try:
        first_underscore = data.index("_")
        product_id = int(data[:first_underscore])
        back_callback = data[first_underscore + 1:] if first_underscore + 1 < len(data) else "cat_back"
    except (ValueError, IndexError):
        await callback.answer("Помилка навігації", show_alert=True)
        return
    product = await get_product_by_id(product_id)

    if not product:
        await callback.answer("Товар не знайдено", show_alert=True)
        return

    stock_text = f"✅ В наявності: {product['stock']} шт" if product['stock'] > 0 else "❌ Немає в наявності"

    text = (
        f"<b>{product['name']}</b>\n\n"
        f"{product['description'] or ''}\n\n"
        f"💰 Ціна: {product['price']} грн\n"
        f"{stock_text}"
    )

    in_stock = product['stock'] > 0
    kb = product_keyboard(product_id, back_callback, in_stock)

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        rows = await conn.fetch(
            "SELECT photo_id FROM product_photos WHERE product_id = $1 ORDER BY position",
            product_id
        )
    finally:
        await conn.close()
    photos = [r["photo_id"] for r in rows]

    if not photos and product['photo_id']:
        photos = [product['photo_id']]

    if len(photos) > 1:
        media = [InputMediaPhoto(media=p) for p in photos]
        await callback.message.answer_media_group(media)
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")
    elif len(photos) == 1:
        await callback.message.answer_photo(photos[0], caption=text, reply_markup=kb, parse_mode="HTML")
    else:
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")

    await callback.answer()
