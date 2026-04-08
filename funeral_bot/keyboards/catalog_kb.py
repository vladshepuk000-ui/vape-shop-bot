"""Інлайн-клавіатури для каталогу послуг та товарів."""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def services_keyboard(services: list[dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for svc in services:
        builder.button(
            text=f"{svc['name']} — {svc['price']:.0f} грн",
            callback_data=f"service:{svc['id']}",
        )
    builder.button(text="⬅️ Назад", callback_data="catalog:back")
    builder.adjust(1)
    return builder.as_markup()


def categories_keyboard(categories: list[dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for cat in categories:
        builder.button(text=cat["name"], callback_data=f"category:{cat['id']}")
    builder.button(text="⬅️ Назад", callback_data="catalog:back")
    builder.adjust(1)
    return builder.as_markup()


def products_keyboard(products: list[dict], category_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for p in products:
        label = p["name"]
        if p["is_custom"]:
            label += " 🔧"
        builder.button(text=label, callback_data=f"product:{p['id']}")
    builder.button(text="⬅️ До категорій", callback_data="catalog:categories")
    builder.adjust(1)
    return builder.as_markup()


def product_detail_keyboard(product_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📝 Замовити цей товар", callback_data=f"order_product:{product_id}")
    builder.button(text="✍️ Написати менеджеру", callback_data="contact:manager")
    builder.button(text="📞 Зателефонувати", callback_data="contact:phone")
    builder.button(text="⬅️ Назад", callback_data="catalog:categories")
    builder.adjust(1)
    return builder.as_markup()


def packages_keyboard(packages: list[dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for pkg in packages:
        builder.button(
            text=f"{pkg['name']} — {pkg['price']:.0f} грн",
            callback_data=f"package:{pkg['id']}",
        )
    builder.button(text="⬅️ Назад", callback_data="catalog:back")
    builder.adjust(1)
    return builder.as_markup()


def package_detail_keyboard(package_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📝 Замовити пакет", callback_data=f"order_package:{package_id}")
    builder.button(text="⬅️ До пакетів", callback_data="catalog:packages")
    builder.adjust(1)
    return builder.as_markup()
