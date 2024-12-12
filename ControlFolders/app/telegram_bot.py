from telegram import Update
from telegram.ext import Application, CommandHandler
import os
import asyncio
from dotenv import load_dotenv

# Класс для работы с Telegram-ботом
class TelegramBot:
    def __init__(self, config):
        self.chat_id = config['CHAT_ID']
        self.history = []  # История сообщений за день
        self.application = Application.builder().token(config['TELEGRAM_TOKEN']).build()

    async def send_telegram_message(self, message):
        """Отправить сообщение в Telegram"""
        self.history.append(message)
        await self.application.bot.send_message(chat_id=self.chat_id, text=message)

    async def history_command(self, update: Update, context):
        """Команда для получения истории сообщений"""
        today_history = '\n'.join(self.history)
        await update.message.reply_text(f"История за сегодня:\n{today_history}")

    async def run(self):
        """Запуск бота с обработкой команд"""
        self.application.add_handler(CommandHandler("history", self.history_command))
        await self.application.run_polling()
