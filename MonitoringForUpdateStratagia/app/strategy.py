from .monitoring import TELEGRAM_TOKEN, CHAT_ID, FREQTRADE_BOT_TOKEN, FREQTRADE_CHAT_ID, FILE_URL, LOCAL_FILE_PATH, CHECK_INTERVAL, RETRY_LIMIT, RETRY_DELAY, REPO_URL, REMOTE_FILE_PATH, TIMEZONE, BOT_VERSION, logger, send_telegram_message, log_telegram_message
import aiohttp
import asyncio
import re

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