import os
import logging
from datetime import date
import asyncpg
import aiohttp
from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import StateFilter
from aiogram.fsm.state import default_state

router = Router()
logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:jHInKjjHzgONUJeWLNNkoxIumLhqIjIs@tramway.proxy.rlwy.net:56512/railway"
)

SYSTEM_PROMPT = (
    "Ти — помічник вейп-шопу. Відповідай українською мовою, коротко і по суті. "
    "Допомагай клієнтам обирати рідини, картриджі та системи (поди). "
    "Якщо питають про каталог або ціни — пропонуй переглянути /start. "
    "Якщо питають про замовлення або статус — пропонуй написати продавцю @Vlad_shepuk. "
    "Не вигадуй конкретних цін чи назв товарів — посилайся на каталог. "
    "Будь дружнім і лаконічним."
)


async def get_daily_usage(conn, customer_id: int) -> int:
    today = date.today()
    row = await conn.fetchrow(
        "SELECT count FROM ai_usage WHERE customer_id = $1 AND date = $2",
        customer_id, today
    )
    return row["count"] if row else 0


async def increment_daily_usage(conn, customer_id: int):
    today = date.today()
    await conn.execute("""
        INSERT INTO ai_usage (customer_id, date, count) VALUES ($1, $2, 1)
        ON CONFLICT (customer_id, date) DO UPDATE SET count = ai_usage.count + 1
    """, customer_id, today)


async def get_chat_history(conn, customer_id: int) -> list[dict]:
    rows = await conn.fetch("""
        SELECT role, content FROM ai_chat_history
        WHERE customer_id = $1
        ORDER BY created_at DESC
        LIMIT 4
    """, customer_id)
    return [{"role": r["role"], "parts": [r["content"]]} for r in reversed(rows)]


async def save_message(conn, customer_id: int, role: str, content: str):
    await conn.execute(
        "INSERT INTO ai_chat_history (customer_id, role, content) VALUES ($1, $2, $3)",
        customer_id, role, content
    )


async def get_catalog_context() -> str:
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        products = await conn.fetch(
            "SELECT name, description, price, stock FROM products WHERE is_active = TRUE ORDER BY category"
        )
    finally:
        await conn.close()

    if not products:
        return "Каталог порожній. Товарів немає."

    in_stock = [p for p in products if p["stock"] > 0]
    out_stock = [p for p in products if p["stock"] == 0]

    lines = [
        "=== АКТУАЛЬНИЙ КАТАЛОГ (дані з бази даних, оновлено щойно) ===",
        "",
        "В НАЯВНОСТІ (можна замовити):",
    ]
    for p in in_stock:
        lines.append(f"  + {p['name']} — {p['price']} грн")

    if out_stock:
        lines.append("")
        lines.append("НЕМАЄ В НАЯВНОСТІ (не можна замовити):")
        for p in out_stock:
            lines.append(f"  - {p['name']}")

    lines.append("")
    lines.append("ВАЖЛИВО: Не вигадуй інші товари. Є тільки те що вказано вище.")
    return "\n".join(lines)


@router.message(StateFilter(default_state), F.text)
async def handle_ai_message(message: Message):
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key or api_key == "your_groq_api_key_here":
        return

    ai_daily_limit = int(os.getenv("AI_DAILY_LIMIT", "30"))
    user_text = message.text.strip()

    if user_text.startswith("/"):
        return

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        customer = await conn.fetchrow(
            "SELECT id FROM customers WHERE telegram_id = $1",
            message.from_user.id
        )

        if not customer:
            logger.warning(f"Клієнт {message.from_user.id} не знайдений в БД")
            await message.answer("Спочатку натисни /start")
            return

        customer_id = customer["id"]

        usage = await get_daily_usage(conn, customer_id)
        if usage >= ai_daily_limit:
            await message.answer(
                f"⚠️ Ти вичерпав ліміт AI-запитів на сьогодні ({ai_daily_limit}).\n"
                "Спробуй завтра або напиши продавцю: @Vlad_shepuk"
            )
            return

        history = await get_chat_history(conn, customer_id)
        await save_message(conn, customer_id, "user", user_text)
        await increment_daily_usage(conn, customer_id)
    finally:
        await conn.close()

    await message.bot.send_chat_action(message.chat.id, "typing")

    try:
        catalog = await get_catalog_context()
        system_with_catalog = f"{SYSTEM_PROMPT}\n\n{catalog}"

        messages = [{"role": "system", "content": system_with_catalog}]
        for h in history:
            role = "assistant" if h["role"] == "model" else h["role"]
            messages.append({"role": role, "content": h["parts"][0]})
        messages.append({"role": "user", "content": user_text})

        payload = {
            "model": "llama-3.1-8b-instant",
            "messages": messages,
            "max_tokens": 250,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.groq.com/openai/v1/chat/completions",
                json=payload,
                headers=headers
            ) as resp:
                data = await resp.json()

        if "error" in data:
            raise Exception(data["error"].get("message", str(data["error"])))

        reply = data["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"Groq API error: {e}")
        await message.answer(
            "⚠️ Не вдалось отримати відповідь. Спробуй ще раз або напиши @Vlad_shepuk"
        )
        return

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await save_message(conn, customer_id, "model", reply)
    finally:
        await conn.close()

    await message.answer(reply)
