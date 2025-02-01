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
from config.settings import *
from config.logging_config import logger

# Функция для преобразования времени в удобный формат
def format_time_interval(seconds):
    """Преобразует интервал времени в формат 'часы:минуты:секунды'."""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60
    if hours > 0:
        return f"{hours} ч. {minutes} мин. {seconds} сек."
    elif minutes > 0:
        return f"{minutes} мин. {seconds} сек."
    else:
        return f"{seconds} сек."

# Функция start с обновленной информацией
async def start(update: Update, context: CallbackContext):
    """Отправляет стартовое сообщение и кнопки для выбора действий."""
    await log_telegram_message(update)  # Логируем входящее сообщение
    logger.info("Бот получил команду /start")
    # Получаем версию локального файла
    local_version = extract_version_from_file(LOCAL_FILE_PATH)
    # Логируем версию локального файла
    logger.info(f"Локальная версия: {local_version}")
    # Получаем версию файла с сервера
    try:
        server_file_content = await fetch_file_content(REPO_URL, REMOTE_FILE_PATH)
        server_version = extract_version_from_content(server_file_content)
    except Exception as e:
        logger.error(f"Ошибка при скачивании файла для получения версии: {e}")
        server_version = "Не удалось получить версию с сервера"
    # Логируем версию с сервера
    logger.info(f"Версия на сервере: {server_version}")
    # Сравниваем версии
    if local_version == server_version:
        version_status = "✅  Обновлений не обнаружено"
    else:
        version_status = f"📥 Обнаружена новая версия на GitHub: {server_version}"
    # Преобразуем интервал в более удобный формат
    formatted_check_interval = format_time_interval(CHECK_INTERVAL)
    # Формируем стартовое сообщение
    start_message = (
        "🤖 Добро пожаловать!\n"
        f"Версия телеграмм бота: {BOT_VERSION}\n"
        "Этот бот создан для мониторинга обновлений стратегии NostalgiaForInfinityX5.\n\n"
        f"📊  Стартовая информация:\n"
        f"📂  Версия локального файла: {local_version}\n"
        f"🌐  Версия на сервере: {server_version}\n"
        f"{version_status}\n"
        f"🕒  Интервал проверки обновлений: {formatted_check_interval}\n\n"
        "📌 Основные функции:\n"
        "1️⃣ Проверка актуальной версии файла.\n"
        "2️⃣ Загрузка обновлений стратегии.\n"
        "3️⃣ Отображение последних коммитов из GitHub.\n"
        "4️⃣ Перезапуск Freqtrade после обновления.\n\n"
        "Используйте кнопки ниже для управления."
    )
    # Отправляем стартовое сообщение и кнопки
    keyboard = [
        [InlineKeyboardButton("🔍 Проверить версию файла", callback_data='check_version')],
        [InlineKeyboardButton("📥 Скачать обновление", callback_data='download_file')],
        [InlineKeyboardButton("📜 Последние коммиты", callback_data='check_commits')],
        [InlineKeyboardButton("🔄 Перезапустить Freqtrade", callback_data='reload_freqtrade')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.message:
        await update.message.reply_text(start_message, reply_markup=reply_markup)