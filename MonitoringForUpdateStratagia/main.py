import asyncio

from app import handlers
from app.monitoring import Monitor, periodic_update_check
from config import settings
from config.logging_config import configure_logging, logger
from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes


async def on_startup(application: Application) -> None:
    application.bot_data["monitor"] = Monitor()


class MonitoringApplication(Application):
    async def start(self) -> None:
        # post_init precedes polling bootstrap. Do not modify files or send commands
        # until both polling bootstrap and Application.start have succeeded.
        await super().start()
        self.bot_data["monitor_task"] = asyncio.create_task(
            periodic_update_check(self.bot_data["monitor"])
        )


async def on_shutdown(application: Application) -> None:
    task = application.bot_data.pop("monitor_task", None)
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


async def on_error(update: Update | None, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.warning("Telegram handler failed")


def build_application() -> MonitoringApplication:
    settings.validate_settings()
    configure_logging()
    application = (
        Application.builder().application_class(MonitoringApplication).token(settings.TELEGRAM_TOKEN)
        .post_init(on_startup).post_stop(on_shutdown).post_shutdown(on_shutdown).build()
    )
    application.add_handler(CommandHandler("start", handlers.start))
    for callback in (handlers.check_version, handlers.download_file, handlers.check_commits, handlers.reload_freqtrade):
        application.add_handler(CallbackQueryHandler(callback, pattern=rf"\A{callback.__name__}\Z"))
    application.add_error_handler(on_error)
    return application


def main() -> None:
    try:
        build_application().run_polling(bootstrap_retries=0)
    except Exception:
        # Even startup/network errors can carry a bot token. Fail with a safe status.
        logger.error("Monitoring stopped; check configuration and connectivity")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
