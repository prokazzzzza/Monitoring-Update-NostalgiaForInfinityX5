from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackContext, CallbackQueryHandler
from datetime import datetime, timedelta
from dotenv import load_dotenv
import requests
import logging
import aiohttp
import asyncio
import pytz
import re
import os
from app.monitoring import *
from app.strategy import *
from app.handlers import *
from app.utils import *
from config.settings import *
from config.logging_config import logger

def main():
    """Основная функция для запуска бота и периодической проверки обновлений."""
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    # Добавляем все обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(check_version, pattern='check_version'))
    application.add_handler(CallbackQueryHandler(download_file, pattern='download_file'))
    application.add_handler(CallbackQueryHandler(check_commits, pattern='check_commits'))
    application.add_handler(CallbackQueryHandler(reload_freqtrade, pattern='reload_freqtrade'))
    # Запускаем фоновую задачу для проверки обновлений
    asyncio.get_event_loop().create_task(periodic_update_check())
    # Запускаем Telegram бота
    application.run_polling()

if __name__ == "__main__":
    main()