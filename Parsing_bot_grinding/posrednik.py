import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, CallbackContext

# Настройки
TOKEN = '8156069823:AAEuh8Y_1kHHHKWi06QVoG2RosNJDDaMmAU'
CHANNEL_ID = -1002307617437  # ID канала с префиксом -100

# Включаем логирование
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

async def forward_to_channel(update: Update, context: CallbackContext) -> None:
    # Пересылаем текст сообщения в канал
    if update.message:
        await context.bot.send_message(chat_id=CHANNEL_ID, text=update.message.text)

def main():
    application = ApplicationBuilder().token(TOKEN).build()

    # Обработчик текстовых сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, forward_to_channel))

    # Запуск бота
    application.run_polling()

if __name__ == '__main__':
    main()
