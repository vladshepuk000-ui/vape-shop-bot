"""Часті запитання (FAQ) — відповіді без участі менеджера."""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from keyboards.main_menu import BTN_FAQ

router = Router()

FAQ_ITEMS = [
    (
        "📄 Які документи потрібні для оформлення?",
        "Для оформлення ритуальних послуг зазвичай потрібні:\n"
        "• Свідоцтво про смерть (або довідка лікаря)\n"
        "• Паспорт замовника\n"
        "• Медичне свідоцтво про смерть\n\n"
        "Наш менеджер уточнить повний перелік при дзвінку.",
    ),
    (
        "🚗 Як відбувається забір тіла?",
        "Наша бригада приїжджає в узгоджений час. "
        "Транспортування здійснюється спеціалізованим автомобілем. "
        "Точні деталі менеджер узгодить по телефону.",
    ),
    (
        "⏱ Скільки часу займає організація?",
        "Стандартний термін підготовки — від 1 до 3 діб. "
        "У термінових випадках можливе прискорення. "
        "Менеджер розповість про строки у вашій конкретній ситуації.",
    ),
    (
        "🕐 Чи працюєте ви цілодобово?",
        "Агентство приймає заявки через бота цілодобово. "
        "Менеджери відповідають з 8:00 до 23:00. "
        "У надзвичайних ситуаціях — натисніть кнопку '🆘 Потрібна допомога прямо зараз'.",
    ),
    (
        "⛪️ З якими кладовищами співпрацюєте?",
        "Ми співпрацюємо з більшістю кладовищ регіону. "
        "Точний перелік менеджер надасть при дзвінку залежно від вашого населеного пункту.",
    ),
    (
        "💳 Чи є розстрочка або допомога у пільгах?",
        "Так, ми допомагаємо з оформленням:\n"
        "• Допомоги на поховання від держави\n"
        "• Пільг для окремих категорій громадян\n\n"
        "Зверніться до менеджера — він підкаже, які виплати вам доступні.",
    ),
]


def faq_list_keyboard():
    builder = InlineKeyboardBuilder()
    for i, (question, _) in enumerate(FAQ_ITEMS):
        builder.button(text=question, callback_data=f"faq:{i}")
    builder.adjust(1)
    return builder.as_markup()


def faq_back_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ До запитань", callback_data="faq:list")
    builder.adjust(1)
    return builder.as_markup()


@router.message(lambda m: m.text == BTN_FAQ)
async def show_faq(message: Message) -> None:
    await message.answer(
        "❓ <b>Часті запитання</b>\n\nОберіть запитання:",
        parse_mode="HTML",
        reply_markup=faq_list_keyboard(),
    )


@router.callback_query(F.data == "faq:list")
async def faq_list(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "❓ <b>Часті запитання</b>\n\nОберіть запитання:",
        parse_mode="HTML",
        reply_markup=faq_list_keyboard(),
    )


@router.callback_query(F.data.startswith("faq:") & ~F.data.endswith("list"))
async def faq_answer(callback: CallbackQuery) -> None:
    index = int(callback.data.split(":")[1])
    if index < 0 or index >= len(FAQ_ITEMS):
        await callback.answer("Запитання не знайдено.", show_alert=True)
        return
    question, answer = FAQ_ITEMS[index]
    await callback.message.edit_text(
        f"<b>{question}</b>\n\n{answer}",
        parse_mode="HTML",
        reply_markup=faq_back_keyboard(),
    )
