import asyncio
from dataclasses import dataclass
from pathlib import Path

import httpx
from config import settings
from config.logging_config import logger

from app import strategy
from app.utils import extract_version_from_file, text


async def send_telegram_message(token: str, chat_id: str | int, message: str) -> bool:
    """Confirm API delivery only, never infer that Freqtrade applied a command."""
    try:
        async with httpx.AsyncClient(trust_env=False, follow_redirects=False) as client:
            response = await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": message}, timeout=15,
            )
            if response.status_code == 200 and response.json().get("ok") is True:
                return True
    except Exception:
        # Transport exceptions may contain the token-bearing request URL.
        logger.warning("Telegram delivery failed")
    return False


@dataclass(frozen=True)
class UpdateResult:
    status: str
    changed: tuple[str, ...] = ()


class Monitor:
    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.marker_path = Path(settings.LOCAL_FILE_PATH).parent / ".monitoring-reload-pending.json"

    def mark_pending(self) -> None:
        # Existence alone is fail-closed, including an unreadable/corrupt marker.
        strategy.atomic_write(self.marker_path, b'{"version":1,"reload":"pending"}\n')

    def has_pending_reload(self) -> bool:
        try:
            self.marker_path.lstat()
        except FileNotFoundError:
            return False
        except OSError:
            # Permission errors must not look like a missing pending marker.
            return True
        return True

    async def _deliver_reload(self) -> bool:
        self.mark_pending()
        delivered = await send_telegram_message(
            settings.FREQTRADE_BOT_TOKEN, settings.FREQTRADE_CHAT_ID, "/reload_config",
        )
        if delivered:
            self.marker_path.unlink()
        return delivered

    async def reload(self) -> bool:
        async with self.lock:
            try:
                return await self._deliver_reload()
            except Exception:
                logger.warning("Reload delivery remains unconfirmed")
                return False

    async def force_download(self) -> UpdateResult:
        async with self.lock:
            return await self._update(force=True)

    async def check_for_updates(self) -> UpdateResult:
        async with self.lock:
            if self.has_pending_reload():
                return UpdateResult("reload_pending")
            return await self._update(force=False)

    async def _update(self, *, force: bool) -> UpdateResult:
        changed = []
        try:
            remote_version = None
            if not force:
                local_version = extract_version_from_file(settings.LOCAL_FILE_PATH)
                if local_version is None:
                    return UpdateResult("failed")
                remote_version = await strategy.check_remote_version()
                if remote_version is None:
                    return UpdateResult("failed")
            if force or local_version != remote_version:
                if await strategy.download_file_with_retries(
                    settings.FILE_URL, settings.LOCAL_FILE_PATH,
                    expected_version=remote_version, before_replace=self.mark_pending,
                ):
                    changed.append("strategy")
            if await strategy.update_blacklist_if_needed(force=force, before_replace=self.mark_pending):
                changed.append("blacklist")
            if force:
                return UpdateResult("downloaded", tuple(changed))
            if changed:
                try:
                    delivered = await self._deliver_reload()
                except Exception:
                    logger.warning("Reload delivery state requires manual review")
                    delivered = False
                return UpdateResult("command_delivered" if delivered else "reload_pending", tuple(changed))
            return UpdateResult("unchanged")
        except Exception:
            logger.warning("Update operation failed")
            return UpdateResult("partial" if changed else "failed", tuple(changed))


async def periodic_update_check(monitor: Monitor) -> None:
    while True:
        try:
            result = await monitor.check_for_updates()
            logger.info("Scheduled check: %s", result.status)
            if result.changed:
                outcomes = {
                    "command_delivered": (
                        "Файлы обновлены; команда доставлена в Telegram. Применение в Freqtrade не подтверждено.",
                        "Files updated; command delivered to Telegram. Freqtrade application is unconfirmed.",
                    ),
                    "reload_pending": (
                        "Файлы обновлены; доставка команды не подтверждена. Нужна ручная проверка.",
                        "Files updated; command delivery unconfirmed. Manual review required.",
                    ),
                    "partial": (
                        "Обновлена только часть файлов. Автоматическая перезагрузка остановлена.",
                        "Only some files updated. Automatic reload is stopped.",
                    ),
                }
                await send_telegram_message(settings.TELEGRAM_TOKEN, settings.CHAT_ID, text(*outcomes[result.status]))
        except Exception:
            logger.warning("Scheduled check failed")
        await asyncio.sleep(int(settings.CHECK_INTERVAL))
