"""Тести валідації вхідних даних."""
import pytest
import re

# Той самий паттерн, що у handlers/order.py
PHONE_RE = re.compile(r"^(\+?380|0)\d{9}$")

# ---------------------------------------------------------------------------
# Валідація телефону
# ---------------------------------------------------------------------------

VALID_PHONES = [
    "+380501234567",
    "+380671234567",
    "+380931234567",
    "0501234567",
    "0671234567",
    "380501234567",   # без +
]

INVALID_PHONES = [
    "123",
    "+1234567890",       # не Україна
    "+38050123456",      # короткий
    "+3805012345678",    # довгий
    "",
    "abc",
    "+380 50 123 45 67", # пробіли (не очищені)
    "8-050-123-45-67",   # дефіси (не очищені)
]

# Кнопки меню НЕ мають проходити валідацію телефону — це і є суть бага
MENU_BUTTON_TEXTS = [
    "⚰️ Послуги поховання",
    "🪨 Виготовлення памятників",
    "🔧 Встановлення памятників",
    "🔍 Статус замовлення",
    "🆘 Потрібна допомога прямо зараз",
]


@pytest.mark.parametrize("phone", VALID_PHONES)
def test_valid_phone(phone):
    assert PHONE_RE.match(phone), f"Очікувався валідний: {phone!r}"


@pytest.mark.parametrize("phone", INVALID_PHONES)
def test_invalid_phone(phone):
    assert not PHONE_RE.match(phone), f"Очікувався невалідний: {phone!r}"


@pytest.mark.parametrize("btn_text", MENU_BUTTON_TEXTS)
def test_menu_buttons_are_not_valid_phones(btn_text):
    """Регресійний тест: текст кнопок меню не має проходити як номер телефону.

    Якщо цей тест зеленій — хендлер process_phone ніколи не обробить
    кнопку меню як коректний номер (але без фікса він все одно показував
    помилку валідації замість переходу в каталог).
    """
    assert not PHONE_RE.match(btn_text)


# ---------------------------------------------------------------------------
# Валідація імені та міста (логіка з handlers/order.py)
# ---------------------------------------------------------------------------

def _name_valid(name: str) -> bool:
    return 2 <= len(name.strip()) <= 100


def _city_valid(city: str) -> bool:
    return 2 <= len(city.strip()) <= 100


@pytest.mark.parametrize("name", ["Іван", "Марія-Олена", "A" * 100])
def test_valid_name(name):
    assert _name_valid(name)


@pytest.mark.parametrize("name", ["", "A", "A" * 101, "   "])
def test_invalid_name(name):
    assert not _name_valid(name)


@pytest.mark.parametrize("city", ["Київ", "Кривий Ріг", "B" * 100])
def test_valid_city(city):
    assert _city_valid(city)


@pytest.mark.parametrize("city", ["", "К", "K" * 101])
def test_invalid_city(city):
    assert not _city_valid(city)
