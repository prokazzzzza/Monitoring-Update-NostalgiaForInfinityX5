import json
from datetime import datetime

import pytz
from config import settings
from config.logging_config import logger
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app import strategy
from app.monitoring import Monitor, UpdateResult
from app.utils import extract_version_from_file, format_time_interval, text


def authorized(update: Update | None) -> bool:
    chat = update.effective_chat if update else None
    return bool(chat and settings.CHAT_ID and str(chat.id) == str(settings.CHAT_ID))


async def acknowledge(update: Update) -> None:
    if update.callback_query:
        await update.callback_query.answer()


def monitor_for(context: ContextTypes.DEFAULT_TYPE) -> Monitor:
    if "monitor" not in context.bot_data:
        context.bot_data["monitor"] = Monitor()
    return context.bot_data["monitor"]


async def version_message(monitor: Monitor) -> str:
    local = extract_version_from_file(settings.LOCAL_FILE_PATH)
    remote = await strategy.check_remote_version()
    unavailable = text("не определена", "unavailable")
    message = text(
        f"Версия локального файла: {local or unavailable}\nВерсия на GitHub: {remote or unavailable}",
        f"Version of local file: {local or unavailable}\nVersion on GitHub: {remote or unavailable}",
    )
    if monitor.has_pending_reload():
        message += "\n" + text(
            "Перезагрузка ожидает ручной проверки; версии файлов не подтверждают применение в Freqtrade.",
            "Reload awaits manual review; file versions do not confirm application in Freqtrade.",
        )
    return message


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    buttons = [
        (text("Проверить версию", "Check version"), "check_version"),
        (text("Скачать обновление", "Download update"), "download_file"),
        (text("Последние коммиты", "Latest commits"), "check_commits"),
        (text("Перезапустить Freqtrade", "Reload Freqtrade"), "reload_freqtrade"),
    ]
    message = text("Мониторинг стратегии", "Strategy monitoring") + f" {settings.BOT_VERSION}\n"
    message += await version_message(monitor_for(context))
    message += "\n" + text("Интервал: ", "Interval: ") + format_time_interval(settings.CHECK_INTERVAL)
    await update.effective_message.reply_text(
        message, reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(label, callback_data=action)] for label, action in buttons
        ]),
    )


async def check_version(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    await acknowledge(update)
    await update.effective_message.reply_text(await version_message(monitor_for(context)))


def result_message(result: UpdateResult) -> str:
    messages = {
        "downloaded": ("Файлы проверены и загружены. Перезагрузка выполняется отдельной кнопкой.", "Files checked and downloaded. Use the separate reload button."),
        "partial": ("Обновлена только часть файлов. Перезагрузка не отправлена; требуется проверка.", "Only some files were updated. No reload sent; review is required."),
        "failed": ("Обновление не завершено. Проверьте настройки и доступность источника.", "Update incomplete. Check configuration and source availability."),
    }
    return text(*messages.get(result.status, messages["failed"]))


async def download_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    await acknowledge(update)
    result = await monitor_for(context).force_download()
    await update.effective_message.reply_text(result_message(result))


async def reload_freqtrade(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    await acknowledge(update)
    delivered = await monitor_for(context).reload()
    message = text(
        "Команда доставлена в Telegram; применение в Freqtrade не подтверждено.",
        "Command delivered to Telegram; application by Freqtrade is unconfirmed.",
    ) if delivered else text(
        "Доставка команды не подтверждена. Проверьте Freqtrade перед повторной ручной попыткой.",
        "Command delivery unconfirmed. Check Freqtrade before retrying manually.",
    )
    await update.effective_message.reply_text(message)


async def get_commits_from_github(repo_url: str) -> list[str]:
    try:
        if repo_url != settings.REPO_URL:
            raise ValueError
        content = await strategy.fetch_bytes(f"https://api.github.com/repos/{repo_url}/commits?per_page=100", api=True)
        commits = json.loads(content)
        if not isinstance(commits, list) or not commits:
            return []
        commits.sort(key=lambda item: item["commit"]["author"]["date"], reverse=True)
        latest = commits[0]["commit"]["author"]["date"][:10]
        zone = pytz.timezone(settings.TIMEZONE)
        lines = []
        for item in commits:
            date = item["commit"]["author"]["date"]
            if date[:10] == latest:
                timestamp = datetime.fromisoformat(date.replace("Z", "+00:00")).astimezone(zone)
                lines.append(f"{item['sha'][:7]} {item['commit']['message']} — {timestamp:%H:%M:%S}")
        return [text(f"Последние коммиты: {latest} ({len(lines)})", f"Latest commits: {latest} ({len(lines)})"), *lines]
    except Exception:
        logger.warning("Commit list unavailable")
        return [text("Не удалось получить коммиты.", "Could not retrieve commits.")]


async def check_commits(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not authorized(update):
        return
    await acknowledge(update)
    commits = await get_commits_from_github(settings.REPO_URL)
    message = "\n".join(commits) or text("Нет коммитов.", "No commits.")
    # Telegram limits message length; do not log external commit messages.
    for offset in range(0, len(message), 3500):
        await update.effective_message.reply_text(message[offset:offset + 3500])
