import os
import aiohttp
import asyncpg
from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from web.auth_utils import verify_session

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
BOT_USERNAME = os.getenv("BOT_USERNAME", "")

BASE_DIR = os.path.join(os.path.dirname(__file__), "..", "templates")
templates = Jinja2Templates(directory=BASE_DIR)
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:jHInKjjHzgONUJeWLNNkoxIumLhqIjIs@tramway.proxy.rlwy.net:56512/railway"
)

router = APIRouter(prefix="/broadcasts")


@router.get("", response_class=HTMLResponse)
async def broadcasts_list(request: Request, session: str = Depends(verify_session)):
    if not session:
        return RedirectResponse(url="/login")

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        history = await conn.fetch(
            "SELECT * FROM broadcasts ORDER BY created_at DESC LIMIT 20"
        )
        subscribers = await conn.fetchval(
            "SELECT COUNT(*) FROM customers WHERE is_subscribed = TRUE"
        )
    finally:
        await conn.close()

    return templates.TemplateResponse(request, "broadcasts.html", {
        "history": history,
        "subscribers": subscribers,
    })


@router.post("/send", response_class=JSONResponse)
async def send_broadcast(
    request: Request,
    session: str = Depends(verify_session),
    text: str = Form(...),
    add_button: str = Form(default="0"),
):
    if not session:
        return JSONResponse({"error": "Не авторизований"}, status_code=401)
    if not BOT_TOKEN:
        return JSONResponse({"error": "BOT_TOKEN не налаштований"}, status_code=500)

    reply_markup = None
    if add_button == "1" and BOT_USERNAME:
        reply_markup = {
            "inline_keyboard": [[
                {"text": "🛒 Замовити", "url": f"https://t.me/{BOT_USERNAME}"}
            ]]
        }

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        customers = await conn.fetch(
            "SELECT telegram_id FROM customers WHERE is_subscribed = TRUE"
        )
    finally:
        await conn.close()

    if not customers:
        return JSONResponse({"error": "Немає підписаних клієнтів"}, status_code=400)

    sent = errors = 0
    async with aiohttp.ClientSession() as http:
        for c in customers:
            payload = {"chat_id": c["telegram_id"], "text": text, "parse_mode": "HTML"}
            if reply_markup:
                payload["reply_markup"] = reply_markup
            async with http.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json=payload
            ) as resp:
                data = await resp.json()
                if data.get("ok"):
                    sent += 1
                else:
                    errors += 1

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.execute(
            "INSERT INTO broadcasts (text, sent_count, error_count) VALUES ($1, $2, $3)",
            text, sent, errors,
        )
    finally:
        await conn.close()

    return JSONResponse({"ok": True, "sent": sent, "errors": errors})
