import logging
import re
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, CallbackContext

# Включаем логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# Токен вашего бота
TOKEN = '8156069823:AAEuh8Y_1kHHHKWi06QVoG2RosNJDDaMmAU'

# ID канала с префиксом -100
CHANNEL_ID = -1002307617437

async def start(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text('Привет! Я бот, который будет парсить сообщения о гриндинге.')

def parse_message(message: str) -> dict:
    pattern = (
        r'Grinding exit \(gd1\) '
        r'(?P<symbol>[A-Z]+\/[A-Z]+:[A-Z]+) \| '
        r'Rate: (?P<rate>\d+\.\d+) \| '
        r'Stake amount: (?P<stake_amount>\d+\.\d+) \| '
        r'Coin amount: (?P<coin_amount>\d+\.\d+) \| '
        r'Profit \(stake\): (?P<profit_stake>\d+\.\d+) \| '
        r'Profit: (?P<profit>\d+\.\d+)% \| '
        r'Grind profit: (?P<grind_profit>\d+\.\d+)% \((?P<grind_profit_amount>\d+\.\d+)\ [A-Z]+\)'
    )

    match = re.match(pattern, message)
    if not match:
        return {}

    data = match.groupdict()

    try:
        data['stake_amount'] = round(float(data['stake_amount']), 2)
        data['profit'] = round(float(data['profit']), 2)
        data['grind_profit'] = round(float(data['grind_profit']), 2)
    except ValueError as e:
        logger.error(f"Ошибка округления: {e}")
        return {}

    return data

async def handle_message(update: Update, context: CallbackContext) -> None:
    # Проверяем, что сообщение пришло из нужного канала
    if update.message and update.message.chat.id == CHANNEL_ID:
        message_text = update.message.text
        data = parse_message(message_text)
        if data:
            response = (
                f'Получено валидное сообщение:\n'
                f'Символ: {data["symbol"]}\n'
                f'Коэффициент: {data["rate"]}\n'
                f'Сумма стейка: {data["stake_amount"]}\n'
                f'Сумма монет: {data["coin_amount"]}\n'
                f'Прибыль (стейк): {data["profit_stake"]}\n'
                f'Прибыль: {data["profit"]}%\n'
                f'Прибыль от гриндинга: {data["grind_profit"]}% '
                f'({data["grind_profit_amount"]} {data["symbol"].split(":")[-1]})'
            )
        else:
            response = 'Сообщение не соответствует шаблону.'

        await update.message.reply_text(response)

def main() -> None:
    # Создаем Application и передаем ему токен вашего бота
    application = ApplicationBuilder().token(TOKEN).build()

    # Регистрируем команду /start
    application.add_handler(CommandHandler("start", start))

    # Регистрируем обработчик сообщений из канала
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Запускаем бота и циклически обрабатываем события
    application.run_polling()

if __name__ == '__main__':
    main()
