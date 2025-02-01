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

# Функция обработчика проверки версии
async def check_version(update: Update, context: CallbackContext):
    """Проверяет текущую версию локального файла и версию на сервере (GitHub)."""
    logger.info("Обработка кнопки 'Проверить версию'.")
    # Получаем версию локального файла
    local_version = extract_version_from_file(LOCAL_FILE_PATH)
    logger.info(f"Локальная версия: {local_version}")
    # Получаем версию удалённого файла
    remote_version = await check_remote_version()
    # Сравниваем версии
    if local_version == remote_version:
        version_status = "✅  Обновлений не обнаружено"
    else:
        version_status = f"📥  Обнаружена новая версия на GitHub: {remote_version}"
    # Формируем сообщение
    message = f"🗂️ Версия локального файла: {local_version}\n" \
              f"🌐 Версия на сервере (GitHub): {remote_version}\n" \
              f"{version_status}"
    if update.callback_query:
        await update.callback_query.message.reply_text(message)

async def check_commits(update: Update, context: CallbackContext):
    """Проверка коммитов в репозитории GitHub."""
    logger.info("Обработка кнопки 'Проверить последние коммиты'.")
    commits = await get_commits_from_github(REPO_URL)
    # Если коммиты были получены
    if commits:
        # Извлекаем заголовок с датой, количеством коммитов и список коммитов
        header = commits[0]
        commits_message = "\n".join(commits[1:])
        commits_message = f"{header}\n{commits_message}"
    else:
        commits_message = "Нет коммитов за этот период."
    if update.callback_query:  # Проверяем, существует ли callback_query
        logger.info(f"Отправка сообщения: {commits_message}")
        await update.callback_query.message.reply_text(commits_message)

async def get_commits_from_github(repo_url):
    """Получает коммиты из репозитория на GitHub, сделанные за последнюю дату, когда они были выложены."""
    # Формируем URL для запроса к API GitHub
    api_url = f"https://api.github.com/repos/{repo_url}/commits?per_page=100"  # Получаем 100 коммитов для анализа
    async with aiohttp.ClientSession() as session:
        try:
            # Отправляем запрос на GitHub API
            async with session.get(api_url) as response:
                response.raise_for_status()  # Проверка на успешный статус ответа
                commits = await response.json()  # Парсим JSON ответ
                if not commits:
                    return ["Нет коммитов в репозитории."]
                # Сортируем коммиты по дате в порядке убывания
                commits.sort(key=lambda x: x['commit']['author']['date'], reverse=True)
                # Получаем дату последнего коммита
                last_commit_date = datetime.fromisoformat(commits[0]['commit']['author']['date'].replace('Z', '+00:00')).date()
                # Извлекаем только те коммиты, которые были сделаны в последний день
                filtered_commits = [
                    commit for commit in commits
                    if datetime.fromisoformat(commit['commit']['author']['date'].replace('Z', '+00:00')).date() == last_commit_date
                ]
                # Формируем список коммитов с нужной информацией
                tz = pytz.timezone(TIMEZONE)
                commit_list = [
                    f"{commit['sha'][:7]} {commit['commit']['message']} at {datetime.fromisoformat(commit['commit']['author']['date'].replace('Z', '+00:00')).astimezone(tz).strftime('%H:%M:%S')}"
                    for commit in filtered_commits
                ]
                if not commit_list:
                    return [f"Нет коммитов на {last_commit_date}."]
                # Заголовок с эмодзи, датой и количеством коммитов
                header = f"📜 Последние коммиты от {last_commit_date} ({len(filtered_commits)} коммитов)"
                # Возвращаем заголовок и список коммитов
                return [header] + commit_list
        except aiohttp.ClientError as e:
            logger.error(f"Ошибка при запросе к GitHub API: {e}")
            return ["Ошибка при получении коммитов."]
        except Exception as e:
            logger.error(f"Неизвестная ошибка: {e}")
            return ["Не удалось получить данные о коммитах."]