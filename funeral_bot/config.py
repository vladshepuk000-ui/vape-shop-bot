"""Конфігурація бота — завантаження змінних з .env файлу."""
import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    
    # Превращаем строку ID в список чисел
    admin_str = os.getenv("ADMIN_IDS", "")
    ADMIN_IDS = [int(id_str.strip()) for id_str in admin_str.split(",") if id_str.strip().isdigit()]
    
    MANAGER_CHAT_ID = os.getenv("MANAGER_CHAT_ID")
    AGENCY_PHONE = os.getenv("AGENCY_PHONE")
    AGENCY_ADDRESS = os.getenv("AGENCY_ADDRESS")
    DB_NAME = "funeral_agency.db"


settings = Settings()