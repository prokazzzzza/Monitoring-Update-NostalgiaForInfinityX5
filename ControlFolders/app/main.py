import logging
import os
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, CallbackContext
from dotenv import load_dotenv

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

# Класс для работы с Telegram-ботом
class TelegramBot:
    def __init__(self, config):
        self.chat_id = config['CHAT_ID']
        self.application = Application.builder().token(config['TELEGRAM_TOKEN']).build()

    async def send_telegram_message(self, message):
        """Отправить сообщение в Telegram"""
        await self.application.bot.send_message(chat_id=self.chat_id, text=message)

    async def history_command(self, update: Update, context: CallbackContext):
        """Команда для получения истории сообщений"""
        today_history = ' '.join(context.args)
        await update.message.reply_text(f"История за сегодня:\n{today_history}")

    async def start_command(self, update: Update, context: CallbackContext):
        """Команда для начала работы с ботом"""
        keyboard = [
            [InlineKeyboardButton("Получить историю", callback_data="history")],
            [InlineKeyboardButton("Привет", callback_data="hello")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Привет! Я ваш бот. Выберите опцию.", reply_markup=reply_markup)

    async def callback_query_handler(self, update: Update, context: CallbackContext):
        """Обработка нажатий кнопок"""
        query = update.callback_query
        data = query.data
        if data == "history":
            await query.answer("История загружена")
            await query.edit_message_text("Здесь будет ваша история.")
        elif data == "hello":
            await query.answer("Привет!")
            await query.edit_message_text("Привет! Чем могу помочь?")

    def run(self):
        """Запуск бота с обработкой команд"""
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("history", self.history_command))
        self.application.add_handler(CallbackQueryHandler(self.callback_query_handler))

        # Логируем входящие сообщения
        self.application.add_handler(MessageHandler(filters.TEXT, log_telegram_message))

        # Запуск бота с обработкой событий без необходимости закрывать цикл
        self.application.run_polling()

# Основная функция
def main():
    # Загружаем переменные окружения
    load_dotenv()

    # Конфигурация Telegram-бота
    config = {
        'TELEGRAM_TOKEN': os.getenv('TELEGRAM_TOKEN'),
        'CHAT_ID': os.getenv('CHAT_ID'),
    }

    # Инициализация бота
    bot = TelegramBot(config)

    # Сообщение при запуске
    startup_message = "Приложение запущено успешно!"
    bot.send_telegram_message(startup_message)  # Отправляем сообщение в Telegram

    # Запускаем бота
    bot.run()

if __name__ == "__main__":
    main()
