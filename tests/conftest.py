import asyncio
import importlib
import socket
import sys
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / "MonitoringForUpdateStratagia"
sys.path.insert(0, str(APP))


@pytest.fixture(autouse=True)
def offline(monkeypatch, tmp_path):
    # Construct the event loop before blocking Windows' local socketpair setup.
    loop = asyncio.new_event_loop()

    def blocked(*args, **kwargs):
        raise AssertionError("Network is disabled in offline tests")

    for name in ("connect", "connect_ex", "sendto"):
        monkeypatch.setattr(socket.socket, name, blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    for key in (
        "BLACKLIST_FILE_URL", "BLACKLIST_LOCAL_FILE_PATH", "BLACKLIST_REMOTE_FILE_PATH",
        "FREQTRADE_CHAT_ID", "LOCAL_VOLUME_PATH",
    ):
        monkeypatch.delenv(key, raising=False)
    for key, value in {
        "TELEGRAM_TOKEN": "123456:offline-monitor-token",
        "FREQTRADE_BOT_TOKEN": "654321:offline-freqtrade-token",
        "CHAT_ID": "123", "CHECK_INTERVAL": "60", "RETRY_LIMIT": "2",
        "RETRY_DELAY": "1", "REPO_URL": "example/strategy",
        "REMOTE_FILE_PATH": "Strategy.py",
        "FILE_URL": "https://raw.githubusercontent.com/example/strategy/main/Strategy.py",
        "LOCAL_FILE_PATH": str(tmp_path / "Strategy.py"),
        "TIMEZONE": "UTC", "LANGUAGE": "RU", "PYTHON_DOTENV_DISABLED": "1",
    }.items():
        monkeypatch.setenv(key, value)
    (tmp_path / "Strategy.py").write_bytes(b"class Strategy:\n    def version(self):\n        return 'v1.2.2'\n")
    # Re-import actual source per test: no settings, locks or tasks leak between tests.
    for name in list(sys.modules):
        if name in ("app", "config", "main") or name.startswith(("app.", "config.")):
            monkeypatch.delitem(sys.modules, name)
    yield loop
    pending = asyncio.all_tasks(loop)
    for task in pending:
        task.cancel()
    if pending:
        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
    loop.close()


@pytest.fixture
def modules():
    return {
        name: importlib.import_module(name)
        for name in ("config.settings", "app.utils", "app.strategy", "app.monitoring", "app.handlers", "main")
    }
