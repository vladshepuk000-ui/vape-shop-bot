"""Хендлери каталогу: послуги, категорії, товари, пакети."""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery

from db.database import get_connection
from db import models
from keyboards.main_menu import BTN_CATALOG, BTN_PACKAGES, BTN_ORDER
from keyboards.catalog_kb import (
    services_keyboard,
    categories_keyboard,
    products_keyboard,
    product_detail_keyboard,
    packages_keyboard,
    package_detail_keyboard,
)
from config import settings

router = Router()

NO_ITEMS_TEXT = "Наразі в каталозі немає доступних позицій. Зверніться до менеджера."


# ---------------------------------------------------------------------------
# Каталог послуг
# ---------------------------------------------------------------------------

@router.message(lambda m: m.text == BTN_CATALOG)
async def show_catalog_menu(message: Message) -> None:
    await message.answer(
        "Оберіть розділ каталогу:",
        reply_markup=_catalog_section_kb(),
    )


@router.message(lambda m: m.text == BTN_ORDER)
async def show_installation_menu(message: Message) -> None:
    await message.answer(
        "Встановлення памятників:",
        reply_markup=_catalog_section_kb(),
    )


def _catalog_section_kb():
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text="🕊 Послуги", callback_data="catalog:services")
    builder.button(text="🛒 Товари", callback_data="catalog:categories")
    builder.adjust(2)
    return builder.as_markup()


@router.callback_query(F.data == "catalog:services")
async def show_services(callback: CallbackQuery) -> None:
    async with get_connection() as db:
        services = await models.get_services(db)
    if not services:
        await callback.message.edit_text(NO_ITEMS_TEXT)
        return
    await callback.message.edit_text(
        "Наші послуги:", reply_markup=services_keyboard(services)
    )


@router.callback_query(F.data.startswith("service:"))
async def show_service_detail(callback: CallbackQuery) -> None:
    service_id = int(callback.data.split(":")[1])
    async with get_connection() as db:
        svc = await models.get_service(db, service_id)
    if not svc:
        await callback.answer("Послуга не знайдена.", show_alert=True)
        return

    text = (
        f"<b>{svc['name']}</b>\n\n"
        f"{svc['description']}\n\n"
        f"💰 Вартість: <b>{svc['price']:.0f} грн</b>"
    )
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text="📝 Замовити послугу", callback_data=f"order_service:{service_id}")
    builder.button(text="⬅️ До послуг", callback_data="catalog:services")
    builder.adjust(1)
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())


# ---------------------------------------------------------------------------
# Категорії та товари
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "catalog:categories")
async def show_categories(callback: CallbackQuery) -> None:
    async with get_connection() as db:
        categories = await models.get_categories(db)
    if not categories:
        await callback.message.edit_text(NO_ITEMS_TEXT)
        return
    await callback.message.edit_text(
        "Оберіть категорію:", reply_markup=categories_keyboard(categories)
    )


@router.callback_query(F.data.startswith("category:"))
async def show_products(callback: CallbackQuery) -> None:
    category_id = int(callback.data.split(":")[1])
    async with get_connection() as db:
        products = await models.get_products_by_category(db, category_id)
    if not products:
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        builder = InlineKeyboardBuilder()
        builder.button(text="✍️ Написати менеджеру", callback_data="contact:manager")
        builder.button(text="📞 Зателефонувати", callback_data="contact:phone")
        builder.button(text="⬅️ Назад", callback_data="catalog:categories")
        builder.adjust(1)
        await callback.message.edit_text(
            "У цій категорії поки немає товарів.\n"
            "Ви можете звернутися до менеджера напряму:",
            reply_markup=builder.as_markup(),
        )
        return
    await callback.message.edit_text(
        "Товари в категорії:\n🔧 — виготовляється на замовлення",
        reply_markup=products_keyboard(products, category_id),
    )


@router.callback_query(F.data.startswith("product:"))
async def show_product_detail(callback: CallbackQuery) -> None:
    product_id = int(callback.data.split(":")[1])
    async with get_connection() as db:
        product = await models.get_product(db, product_id)
    if not product:
        await callback.answer("Товар не знайдено.", show_alert=True)
        return

    custom_note = ""
    if product["is_custom"]:
        days = product["lead_days"] or "?"
        custom_note = f"\n\n🔧 <i>Виготовляється на замовлення. Орієнтовний термін: {days} дн.</i>"

    text = (
        f"<b>{product['name']}</b>\n\n"
        f"{product['description']}"
        f"{custom_note}\n\n"
        f"💰 Ціна: <b>{product['price']:.0f} грн</b>"
    )

    if product["photo_file_id"]:
        await callback.message.answer_photo(
            photo=product["photo_file_id"],
            caption=text,
            parse_mode="HTML",
            reply_markup=product_detail_keyboard(product_id),
        )
        await callback.message.delete()
    else:
        await callback.message.edit_text(
            text, parse_mode="HTML", reply_markup=product_detail_keyboard(product_id)
        )


# ---------------------------------------------------------------------------
# Пакети
# ---------------------------------------------------------------------------

@router.message(lambda m: m.text == BTN_PACKAGES)
async def show_packages(message: Message) -> None:
    async with get_connection() as db:
        packages = await models.get_packages(db)
    if not packages:
        await message.answer(NO_ITEMS_TEXT)
        return
    await message.answer(
        "Виготовлення памятників:", reply_markup=packages_keyboard(packages)
    )


@router.callback_query(F.data == "catalog:packages")
async def show_packages_callback(callback: CallbackQuery) -> None:
    async with get_connection() as db:
        packages = await models.get_packages(db)
    await callback.message.edit_text(
        "Виготовлення памятників:", reply_markup=packages_keyboard(packages)
    )


@router.callback_query(F.data.startswith("package:"))
async def show_package_detail(callback: CallbackQuery) -> None:
    package_id = int(callback.data.split(":")[1])
    async with get_connection() as db:
        pkg = await models.get_package(db, package_id)
    if not pkg:
        await callback.answer("Пакет не знайдено.", show_alert=True)
        return
    text = (
        f"<b>{pkg['name']}</b>\n\n"
        f"{pkg['description']}\n\n"
        f"💰 Вартість пакету: <b>{pkg['price']:.0f} грн</b>"
    )
    await callback.message.edit_text(
        text, parse_mode="HTML", reply_markup=package_detail_keyboard(package_id)
    )


# ---------------------------------------------------------------------------
# Контакти (якщо товару немає)
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "contact:manager")
async def contact_manager(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.answer(
        "✍️ Напишіть менеджеру напряму: @manager_username\n"
        "(замініть на реальний username менеджера)"
    )


@router.callback_query(F.data == "contact:phone")
async def contact_phone(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.answer(
        f"📞 Телефон агентства: {settings.AGENCY_PHONE}"
    )


@router.callback_query(F.data == "catalog:back")
async def catalog_back(callback: CallbackQuery) -> None:
    await show_catalog_menu.__wrapped__(callback.message) if hasattr(show_catalog_menu, "__wrapped__") else None
    await callback.message.edit_text(
        "Оберіть розділ каталогу:", reply_markup=_catalog_section_kb()
    )
