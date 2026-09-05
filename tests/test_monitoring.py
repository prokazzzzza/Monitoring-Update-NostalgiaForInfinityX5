import asyncio
import hashlib
import importlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from conftest import APP

STRATEGY = b"class Strategy:\n    def version(self):\n        return 'v1.2.3'\n"


def update(chat_id=123, callback=True):
    message = SimpleNamespace(reply_text=AsyncMock())
    return SimpleNamespace(
        effective_chat=None if chat_id is None else SimpleNamespace(id=chat_id),
        effective_message=message,
        message=message if not callback else None,
        callback_query=SimpleNamespace(answer=AsyncMock(), message=message) if callback else None,
    )


class Response:
    def __init__(self, data=STRATEGY, status=200, error=None):
        self.data, self.status, self.error = data, status, error
        self.content = self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def iter_chunked(self, size):
        yield self.data[:5]
        if self.error:
            raise self.error
        yield self.data[5:]


def fake_http(monkeypatch, module, responses):
    session = Mock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.get.side_effect = responses
    factory = Mock(return_value=session)
    monkeypatch.setattr(module.aiohttp, "ClientSession", factory)
    return session, factory


def test_actual_modules_import_and_build_offline(modules):
    app = modules["main"].build_application()
    callbacks = [h for group in app.handlers.values() for h in group if hasattr(h, "pattern")]
    assert len(callbacks) == 4
    for handler in callbacks:
        assert handler.pattern.fullmatch(handler.callback.__name__)
        assert not handler.pattern.search("prefix_" + handler.callback.__name__)
        assert not handler.pattern.search(handler.callback.__name__ + "_suffix")
        assert not handler.pattern.search(handler.callback.__name__ + "\n")
    assert app.post_init and app.post_stop and app.post_shutdown
    assert app.error_handlers


@pytest.mark.parametrize("key,value", [
    ("CHAT_ID", "bad-sensitive-value"), ("TELEGRAM_TOKEN", ""),
    ("CHECK_INTERVAL", "0"), ("RETRY_LIMIT", "invalid"), ("RETRY_DELAY", "-1"),
    ("TIMEZONE", "Invalid/Zone"), ("LANGUAGE", "FR"), ("LOCAL_FILE_PATH", ""),
    ("FILE_URL", "https://raw.githubusercontent.com.evil.invalid/payload"),
    ("REPO_URL", "../private"), ("REMOTE_FILE_PATH", "../escape.py"),
    ("BLACKLIST_FILE_URL", "https://raw.githubusercontent.com/example/r/main/blacklist.json"),
])
def test_invalid_settings_fail_before_application(monkeypatch, key, value):
    monkeypatch.setenv(key, value)
    main = importlib.import_module("main")
    builder = Mock(side_effect=AssertionError("Application must not be constructed"))
    monkeypatch.setattr(main.Application, "builder", builder)
    with pytest.raises(ValueError) as error:
        main.build_application()
    assert key in str(error.value)
    assert "bad-sensitive-value" not in str(error.value)
    builder.assert_not_called()


def test_freqtrade_chat_setting_and_legacy_fallback(monkeypatch):
    settings = importlib.import_module("config.settings")
    settings.validate_settings()
    assert str(settings.FREQTRADE_CHAT_ID) == "123"
    monkeypatch.setenv("FREQTRADE_CHAT_ID", "456")
    importlib.reload(settings)
    settings.validate_settings()
    assert str(settings.FREQTRADE_CHAT_ID) == "456"


@pytest.mark.parametrize("name", ["start", "check_version", "download_file", "check_commits", "reload_freqtrade"])
@pytest.mark.parametrize("chat_id", [999, None])
def test_unauthorized_handlers_have_zero_side_effects(modules, monkeypatch, offline, name, chat_id):
    spies = []
    for module_name, function in [
        ("app.handlers", "extract_version_from_file"), ("app.handlers", "monitor_for"),
        ("app.handlers", "get_commits_from_github"), ("app.strategy", "check_remote_version"),
        ("app.strategy", "download_file_with_retries"), ("app.monitoring", "send_telegram_message"),
    ]:
        spy = Mock(side_effect=AssertionError("Unauthorized side effect"))
        monkeypatch.setattr(modules[module_name], function, spy)
        spies.append(spy)
    event = update(chat_id, callback=name != "start")
    context = SimpleNamespace(bot_data={})
    offline.run_until_complete(getattr(modules["app.handlers"], name)(event, context))
    event.effective_message.reply_text.assert_not_awaited()
    if event.callback_query:
        event.callback_query.answer.assert_not_awaited()
    assert context.bot_data == {}
    for spy in spies:
        spy.assert_not_called()


@pytest.mark.parametrize("language,word", [("RU", "Версия"), ("ENG", "Version")])
def test_authorized_start_language_and_buttons(modules, monkeypatch, offline, language, word):
    settings = modules["config.settings"]
    monkeypatch.setattr(settings, "LANGUAGE", language)
    handlers = modules["app.handlers"]
    monkeypatch.setattr(handlers.strategy, "check_remote_version", AsyncMock(return_value="v1.2.3"))
    event = update(callback=False)
    offline.run_until_complete(handlers.start(event, SimpleNamespace(bot_data={})))
    args, kwargs = event.message.reply_text.call_args
    assert word in args[0]
    assert len(kwargs["reply_markup"].inline_keyboard) == 4


@pytest.mark.parametrize("status,body,expected", [(200, {"ok": True}, True), (200, {"ok": False}, False), (500, {"ok": True}, False)])
def test_telegram_delivery_requires_http_and_json_ok(modules, monkeypatch, offline, caplog, status, body, expected):
    monitoring = modules["app.monitoring"]
    response = SimpleNamespace(status_code=status, json=Mock(return_value=body))
    post = AsyncMock(return_value=response)
    client = Mock()
    client.post = post
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(monitoring.httpx, "AsyncClient", Mock(return_value=client))
    assert offline.run_until_complete(monitoring.send_telegram_message("synthetic-secret", "123", "private-text")) is expected
    assert post.call_args.kwargs["timeout"] == 15
    assert "synthetic-secret" not in caplog.text and "private-text" not in caplog.text


def test_raw_transport_and_handler_errors_never_logged(modules, monkeypatch, offline, caplog):
    monitoring = modules["app.monitoring"]
    secret = "synthetic-secret-with-personal-content"
    monkeypatch.setattr(monitoring.httpx, "AsyncClient", Mock(side_effect=RuntimeError(secret)))
    assert offline.run_until_complete(monitoring.send_telegram_message(secret, "123", secret)) is False
    offline.run_until_complete(modules["main"].on_error(update(), SimpleNamespace(error=RuntimeError(secret))))
    assert secret not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)


@pytest.mark.parametrize("data,status", [(b"<html>error</html>", 200), (b"return (", 200), (STRATEGY, 302)])
def test_failed_download_preserves_destination(modules, monkeypatch, offline, tmp_path, data, status):
    strategy = modules["app.strategy"]
    target = tmp_path / "target.py"
    target.write_bytes(b"original")
    session, factory = fake_http(monkeypatch, strategy, [Response(data, status)])
    with pytest.raises(strategy.DownloadError):
        offline.run_until_complete(strategy.download_file_with_retries(
            modules["config.settings"].FILE_URL, target, retries=1, delay=0))
    assert target.read_bytes() == b"original"
    assert list(tmp_path.glob("*.tmp")) == []
    assert session.get.call_args.kwargs["allow_redirects"] is False
    assert factory.call_args.kwargs["timeout"].total == 30


def test_download_retry_is_atomic_and_bounded(modules, monkeypatch, offline, tmp_path):
    strategy = modules["app.strategy"]
    target = tmp_path / "target.py"
    target.write_bytes(b"original")
    session, _ = fake_http(monkeypatch, strategy, [Response(error=OSError("synthetic-secret")), Response()])
    offline.run_until_complete(strategy.download_file_with_retries(
        modules["config.settings"].FILE_URL, target, retries=2, delay=0))
    assert target.read_bytes() == STRATEGY
    assert session.get.call_count == 2
    assert list(tmp_path.glob("*.tmp")) == []


def test_download_cancellation_keeps_file_and_no_retry(modules, monkeypatch, offline, tmp_path):
    strategy = modules["app.strategy"]
    target = tmp_path / "target.py"
    target.write_bytes(b"original")
    session, _ = fake_http(monkeypatch, strategy, [Response(error=asyncio.CancelledError())])
    with pytest.raises(asyncio.CancelledError):
        offline.run_until_complete(strategy.download_file_with_retries(modules["config.settings"].FILE_URL, target))
    assert target.read_bytes() == b"original"
    assert session.get.call_count == 1
    assert list(tmp_path.glob("*.tmp")) == []


@pytest.mark.parametrize("url", ["http://raw.githubusercontent.com/x", "https://evil.invalid/x", "https://user:password@raw.githubusercontent.com/x", "https://raw.githubusercontent.com:444/x"])
def test_untrusted_download_rejected_before_request(modules, monkeypatch, offline, tmp_path, url):
    strategy = modules["app.strategy"]
    factory = Mock(side_effect=AssertionError("HTTP must not start"))
    monkeypatch.setattr(strategy.aiohttp, "ClientSession", factory)
    with pytest.raises(strategy.DownloadError):
        offline.run_until_complete(strategy.download_file_with_retries(url, tmp_path / "target.py"))
    factory.assert_not_called()


def test_scheduled_single_reload_and_persistent_failed_delivery(modules, monkeypatch, offline):
    strategy, monitoring = modules["app.strategy"], modules["app.monitoring"]
    monkeypatch.setattr(strategy, "check_remote_version", AsyncMock(return_value="v1.2.3"))
    async def downloaded(url, path, **kwargs):
        kwargs["before_replace"]()
        Path(path).write_bytes(STRATEGY)
        return True
    download = AsyncMock(side_effect=downloaded)
    monkeypatch.setattr(strategy, "download_file_with_retries", download)
    monkeypatch.setattr(strategy, "update_blacklist_if_needed", AsyncMock(return_value=True))
    send = AsyncMock(return_value=False)
    monkeypatch.setattr(monitoring, "send_telegram_message", send)
    monitor = monitoring.Monitor()
    result = offline.run_until_complete(monitor.check_for_updates())
    assert result.status == "reload_pending"
    assert monitor.marker_path.is_file()
    restored = monitoring.Monitor()
    again = offline.run_until_complete(restored.check_for_updates())
    assert again.status == "reload_pending"
    assert download.await_count == 1
    assert send.await_count == 1
    send.return_value = True
    assert offline.run_until_complete(restored.reload()) is True
    assert not restored.marker_path.exists()


def test_partial_failure_no_reload_or_false_success(modules, monkeypatch, offline):
    strategy, monitoring = modules["app.strategy"], modules["app.monitoring"]
    monkeypatch.setattr(strategy, "check_remote_version", AsyncMock(return_value="v1.2.3"))
    async def downloaded(url, path, **kwargs):
        kwargs["before_replace"]()
        Path(path).write_bytes(STRATEGY)
        return True
    monkeypatch.setattr(strategy, "download_file_with_retries", AsyncMock(side_effect=downloaded))
    monkeypatch.setattr(strategy, "update_blacklist_if_needed", AsyncMock(side_effect=OSError("synthetic-secret")))
    send = AsyncMock()
    monkeypatch.setattr(monitoring, "send_telegram_message", send)
    monitor = monitoring.Monitor()
    result = offline.run_until_complete(monitor.check_for_updates())
    assert result.status == "partial"
    assert result.changed == ("strategy",)
    assert monitor.marker_path.exists()
    send.assert_not_awaited()


def test_manual_download_once_without_reload(modules, monkeypatch, offline):
    strategy, monitoring = modules["app.strategy"], modules["app.monitoring"]
    download = AsyncMock(return_value=True)
    monkeypatch.setattr(strategy, "download_file_with_retries", download)
    blacklist = AsyncMock(return_value=True)
    monkeypatch.setattr(strategy, "update_blacklist_if_needed", blacklist)
    send = AsyncMock()
    monkeypatch.setattr(monitoring, "send_telegram_message", send)
    result = offline.run_until_complete(monitoring.Monitor().force_download())
    assert result.status == "downloaded"
    download.assert_awaited_once()
    assert blacklist.call_args.kwargs["force"] is True
    send.assert_not_awaited()


def test_unknown_remote_version_does_not_write_or_reload(modules, monkeypatch, offline):
    strategy, monitoring = modules["app.strategy"], modules["app.monitoring"]
    monkeypatch.setattr(strategy, "check_remote_version", AsyncMock(return_value=None))
    download = AsyncMock()
    monkeypatch.setattr(strategy, "download_file_with_retries", download)
    result = offline.run_until_complete(monitoring.Monitor().check_for_updates())
    assert result.status == "failed"
    download.assert_not_awaited()


def test_corrupt_pending_marker_fails_closed(modules, offline):
    monitoring = modules["app.monitoring"]
    monitor = monitoring.Monitor()
    monitor.marker_path.write_text("corrupt", encoding="utf-8")
    assert offline.run_until_complete(monitoring.Monitor().check_for_updates()).status == "reload_pending"


def test_background_lifecycle_cancels_and_awaits_task(modules, monkeypatch, offline):
    main = modules["main"]
    started, stopped = asyncio.Event(), asyncio.Event()
    async def periodic(monitor):
        started.set()
        try:
            await asyncio.Future()
        finally:
            stopped.set()
    monkeypatch.setattr(main, "periodic_update_check", periodic)
    app = main.build_application()
    monkeypatch.setattr(main.Application, "start", AsyncMock())
    async def exercise():
        await main.on_startup(app)
        assert not started.is_set()
        await app.start()
        await started.wait()
        await main.on_shutdown(app)
        await main.on_shutdown(app)
        assert stopped.is_set()
        assert "monitor_task" not in app.bot_data
    offline.run_until_complete(exercise())


def test_exact_strategy_preserved_without_import():
    data = (APP / "Update" / "NostalgiaForInfinityX5.py").read_bytes().replace(b"\r\n", b"\n")
    assert len(data) == 1996706
    assert hashlib.sha256(data).hexdigest() == "5146f1e1e83921cd9f305888079d1d5f1a002ca0f0f62bcdbe2ceffc4e8c2850"


def test_run_polling_failure_finally_cancels_background(modules, monkeypatch, offline):
    main = modules["main"]
    periodic = AsyncMock()
    async def polling_failed(*args, **kwargs):
        await asyncio.sleep(0)
        raise RuntimeError("synthetic-startup-failure")
    monkeypatch.setattr(main, "periodic_update_check", periodic)
    app = main.build_application()
    monkeypatch.setattr(type(app), "initialize", AsyncMock())
    shutdown = AsyncMock()
    monkeypatch.setattr(type(app), "shutdown", shutdown)
    monkeypatch.setattr(type(app.updater), "start_polling", polling_failed)
    asyncio.set_event_loop(offline)
    try:
        with pytest.raises(RuntimeError, match="synthetic-startup-failure"):
            app.run_polling(close_loop=False, stop_signals=None)
    finally:
        asyncio.set_event_loop(None)
    periodic.assert_not_called()
    assert "monitor_task" not in app.bot_data
    shutdown.assert_awaited_once()


def test_failed_application_start_never_starts_monitor(modules, monkeypatch, offline):
    main = modules["main"]
    app = main.build_application()
    periodic = AsyncMock()
    monkeypatch.setattr(main, "periodic_update_check", periodic)
    monkeypatch.setattr(main.Application, "start", AsyncMock(side_effect=RuntimeError("startup failed")))
    async def exercise():
        await main.on_startup(app)
        with pytest.raises(RuntimeError):
            await app.start()
        await asyncio.sleep(0)
        await main.on_shutdown(app)
    offline.run_until_complete(exercise())
    periodic.assert_not_called()


def test_main_has_bounded_polling_bootstrap(modules, monkeypatch):
    app = SimpleNamespace(run_polling=Mock())
    monkeypatch.setattr(modules["main"], "build_application", Mock(return_value=app))
    modules["main"].main()
    app.run_polling.assert_called_once_with(bootstrap_retries=0)


def test_real_scheduled_success_clears_marker_once(modules, monkeypatch, offline):
    strategy, monitoring = modules["app.strategy"], modules["app.monitoring"]
    settings = modules["config.settings"]
    target = Path(settings.LOCAL_FILE_PATH)
    target.write_bytes(STRATEGY.replace(b"v1.2.3", b"v1.2.2"))
    session, _ = fake_http(monkeypatch, strategy, [Response(), Response(), Response()])
    send = AsyncMock(return_value=True)
    monkeypatch.setattr(monitoring, "send_telegram_message", send)
    monitor = monitoring.Monitor()
    result = offline.run_until_complete(monitor.check_for_updates())
    assert result.status == "command_delivered"
    assert target.read_bytes() == STRATEGY
    assert not monitor.marker_path.exists()
    assert offline.run_until_complete(monitor.check_for_updates()).status == "unchanged"
    send.assert_awaited_once_with(settings.FREQTRADE_BOT_TOKEN, settings.FREQTRADE_CHAT_ID, "/reload_config")
    assert session.get.call_count == 3


def test_marker_write_failure_prevents_publication(modules, monkeypatch, offline, caplog):
    strategy, monitoring = modules["app.strategy"], modules["app.monitoring"]
    target = Path(modules["config.settings"].LOCAL_FILE_PATH)
    target.write_bytes(b"original")
    fake_http(monkeypatch, strategy, [Response()])
    writer = Mock(side_effect=PermissionError("synthetic-secret"))
    monkeypatch.setattr(strategy, "atomic_write", writer)
    send = AsyncMock()
    monkeypatch.setattr(monitoring, "send_telegram_message", send)
    monitor = monitoring.Monitor()
    result = offline.run_until_complete(monitor.force_download())
    assert result.status == "failed"
    assert target.read_bytes() == b"original"
    assert writer.call_args.args[0] == monitor.marker_path
    send.assert_not_awaited()
    assert "synthetic-secret" not in caplog.text


@pytest.mark.parametrize("force", [False, True])
def test_real_blacklist_unchanged_does_not_rewrite(modules, monkeypatch, offline, tmp_path, force):
    strategy, settings = modules["app.strategy"], modules["config.settings"]
    target = tmp_path / "blacklist.json"
    data = b'{"pair_blacklist":["BTC/USDT"]}'
    target.write_bytes(data)
    monkeypatch.setattr(settings, "BLACKLIST_LOCAL_FILE_PATH", str(target))
    monkeypatch.setattr(settings, "BLACKLIST_FILE_URL", "https://raw.githubusercontent.com/example/strategy/main/blacklist.json")
    monkeypatch.setattr(settings, "BLACKLIST_REMOTE_FILE_PATH", "blacklist.json")
    session, _ = fake_http(monkeypatch, strategy, [Response(data)])
    before = Mock()
    assert offline.run_until_complete(strategy.update_blacklist_if_needed(force=force, before_replace=before)) is False
    before.assert_not_called()
    session.get.assert_called_once()


@pytest.mark.parametrize("data", [b"bad-json", b"42", b"[]\x00", b"<html>proxy-error</html>"])
def test_real_blacklist_invalid_content_preserves_file(modules, monkeypatch, offline, tmp_path, data):
    strategy, settings = modules["app.strategy"], modules["config.settings"]
    target = tmp_path / "blacklist.json"
    target.write_bytes(b"[]")
    monkeypatch.setattr(settings, "BLACKLIST_LOCAL_FILE_PATH", str(target))
    monkeypatch.setattr(settings, "BLACKLIST_FILE_URL", "https://raw.githubusercontent.com/example/strategy/main/blacklist.json")
    monkeypatch.setattr(settings, "BLACKLIST_REMOTE_FILE_PATH", "blacklist.json")
    fake_http(monkeypatch, strategy, [Response(data)])
    before = Mock()
    with pytest.raises(strategy.DownloadError):
        offline.run_until_complete(strategy.update_blacklist_if_needed(before_replace=before))
    assert target.read_bytes() == b"[]"
    before.assert_not_called()


def test_real_blacklist_changed_publishes_once(modules, monkeypatch, offline, tmp_path):
    strategy, settings = modules["app.strategy"], modules["config.settings"]
    target = tmp_path / "blacklist.json"
    monkeypatch.setattr(settings, "BLACKLIST_LOCAL_FILE_PATH", str(target))
    monkeypatch.setattr(settings, "BLACKLIST_FILE_URL", "https://raw.githubusercontent.com/example/strategy/main/blacklist.json")
    monkeypatch.setattr(settings, "BLACKLIST_REMOTE_FILE_PATH", "blacklist.json")
    fake_http(monkeypatch, strategy, [Response(b'{"pair_blacklist":[]}')])
    before = Mock()
    assert offline.run_until_complete(strategy.update_blacklist_if_needed(before_replace=before)) is True
    assert json.loads(target.read_bytes()) == {"pair_blacklist": []}
    before.assert_called_once()


def test_manual_and_scheduled_share_one_lock(modules, monkeypatch, offline):
    strategy, monitoring = modules["app.strategy"], modules["app.monitoring"]
    entered, release = asyncio.Event(), asyncio.Event()
    async def fetched(*args, **kwargs):
        entered.set()
        await release.wait()
        return STRATEGY
    fetch = AsyncMock(side_effect=fetched)
    monkeypatch.setattr(strategy, "fetch_bytes", fetch)
    send = AsyncMock(return_value=True)
    monkeypatch.setattr(monitoring, "send_telegram_message", send)
    monitor = monitoring.Monitor()
    async def exercise():
        manual = asyncio.create_task(monitor.force_download())
        await entered.wait()
        scheduled = asyncio.create_task(monitor.check_for_updates())
        await asyncio.sleep(0)
        assert not scheduled.done()
        assert fetch.await_count == 1
        release.set()
        assert (await manual).status == "downloaded"
        assert (await scheduled).status == "reload_pending"
    offline.run_until_complete(exercise())
    fetch.assert_awaited_once()
    send.assert_not_awaited()


def test_atomic_replace_failure_cleans_temporary(modules, monkeypatch, tmp_path):
    strategy = modules["app.strategy"]
    target = tmp_path / "target.py"
    target.write_bytes(b"original")
    monkeypatch.setattr(strategy.os, "replace", Mock(side_effect=OSError("replace failed")))
    with pytest.raises(OSError):
        strategy.atomic_write(target, STRATEGY)
    assert target.read_bytes() == b"original"
    assert list(tmp_path.glob("*.tmp")) == []


def test_download_size_limit_and_version_race_fail_closed(modules, monkeypatch, offline, tmp_path):
    strategy = modules["app.strategy"]
    target = tmp_path / "target.py"
    fake_http(monkeypatch, strategy, [Response()])
    with pytest.raises(strategy.DownloadError):
        offline.run_until_complete(strategy.download_file_with_retries(
            modules["config.settings"].FILE_URL, target, expected_version="v0.0.0"))
    assert not target.exists()
    monkeypatch.setattr(strategy, "MAX_DOWNLOAD_BYTES", 6)
    fake_http(monkeypatch, strategy, [Response()])
    with pytest.raises(strategy.DownloadError):
        offline.run_until_complete(strategy.download_file_with_retries(
            modules["config.settings"].FILE_URL, target, retries=1))
    assert not target.exists()


def test_marker_path_cannot_be_blacklist_destination(modules, monkeypatch):
    settings = modules["config.settings"]
    marker = Path(settings.LOCAL_FILE_PATH).parent / ".monitoring-reload-pending.json"
    monkeypatch.setattr(settings, "BLACKLIST_LOCAL_FILE_PATH", str(marker))
    monkeypatch.setattr(settings, "BLACKLIST_FILE_URL", "https://raw.githubusercontent.com/example/strategy/main/blacklist.json")
    monkeypatch.setattr(settings, "BLACKLIST_REMOTE_FILE_PATH", "blacklist.json")
    with pytest.raises(ValueError, match="BLACKLIST_LOCAL_FILE_PATH"):
        settings.validate_settings()


def test_notification_failure_never_repeats_reload(modules, monkeypatch, offline):
    monitoring = modules["app.monitoring"]
    checks = AsyncMock(side_effect=[monitoring.UpdateResult("command_delivered", ("strategy",)), monitoring.UpdateResult("unchanged")])
    monitor = SimpleNamespace(check_for_updates=checks)
    notify = AsyncMock(side_effect=RuntimeError("synthetic-secret"))
    monkeypatch.setattr(monitoring, "send_telegram_message", notify)
    sleeps = AsyncMock(side_effect=[None, asyncio.CancelledError()])
    monkeypatch.setattr(monitoring.asyncio, "sleep", sleeps)
    with pytest.raises(asyncio.CancelledError):
        offline.run_until_complete(monitoring.periodic_update_check(monitor))
    assert checks.await_count == 2
    notify.assert_awaited_once()
    assert notify.call_args.args[0] == modules["config.settings"].TELEGRAM_TOKEN


@pytest.mark.parametrize("local", [None, b"invalid local source", b"\xff"])
def test_unknown_local_version_requires_manual_bootstrap(modules, monkeypatch, offline, local):
    strategy, monitoring = modules["app.strategy"], modules["app.monitoring"]
    target = Path(modules["config.settings"].LOCAL_FILE_PATH)
    if local is None:
        target.unlink()
    else:
        target.write_bytes(local)
    remote = AsyncMock(return_value="v1.2.3")
    monkeypatch.setattr(strategy, "check_remote_version", remote)
    download = AsyncMock()
    monkeypatch.setattr(strategy, "download_file_with_retries", download)
    assert offline.run_until_complete(monitoring.Monitor().check_for_updates()).status == "failed"
    download.assert_not_awaited()


def test_marker_cleanup_failure_remains_pending_not_partial(modules, monkeypatch, offline):
    strategy, monitoring = modules["app.strategy"], modules["app.monitoring"]
    fake_http(monkeypatch, strategy, [Response(), Response()])
    monitor = monitoring.Monitor()
    original = Path.unlink
    def unlink(path, *args, **kwargs):
        if path == monitor.marker_path:
            raise PermissionError("marker cannot be removed")
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "unlink", unlink)
    send = AsyncMock(return_value=True)
    monkeypatch.setattr(monitoring, "send_telegram_message", send)
    assert offline.run_until_complete(monitor.check_for_updates()).status == "reload_pending"
    assert offline.run_until_complete(monitor.check_for_updates()).status == "reload_pending"
    send.assert_awaited_once()


@pytest.mark.parametrize("field", ["LOCAL_FILE_PATH", "BLACKLIST_LOCAL_FILE_PATH"])
def test_pending_marker_alias_respects_native_case_rules(modules, monkeypatch, field):
    settings = modules["config.settings"]
    alias = Path(settings.LOCAL_FILE_PATH).parent / ".MONITORING-RELOAD-PENDING.JSON"
    monkeypatch.setattr(settings, field, str(alias))
    if field == "BLACKLIST_LOCAL_FILE_PATH":
        monkeypatch.setattr(settings, "BLACKLIST_FILE_URL", "https://raw.githubusercontent.com/example/strategy/main/blacklist.json")
        monkeypatch.setattr(settings, "BLACKLIST_REMOTE_FILE_PATH", "blacklist.json")
    if os.name == "nt":
        with pytest.raises(ValueError, match=field):
            settings.validate_settings()
    else:
        settings.validate_settings()


def test_same_marker_basename_in_another_directory_does_not_collide(modules, monkeypatch, tmp_path):
    settings = modules["config.settings"]
    other = tmp_path / "other"
    other.mkdir()
    monkeypatch.setattr(settings, "BLACKLIST_LOCAL_FILE_PATH", str(other / ".monitoring-reload-pending.json"))
    monkeypatch.setattr(settings, "BLACKLIST_FILE_URL", "https://raw.githubusercontent.com/example/strategy/main/blacklist.json")
    monkeypatch.setattr(settings, "BLACKLIST_REMOTE_FILE_PATH", "blacklist.json")
    settings.validate_settings()
