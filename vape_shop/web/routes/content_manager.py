import os
import aiohttp
import asyncpg
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from web.auth_utils import verify_session

BASE_DIR = os.path.join(os.path.dirname(__file__), "..", "templates")
templates = Jinja2Templates(directory=BASE_DIR)

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
BOT_USERNAME = os.getenv("BOT_USERNAME", "")
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:jHInKjjHzgONUJeWLNNkoxIumLhqIjIs@tramway.proxy.rlwy.net:56512/railway"
)

router = APIRouter(prefix="/content-manager")

PROMPT_TELEGRAM = """Ти — контент-менеджер вейп-шопу. Напиши продаючий пост для Telegram-каналу.
Стиль: живий і дружній, без агресивного продажу.
Виділи ключові характеристики товару і смакові ноти.
Додай заклик написати в бот для замовлення.
Використай емодзі помірно (3–5 штук).
Довжина: 150–220 символів.
Не вигадуй характеристик яких немає у вхідних даних."""

PROMPT_SITE = """Ти — SEO-спеціаліст інтернет-магазину. Напиши опис картки товару.
Структура:
  1. Перше речення — головна перевага товару (містить назву і бренд).
  2. Технічні характеристики — об'єм, склад, міцність якщо є.
  3. Смакова палітра — конкретні ноти (2–3 речення).
Вкажи ключові слова природно (назва товару, бренд).
Обсяг: 80–120 слів. Без "води" і загальних фраз.
Не вигадуй характеристик яких немає у вхідних даних."""


def build_product_description(data: dict) -> str:
    parts = [f"Товар: {data['name']}"]
    if data.get("brand"):
        parts.append(f"Бренд: {data['brand']}")
    if data.get("category"):
        cats = {"liquids": "Рідина", "cartridges": "Картридж", "systems": "Система (под)"}
        parts.append(f"Категорія: {cats.get(data['category'], data['category'])}")
    if data.get("flavor"):
        parts.append(f"Тип смаку: {data['flavor']}")
    if data.get("volume"):
        parts.append(f"Об'єм: {data['volume']} мл")
    if data.get("strength"):
        parts.append(f"Міцність: {data['strength']} мг/мл")
    if data.get("vgpg"):
        parts.append(f"VG/PG: {data['vgpg']}")
    if data.get("price"):
        parts.append(f"Ціна: {data['price']} грн")
    if data.get("notes"):
        parts.append(f"Додатково: {data['notes']}")
    return "\n".join(parts)


async def generate_text(system_prompt: str, product_description: str) -> str:
    if not GROQ_API_KEY:
        return "⚠️ GROQ_API_KEY не налаштований"

    payload = {
        "model": "llama-3.1-8b-instant",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": product_description},
        ],
        "max_tokens": 400,
    }
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://api.groq.com/openai/v1/chat/completions",
            json=payload,
            headers=headers,
        ) as resp:
            data = await resp.json()

    if "error" in data:
        raise Exception(data["error"].get("message", str(data["error"])))

    return data["choices"][0]["message"]["content"].strip()


@router.get("", response_class=HTMLResponse)
async def content_manager_page(request: Request, session: str = Depends(verify_session)):
    if not session:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/login")
    return templates.TemplateResponse("content_manager.html", {"request": request})


@router.post("/generate", response_class=JSONResponse)
async def generate_content(
    request: Request,
    session: str = Depends(verify_session),
    name: str = Form(...),
    brand: str = Form(""),
    category: str = Form("liquids"),
    flavor: str = Form(""),
    volume: str = Form(""),
    strength: str = Form(""),
    vgpg: str = Form(""),
    price: str = Form(""),
    notes: str = Form(""),
):
    if not session:
        return JSONResponse({"error": "Не авторизований"}, status_code=401)

    product_data = {
        "name": name, "brand": brand, "category": category,
        "flavor": flavor, "volume": volume, "strength": strength,
        "vgpg": vgpg, "price": price, "notes": notes,
    }
    description = build_product_description(product_data)

    try:
        tg_text = await generate_text(PROMPT_TELEGRAM, description)
    except Exception as e:
        tg_text = f"⚠️ Помилка генерації: {e}"

    try:
        site_text = await generate_text(PROMPT_SITE, description)
    except Exception as e:
        site_text = f"⚠️ Помилка генерації: {e}"

    return JSONResponse({"telegram": tg_text, "site": site_text})


@router.post("/publish-telegram", response_class=JSONResponse)
async def publish_telegram(
    request: Request,
    session: str = Depends(verify_session),
    text: str = Form(...),
):
    if not session:
        return JSONResponse({"error": "Не авторизований"}, status_code=401)

    if not BOT_TOKEN:
        return JSONResponse({"error": "BOT_TOKEN не налаштований"}, status_code=500)

    # Кнопка "Замовити" — відкриває бота
    reply_markup = None
    if BOT_USERNAME:
        reply_markup = {
            "inline_keyboard": [[
                {"text": "🛒 Замовити", "url": f"https://t.me/{BOT_USERNAME}"}
            ]]
        }

    # Отримати всіх підписаних клієнтів
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        customers = await conn.fetch(
            "SELECT telegram_id FROM customers WHERE is_subscribed = TRUE"
        )
    finally:
        await conn.close()

    if not customers:
        return JSONResponse({"error": "Немає підписаних клієнтів"}, status_code=400)

    sent = 0
    errors = 0
    async with aiohttp.ClientSession() as http:
        for c in customers:
            payload = {
                "chat_id": c["telegram_id"],
                "text": text,
                "parse_mode": "HTML",
            }
            if reply_markup:
                payload["reply_markup"] = reply_markup

            async with http.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json=payload,
            ) as resp:
                data = await resp.json()
                if data.get("ok"):
                    sent += 1
                else:
                    errors += 1

    # Логуємо розсилку в БД
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.execute(
            "INSERT INTO broadcasts (text, sent_count, error_count) VALUES ($1, $2, $3)",
            text, sent, errors
        )
    finally:
        await conn.close()

    return JSONResponse({"ok": True, "sent": sent, "errors": errors})
