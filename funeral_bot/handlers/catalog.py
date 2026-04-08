"""Хендлери каталогу: послуги, категорії, товари, памятники."""
import logging
from pathlib import Path

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InputMediaPhoto
from aiogram.types import FSInputFile

from db.database import get_connection
from db import models
from keyboards.main_menu import BTN_CATALOG, BTN_PACKAGES, BTN_ORDER
from keyboards.catalog_kb import (
    categories_keyboard,
    products_keyboard,
    product_detail_keyboard,
)
from config import settings

logger = logging.getLogger(__name__)

# Папка з фото відносно цього файлу: funeral_bot/assets/images/
IMAGES_DIR = Path(__file__).parent.parent / "assets" / "images"

router = Router()

NO_ITEMS_TEXT = "Наразі в каталозі немає доступних позицій. Зверніться до менеджера."


# ---------------------------------------------------------------------------
# Каталог послуг
# ---------------------------------------------------------------------------

BURIAL_INFO_TEXT = (
    "🕊️ <b>Комплекс послуг з поховання</b>\n\n"
    "📦 <b>Базовий пакет — від 8 000 грн</b>\n"
    "• <b>Транспортування:</b> Перевезення тіла з дому безпосередньо до місця поховання.\n"
    "• <b>Підготовка місця:</b> Професійне викопування та засипання могили.\n\n"
    "➕ <b>Додаткові послуги:</b>\n\n"
    "🚐 <b>Транспортні послуги (Морг):</b>\n"
    "• Перевезення з дому до моргу або з моргу до місця поховання/додому — +500 грн.\n\n"
    "🏛️ <b>Облаштування місця прощання:</b>\n"
    "• Повний комплект (захисний намет + ритуальні столики та підставки) — 500 грн.\n\n"
    "🛠️ <b>Демонтаж та підготовка ділянки:</b>\n"
    "• Демонтаж старих елементів: Прибирання столиків, лавок чи інших конструкцій — від 500 грн.\n"
    "• Розчищення місця: Спилювання та видалення дерев, чагарників — від 800 грн.\n\n"
    "Для замовлення або консультації звертайтесь до адміністратора."
)


@router.message(lambda m: m.text == BTN_CATALOG)
async def show_catalog_menu(message: Message) -> None:
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text="📝 Оформити замовлення", callback_data="order_burial")
    await message.answer(BURIAL_INFO_TEXT, parse_mode="HTML", reply_markup=builder.as_markup())


INSTALLATION_CAPTION = (
    "🪦 <b>Встановлення пам'ятників</b>\n\n"
    "🏗️ <b>Стандартна установка — від 8 000 грн</b>\n"
    "(Розміри: 1.20м x 1.60м, товщина 15 см. Включає підготовку та монтаж).\n\n"
    "🛠️ <b>Додаткові роботи:</b>\n"
    "• Демонтаж: від 1 000 грн.\n"
    "• Тротуарна плитка (фото 1-2): від 3 000 грн.\n"
    "• Облицювальна плитка (фото 3-4): від 8 000 грн.\n\n"
    "На фото представлені наші роботи з укладання різних видів плитки."
)

def _installation_photos() -> list[Path]:
    folder = IMAGES_DIR / "plitky"
    if not folder.exists():
        return []
    files = sorted(folder.iterdir(), key=lambda f: f.name)
    # тротуарна першими, потім обліцовочна, решта в кінці
    trot = [f for f in files if "тратуарна" in f.name.lower() or "тротуарна" in f.name.lower()]
    oblic = [f for f in files if "обліц" in f.name.lower() or "облиц" in f.name.lower()]
    rest = [f for f in files if f not in trot and f not in oblic]
    return trot + oblic + rest


@router.message(lambda m: m.text == BTN_ORDER)
async def show_installation_menu(message: Message) -> None:
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InputMediaPhoto, FSInputFile

    photos = _installation_photos()

    if not photos:
        builder = InlineKeyboardBuilder()
        builder.button(text="📝 Оформити замовлення", callback_data="order_installation")
        await message.answer(INSTALLATION_CAPTION, parse_mode="HTML", reply_markup=builder.as_markup())
        return

    # Перше фото — з підписом і кнопкою, решта без підпису (MediaGroup не підтримує кнопки)
    # Відправляємо альбом, потім окремо кнопку
    media = []
    for i, path in enumerate(photos):
        caption = INSTALLATION_CAPTION if i == 0 else None
        media.append(InputMediaPhoto(
            media=FSInputFile(str(path)),
            caption=caption,
            parse_mode="HTML" if i == 0 else None,
        ))

    sent = await message.answer_media_group(media=media)

    # Зберігаємо file_id для наступних відправок
    async with get_connection() as db:
        for path, msg in zip(photos, sent):
            if msg.photo:
                await models.save_monument_file_id(db, "plitky", path.name, msg.photo[-1].file_id)

    builder = InlineKeyboardBuilder()
    builder.button(text="📝 Оформити замовлення", callback_data="order_installation")
    await message.answer("Для замовлення:", reply_markup=builder.as_markup())


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
# Виготовлення памятників
# ---------------------------------------------------------------------------

MONUMENTS = [
    ("Дитячі ексклюзивні",   "DE"),
    ("Дитячі класичні",      "DS"),
    ("Дитячі комбіновані",   "DK"),
    ("Одинарні ексклюзивні", "OE"),
    ("Одинарні класичні",    "OS"),
    ("Одинарні комбіновані", "OK"),
    ("Подвійні ексклюзивні", "PE"),
    ("Подвійні класичні",    "PS"),
    ("Подвійні комбіновані", "PK"),
]


def _monuments_list_keyboard():
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    for name, code in MONUMENTS:
        builder.button(text=f"{code} — {name}", callback_data=f"monument:{code}")
    builder.adjust(1)
    return builder.as_markup()


def _photo_nav_keyboard(code: str, index: int, total: int):
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    if total > 1:
        prev_idx = (index - 1) % total
        next_idx = (index + 1) % total
        builder.button(text="←", callback_data=f"mon_nav:{code}:{prev_idx}")
        builder.button(text=f"{index + 1} / {total}", callback_data="mon_nav_noop")
        builder.button(text="→", callback_data=f"mon_nav:{code}:{next_idx}")
        builder.adjust(3)
    builder.button(text="📝 Замовити", callback_data=f"order_monument:{code}:{index}")
    builder.button(text="↩ До списку", callback_data="monuments_list")
    builder.adjust(3, 1, 1)
    return builder.as_markup()


def _get_photo_files(code: str) -> list[Path]:
    folder = IMAGES_DIR / code
    if not folder.exists():
        return []
    return sorted(f for f in folder.iterdir() if f.suffix.lower() in (".jpg", ".jpeg", ".png"))


@router.message(lambda m: m.text == BTN_PACKAGES)
async def show_monuments(message: Message) -> None:
    await message.answer("Оберіть вид памятника:", reply_markup=_monuments_list_keyboard())


@router.callback_query(F.data == "monuments_list")
async def back_to_monuments_list(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.delete()
    await callback.message.answer("Оберіть вид памятника:", reply_markup=_monuments_list_keyboard())


@router.callback_query(F.data == "mon_nav_noop")
async def nav_noop(callback: CallbackQuery) -> None:
    await callback.answer()


@router.callback_query(F.data.startswith("monument:"))
async def show_monument_photos(callback: CallbackQuery) -> None:
    code = callback.data.split(":")[1]
    await callback.answer()
    await _show_photo(callback, code, 0, first=True)


@router.callback_query(F.data.startswith("mon_nav:"))
async def navigate_monument_photos(callback: CallbackQuery) -> None:
    _, code, idx_str = callback.data.split(":")
    await callback.answer()
    await _show_photo(callback, code, int(idx_str), first=False)


async def _show_photo(callback: CallbackQuery, code: str, index: int, first: bool) -> None:
    """Відправляє або оновлює фото памятника з кнопками навігації."""
    files = _get_photo_files(code)
    if not files:
        await callback.message.answer("Фото для цього розділу поки не додані.")
        return

    total = len(files)
    index = max(0, min(index, total - 1))
    file_path = files[index]
    filename = file_path.name
    name = next((n for n, c in MONUMENTS if c == code), code)
    caption = f"<b>{code} — {name}</b>\n{index + 1} / {total}\n\n💰 Ціна уточнюється у менеджера по телефону"
    nav_kb = _photo_nav_keyboard(code, index, total)

    # Беремо file_id з кешу БД якщо є
    async with get_connection() as db:
        cached_file_id = await models.get_monument_file_id(db, code, filename)

    media_source = cached_file_id if cached_file_id else FSInputFile(str(file_path))

    if first:
        # Перший показ: видаляємо текстове меню, відправляємо фото
        await callback.message.delete()
        sent = await callback.message.answer_photo(
            photo=media_source,
            caption=caption,
            parse_mode="HTML",
            reply_markup=nav_kb,
        )
    else:
        # Навігація: редагуємо існуюче фото
        sent = await callback.message.edit_media(
            media=InputMediaPhoto(media=media_source, caption=caption, parse_mode="HTML"),
            reply_markup=nav_kb,
        )

    # Зберігаємо file_id після першої відправки з диску
    if not cached_file_id and sent.photo:
        new_file_id = sent.photo[-1].file_id
        async with get_connection() as db:
            await models.save_monument_file_id(db, code, filename, new_file_id)
        logger.info("Збережено file_id для %s/%s", code, filename)



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
