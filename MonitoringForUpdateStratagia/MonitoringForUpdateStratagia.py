from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackContext, CallbackQueryHandler
import os
import requests
import hashlib
import time
import re
from dotenv import load_dotenv
import logging
import aiohttp
import asyncio
import pytz
from datetime import datetime, timedelta

# Настроим логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Загружаем переменные окружения из .env
load_dotenv()

# Настройки
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
FREQTRADE_BOT_TOKEN = os.getenv("FREQTRADE_BOT_TOKEN")
FREQTRADE_CHAT_ID = os.getenv("FREQTRADE_CHAT_ID")

FILE_URL = os.getenv("FILE_URL")
LOCAL_FILE_PATH = os.getenv("LOCAL_FILE_PATH")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL"))
RETRY_LIMIT = int(os.getenv("RETRY_LIMIT"))
RETRY_DELAY = int(os.getenv("RETRY_DELAY"))
REPO_URL = os.getenv("REPO_URL")

# Логирование входящих сообщений
async def log_telegram_message(update: Update):
    """Логирует входящие сообщения в Telegram."""
    if update.message:
        logger.info(f"Входящее сообщение от {update.message.from_user.username} ({update.message.from_user.id}): {update.message.text}")
    elif update.callback_query:
        logger.info(f"Входящий callback от {update.callback_query.from_user.username} ({update.callback_query.from_user.id}): {update.callback_query.data}")

# Логирование отправки сообщений
def send_telegram_message(token, chat_id, message):
    """Отправляет сообщение в Telegram и логирует ответ."""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message}
    response = requests.post(url, json=payload)
    logger.info(f"Отправка сообщения: {message}")
    logger.info(f"Ответ от Telegram API: {response.text}")
    response.raise_for_status()  # Если произошла ошибка, выбросит исключение

# Заменить синхронные запросы на асинхронные
async def download_file_with_retries(url, save_path, retries=RETRY_LIMIT, delay=RETRY_DELAY):
    """Асинхронная версия загрузки файла с повторными попытками."""
    async with aiohttp.ClientSession() as session:
        for attempt in range(1, retries + 1):
            try:
                logger.info(f"Попытка {attempt}/{retries} загрузки...")
                async with session.get(url) as response:
                    response.raise_for_status()  # Вызывает ошибку при неудачном ответе
                    with open(save_path, "wb") as f:
                        f.write(await response.read())
                logger.info("Файл успешно загружен.")
                return
            except Exception as e:
                logger.error(f"Попытка {attempt}/{retries} не удалась: {e}")
                if attempt < retries:
                    await asyncio.sleep(delay)  # Задержка перед следующей попыткой
                else:
                    logger.error("Все попытки исчерпаны.")
                    raise

def extract_version_from_line(file_path, line_number=69):
    """Извлекает версию файла из указанной строки."""
    if not os.path.exists(file_path):
        return "Файл не найден"
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            lines = file.readlines()
            if len(lines) >= line_number:
                line = lines[line_number - 1].strip()  # Получаем 69-ю строку
                match = re.search(r'return\s+[\'\"](v[\d.]+)[\'\"]', line)
                return match.group(1) if match else "Неизвестная версия"
    except Exception as e:
        logger.error(f"Ошибка при извлечении версии: {e}")
    return "Неизвестная версия"

async def check_version(update: Update, context: CallbackContext):
    """Проверяет текущую версию локального файла и версию на сервере (GitHub)."""
    logger.info("Обработка кнопки 'Проверить версию'.")
    
    # Получаем версию локального файла
    local_version = extract_version_from_line(LOCAL_FILE_PATH)
    
    # Логируем версию локального файла
    logger.info(f"Локальная версия: {local_version}")
    
    # Получаем версию файла с сервера
    try:
        server_file_content = download_file_with_retries(FILE_URL, LOCAL_FILE_PATH, retries=1, delay=0)
        server_version = extract_version_from_line(LOCAL_FILE_PATH)
    except Exception as e:
        logger.error(f"Ошибка при скачивании файла для получения версии: {e}")
        server_version = "Не удалось получить версию с сервера"
    
    # Логируем версию с сервера
    logger.info(f"Версия на сервере: {server_version}")
    
    # Сравниваем версии
    if local_version == server_version:
        version_status = "✅  Обновлений не обнаружено"
    else:
        version_status = f"📥  Обнаружена новая версия на GitHub: {server_version}"

    # Отправляем сообщение в Telegram
    message = f"Версия локального файла: {local_version}\n" \
              f"Версия на сервере (GitHub): {server_version}\n" \
              f"{version_status}"

    if update.callback_query:  # Проверяем, существует ли callback_query
        logger.info("Отправка сообщения с результатами проверки версии.")
        await update.callback_query.message.reply_text(message)

async def get_commits_from_github(repo_url):
    """Получает последние коммиты из репозитория на GitHub."""
    api_url = f"https://api.github.com/repos/{repo_url}/commits?per_page=5"
    response = requests.get(api_url)
    
    if response.status_code == 200:
        commits = response.json()
        return [f"Коммит: {commit['sha']} - {commit['commit']['message']}" for commit in commits]
    else:
        return ["Не удалось получить данные о коммитах."]

async def check_commits(update: Update, context: CallbackContext):
    """Проверка коммитов в репозитории GitHub."""
    await log_telegram_message(update)  # Логируем входящее сообщение
    logger.info("Обработка кнопки 'Проверить последние коммиты'.")
    commits = await get_commits_from_github(REPO_URL)
    commits_message = "\n".join(commits)
    if update.callback_query:  # Проверяем, существует ли callback_query
        logger.info(f"Отправка сообщения: Последние коммиты:\n{commits_message}")
        await update.callback_query.message.reply_text(f"Последние коммиты:\n{commits_message}")

async def reload_freqtrade(update: Update, context: CallbackContext):
    """Отправка команды на перезапуск Freqtrade в другой бот."""
    await log_telegram_message(update)  # Логируем входящее сообщение
    logger.info("Обработка кнопки 'Перезапустить Freqtrade'.")
    try:
        send_telegram_message(FREQTRADE_BOT_TOKEN, FREQTRADE_CHAT_ID, "/reload_config")  # Отправка команды
        message = "Команда перезапуска Freqtrade отправлена"
        if update.callback_query:  # Проверяем, существует ли callback_query
            await update.callback_query.message.reply_text(message)
        logger.info("Команда на перезапуск Freqtrade успешно отправлена.")
    except Exception as e:
        logger.error(f"Ошибка при отправке команды перезапуска: {e}")
        if update.callback_query:  # Проверяем, существует ли callback_query
            await update.callback_query.message.reply_text(f"❌  Не удалось отправить команду: {e}")

# Использовать только асинхронные версии загрузки
async def download_file(update: Update, context: CallbackContext):
    """Принудительно загружает файл с сервера, если версия устарела."""
    logger.info("Обработка кнопки 'Скачать обновление'.")
    try:
        # Получаем версию локального файла
        local_version = extract_version_from_line(LOCAL_FILE_PATH)
        
        # Получаем версию файла с сервера
        await download_file_with_retries(FILE_URL, LOCAL_FILE_PATH, retries=1, delay=0)  # Асинхронная загрузка файла
        server_version = extract_version_from_line(LOCAL_FILE_PATH)
        
        if local_version == server_version:
            # Если версии совпадают, уведомляем, что обновление не требуется
            message = f"Версия локального файла ({local_version}) актуальна. Обновление не требуется."
            if update.callback_query:  # Проверяем, существует ли callback_query
                await update.callback_query.message.reply_text(message)
            logger.info("Обновление не требуется. Версия актуальна.")
        else:
            # Если версии разные, загружаем новую версию
            await download_file_with_retries(FILE_URL, LOCAL_FILE_PATH)  # Асинхронная загрузка файла
            message = f"✅  Новая версия ({server_version}) успешно загружена!"
            if update.callback_query:  # Проверяем, существует ли callback_query
                await update.callback_query.message.reply_text(message)
            logger.info("Новая версия успешно загружена.")
    
    except Exception as e:
        logger.error(f"Ошибка при скачивании файла: {e}")
        if update.callback_query:  # Проверяем, существует ли callback_query
            await update.callback_query.message.reply_text(f"❌  Не удалось загрузить файл: {e}")

def show_start_info():
    """Отображает стартовую информацию о версии файлов и времени проверки."""
    # Получаем версию локального файла
    local_version = extract_version_from_line(LOCAL_FILE_PATH)
    
    # Логируем версию локального файла
    logger.info(f"Локальная версия: {local_version}")
    
    # Получаем версию файла с сервера
    try:
        server_file_content = download_file_with_retries(FILE_URL, LOCAL_FILE_PATH, retries=1, delay=0)
        server_version = extract_version_from_line(LOCAL_FILE_PATH)
    except Exception as e:
        logger.error(f"Ошибка при скачивании файла для получения версии: {e}")
        server_version = "Не удалось получить версию с сервера"
    
    # Логируем версию с сервера
    logger.info(f"Версия на сервере: {server_version}")
    
    # Сравниваем версии
    if local_version == server_version:
        version_status = "✅  Обновлений не обнаружено"
    else:
        version_status = f"📥  Обнаружена новая версия на GitHub: {server_version}"

    # Время следующей проверки с учетом часового пояса UTC+3
    tz = pytz.timezone('Europe/Moscow')  # Устанавливаем часовой пояс
    now = datetime.now(tz)  # Текущее время с часовым поясом
    next_check_time = now + timedelta(seconds=CHECK_INTERVAL)  # Добавляем интервал проверки

    # Убираем временную зону и миллисекунды
    next_check_time = next_check_time.replace(microsecond=0, tzinfo=None)   # Убираем информацию о временной зоне
    next_check_time_str = next_check_time.strftime('%d-%m-%Y %H:%M:%S')  # Форматируем

    # Формируем сообщение
    start_message = (
        f"📊  Стартовая информация:\n"
        f"📂  Версия локального файла: {local_version}\n"
        f"🌐  Версия на сервере: {server_version}\n"
        f"{version_status}\n"
        f"🕒  Время следующей проверки: {next_check_time}\n\n"
        f"/start\n"
    )
    # Отправляем стартовое сообщение и кнопки
    keyboard = [
        [InlineKeyboardButton("🔍 Проверить версию локального файла", callback_data='check_version')],
        [InlineKeyboardButton("📥 Скачать обновление", callback_data='download_file')],
        [InlineKeyboardButton("📜 Последние коммиты", callback_data='check_commits')],
        [InlineKeyboardButton("🔄 Перезапустить Freqtrade", callback_data='reload_freqtrade')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Отправляем сообщение в Telegram
    send_telegram_message(TELEGRAM_TOKEN, CHAT_ID, start_message)
    
    # Печатаем информацию в консоль
    logger.info(start_message)

async def start(update: Update, context: CallbackContext):
    """Отправляет стартовую информацию и кнопки для выбора действий."""
    await log_telegram_message(update)  # Логируем входящее сообщение
    logger.info("Бот получил команду /start")

    # Получаем версию локального файла
    local_version = extract_version_from_line(LOCAL_FILE_PATH)
    
    # Логируем версию локального файла
    logger.info(f"Локальная версия: {local_version}")
    
    # Получаем версию файла с сервера
    try:
        server_file_content = download_file_with_retries(FILE_URL, LOCAL_FILE_PATH, retries=1, delay=0)
        server_version = extract_version_from_line(LOCAL_FILE_PATH)
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

    # Время следующей проверки
    next_check_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time() + CHECK_INTERVAL))
    
    # Формируем стартовое сообщение
    start_message = (
        f"📊  Стартовая информация:\n"
        f"📂  Версия локального файла: {local_version}\n"
        f"🌐  Версия на сервере: {server_version}\n"
        f"{version_status}\n"
        f"🕒  Время следующей проверки: {next_check_time}\n\n"
        "Выберите действие:"
    )

    # Отправляем стартовое сообщение и кнопки
    keyboard = [
        [InlineKeyboardButton("🔍 Проверить версию локального файла", callback_data='check_version')],
        [InlineKeyboardButton("📥 Скачать обновление", callback_data='download_file')],
        [InlineKeyboardButton("📜 Последние коммиты", callback_data='check_commits')],
        [InlineKeyboardButton("🔄 Перезапустить Freqtrade", callback_data='reload_freqtrade')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.message:
        await update.message.reply_text(start_message, reply_markup=reply_markup)

def main():
    """Основная функция для запуска бота."""
    # Выводим стартовую информацию сразу при старте
    show_start_info()

    # Запускаем бота
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(check_version, pattern='check_version'))
    application.add_handler(CallbackQueryHandler(download_file, pattern='download_file'))
    application.add_handler(CallbackQueryHandler(check_commits, pattern='check_commits'))
    application.add_handler(CallbackQueryHandler(reload_freqtrade, pattern='reload_freqtrade'))

    application.run_polling()

if __name__ == '__main__':
    main()