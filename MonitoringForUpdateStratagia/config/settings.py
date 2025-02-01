import os
from dotenv import load_dotenv

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
RETRY_LIMIT = int(os.getenv("RETRY_LIMIT"))  # Лимит попыток при скачивании
RETRY_DELAY = int(os.getenv("RETRY_DELAY"))  # Задержка между попытками
REPO_URL = os.getenv("REPO_URL")  # URL репозитория GitHub
REMOTE_FILE_PATH = os.getenv("REMOTE_FILE_PATH")  # Путь к файлу в репозитории
TIMEZONE = os.getenv("TIMEZONE")  # Часовой пояс
LANGUAGE = os.getenv("LANGUAGE")  # Язык
LOCAL_VOLUME_PATH = os.getenv("LOCAL_VOLUME_PATH")  # Локальная папка в Windows
BOT_VERSION = "v1.15"