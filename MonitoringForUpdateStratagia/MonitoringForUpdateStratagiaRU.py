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

# Настроим логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Загружаем переменные окружения из .env
load_dotenv()

# Конфигурация из файла .env
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")  # Токен Telegram-бота
CHAT_ID = os.getenv("CHAT_ID")  # ID чата для отправки сообщений
FREQTRADE_BOT_TOKEN = os.getenv("FREQTRADE_BOT_TOKEN")  # Токен бота Freqtrade
FREQTRADE_CHAT_ID = os.getenv("CHAT_ID")  # ID чата для Freqtrade
FILE_URL = os.getenv("FILE_URL")  # URL для скачивания файла
LOCAL_FILE_PATH = os.getenv("LOCAL_FILE_PATH")  # Локальный путь файла
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL"))  # Интервал проверки обновлений
LINE_NUMBER = int(os.getenv("LINE_NUMBER"))  # Номер строки для извлечения версии
RETRY_LIMIT = int(os.getenv("RETRY_LIMIT"))  # Лимит попыток при скачивании
RETRY_DELAY = int(os.getenv("RETRY_DELAY"))  # Задержка между попытками
REPO_URL = os.getenv("REPO_URL")  # URL репозитория GitHub
REMOTE_FILE_PATH = os.getenv("REMOTE_FILE_PATH")  # Путь к файлу в репозитории
TIMEZONE = os.getenv("TIMEZONE")  # Часовой пояс

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

# Функция для перезапуска Freqtrade
async def reload_freqtrade(update: Update, context: CallbackContext):
    """Отправка команды на перезапуск Freqtrade в другой бот."""
    logger.info("Обработка кнопки 'Перезапустить Freqtrade'.")
    try:
        # Отправка команды на перезапуск
        send_telegram_message(FREQTRADE_BOT_TOKEN, FREQTRADE_CHAT_ID, "/reload_config")
        message = "Команда перезапуска Freqtrade отправлена"

        # Проверяем, существует ли callback_query, и отправляем ответ
        if update and update.callback_query:
            await update.callback_query.message.reply_text(message)
        else:
            logger.warning("Перезапуск инициирован без взаимодействия с Telegram.")

        logger.info("Команда на перезапуск Freqtrade успешно отправлена.")
    except Exception as e:
        logger.error(f"Ошибка при отправке команды перезапуска: {e}")

        # Отправляем сообщение об ошибке, если callback_query существует
        if update and update.callback_query:
            await update.callback_query.message.reply_text(f"❌ Не удалось отправить команду: {e}")


# Асинхронная версия загрузки файла с повторными попытками
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

# Получаем содержимое удалённого файла с GitHub
async def fetch_file_content(repo_url, file_path):
    """Получает содержимое файла из GitHub."""
    api_url = f"https://raw.githubusercontent.com/{repo_url}/main/{file_path}"
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(api_url) as response:
                response.raise_for_status()
                return await response.text()
        except Exception as e:
            logger.error(f"Ошибка при получении файла: {e}")
            return None

# Извлекаем версию из содержимого файла
def extract_version_from_content(content):
    """Извлекает версию из содержимого файла."""
    try:
        match = re.search(r'return\s+[\'\"](v[\d.]+)[\'\"]', content)
        return match.group(1) if match else "Неизвестная версия"
    except Exception as e:
        logger.error(f"Ошибка при извлечении версии: {e}")
        return "Ошибка извлечения"

# Извлекаем версию локального файла
def extract_version_from_line(file_path, line_number=LINE_NUMBER):
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

# Получаем версию удалённого файла
async def check_remote_version():
    """Проверяет версию файла на GitHub."""
    content = await fetch_file_content(REPO_URL, REMOTE_FILE_PATH)
    if content:
        version = extract_version_from_content(content)
        logger.info(f"Версия удалённого файла: {version}")
        return version
    else:
        logger.error("Не удалось получить содержимое файла.")
        return "Ошибка загрузки"

# Функция для скачивания файла и уведомления с перезапуском
async def check_for_updates():
    """Проверяет наличие обновлений на удаленном сервере и скачивает файл, если обнаружено обновление."""
    local_version = extract_version_from_line(LOCAL_FILE_PATH)
    remote_version = await check_remote_version()

    if local_version != remote_version:
        # Если версии не совпадают, загружаем новый файл
        await download_file_with_retries(FILE_URL, LOCAL_FILE_PATH)
        message = f"✅ Обновление обнаружено! Новая версия: {remote_version} успешно загружена.\n\n Перезапускаем Freqtrade..."
        send_telegram_message(TELEGRAM_TOKEN, CHAT_ID, message)
        logger.info(f"Обновление загружено. Локальная версия теперь: {remote_version}")

        # После загрузки файла, перезапускаем Freqtrade
        await reload_freqtrade(None, None)  # Здесь передаются пустые значения, если не требуется конкретное обновление через Telegram
    else:
        logger.info(f"Обновлений не обнаружено. Локальная версия: {local_version}")

# Асинхронная задача для периодической проверки
async def periodic_update_check():
    """Периодически проверяет наличие обновлений."""
    timezone = pytz.timezone(TIMEZONE)  # Используем часовой пояс из .env
    while True:
        await check_for_updates()  # Проверяем обновления
        # Обновляем время следующей проверки с учетом часового пояса
        next_check_time = datetime.now(timezone) + timedelta(seconds=CHECK_INTERVAL)
        next_check_time_str = next_check_time.strftime('%d-%m-%Y %H:%M:%S')
        
        # Выводим время следующей проверки в терминал (Docker)
        logger.info(f"Следующая проверка обновлений в: {next_check_time_str}")
        
        await asyncio.sleep(CHECK_INTERVAL)  # Ждем заданный интервал времени

# Функция обработчика проверки версии
async def check_version(update: Update, context: CallbackContext):
    """Проверяет текущую версию локального файла и версию на сервере (GitHub)."""
    logger.info("Обработка кнопки 'Проверить версию'.")

    # Получаем версию локального файла
    local_version = extract_version_from_line(LOCAL_FILE_PATH)
    logger.info(f"Локальная версия: {local_version}")

    # Получаем версию удалённого файла
    remote_version = await check_remote_version()

    # Сравниваем версии
    if local_version == remote_version:
        version_status = "✅  Обновлений не обнаружено"
    else:
        version_status = f"📥  Обнаружена новая версия на GitHub: {remote_version}"

    # Формируем сообщение
    message = f"Версия локального файла: {local_version}\n" \
              f"Версия на сервере (GitHub): {remote_version}\n" \
              f"{version_status}"

    if update.callback_query:
        await update.callback_query.message.reply_text(message)

# Обработчик кнопки "📜 Последние коммиты"
async def check_commits(update: Update, context: CallbackContext):
    """Проверка коммитов в репозитории GitHub."""
    logger.info("Обработка кнопки 'Проверить последние коммиты'.")
    commits = await get_commits_from_github(REPO_URL)
    
    # Если коммиты были получены
    if commits:
        # Извлекаем заголовок с датой и коммиты
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
                
                # Формируем список коммитов с нужной информацией, но только время
                tz = pytz.timezone(TIMEZONE)
                commit_list = [
                    f"{commit['sha'][:7]} {commit['commit']['message']} at {datetime.fromisoformat(commit['commit']['author']['date'].replace('Z', '+00:00')).astimezone(tz).strftime('%H:%M:%S')}" 
                    for commit in filtered_commits
                ]
                
                if not commit_list:
                    return [f"Нет коммитов на {last_commit_date}."]

                # Заголовок с эмодзи и датой
                header = f"📜 Последние коммиты от {last_commit_date}"
                
                # Возвращаем заголовок и список коммитов
                return [header] + commit_list
        
        except aiohttp.ClientError as e:
            logger.error(f"Ошибка при запросе к GitHub API: {e}")
            return ["Ошибка при получении коммитов."]
        except Exception as e:
            logger.error(f"Неизвестная ошибка: {e}")
            return ["Не удалось получить данные о коммитах."]

# Асинхронная загрузка файла с сервера
async def download_file(update: Update, context: CallbackContext):
    """Принудительно загружает файл с сервера, если версия устарела."""
    logger.info("Обработка кнопки 'Скачать обновление'.")
    try:
        # Получаем версию локального файла
        local_version = extract_version_from_line(LOCAL_FILE_PATH)
        
        # Получаем версию файла с сервера
        await download_file_with_retries(FILE_URL, LOCAL_FILE_PATH, retries=1, delay=0) 
        server_version = extract_version_from_line(LOCAL_FILE_PATH)
        
        if local_version == server_version:
            # Если версии совпадают, уведомляем, что обновление не требуется
            message = f"Версия локального файла ({local_version}) актуальна. Обновление не требуется."
            if update.callback_query:  # Проверяем, существует ли callback_query
                await update.callback_query.message.reply_text(message)
            logger.info("Обновление не требуется. Версия актуальна.")
        else:
            # Если версии разные, загружаем новую версию
            await download_file_with_retries(FILE_URL, LOCAL_FILE_PATH)
            message = f"✅  Новая версия ({server_version}) успешно загружена!"
            if update.callback_query:  # Проверяем, существует ли callback_query
                await update.callback_query.message.reply_text(message)
            logger.info("Новая версия успешно загружена.")
    
    except Exception as e:
        logger.error(f"Ошибка при скачивании файла: {e}")
        if update.callback_query:  # Проверяем, существует ли callback_query
            await update.callback_query.message.reply_text(f"❌  Не удалось загрузить файл: {e}")

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
    local_version = extract_version_from_line(LOCAL_FILE_PATH)
    
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
