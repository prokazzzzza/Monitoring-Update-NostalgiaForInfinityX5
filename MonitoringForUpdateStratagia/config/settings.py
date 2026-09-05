import os
import re
from pathlib import Path
from urllib.parse import urlsplit

import pytz
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
CHAT_ID = os.getenv("CHAT_ID", "")
FREQTRADE_BOT_TOKEN = os.getenv("FREQTRADE_BOT_TOKEN", "")
FREQTRADE_CHAT_ID = os.getenv("FREQTRADE_CHAT_ID") or CHAT_ID
FILE_URL = os.getenv("FILE_URL", "")
LOCAL_FILE_PATH = os.getenv("LOCAL_FILE_PATH", "")
CHECK_INTERVAL = os.getenv("CHECK_INTERVAL", "3600")
RETRY_LIMIT = os.getenv("RETRY_LIMIT", "3")
RETRY_DELAY = os.getenv("RETRY_DELAY", "5")
REPO_URL = os.getenv("REPO_URL", "")
REMOTE_FILE_PATH = os.getenv("REMOTE_FILE_PATH", "")
BLACKLIST_FILE_URL = os.getenv("BLACKLIST_FILE_URL", "")
BLACKLIST_LOCAL_FILE_PATH = os.getenv("BLACKLIST_LOCAL_FILE_PATH", "")
BLACKLIST_REMOTE_FILE_PATH = os.getenv("BLACKLIST_REMOTE_FILE_PATH", "")
TIMEZONE = os.getenv("TIMEZONE", "UTC")
LANGUAGE = os.getenv("LANGUAGE", "RU").upper()
BOT_VERSION = "v1.16.1"


def trusted_download_url(value: str) -> bool:
    try:
        url = urlsplit(value)
        return (
            url.scheme == "https" and url.netloc == "raw.githubusercontent.com"
            and bool(url.path.strip("/")) and not url.query and not url.fragment
        )
    except ValueError:
        return False


def valid_remote_path(value: str) -> bool:
    return bool(
        value and re.fullmatch(r"[\w./@-]+", value, flags=re.ASCII)
        and not value.startswith("/") and all(p not in ("", ".", "..") for p in value.split("/"))
    )


def is_blacklist_configured() -> bool:
    return all((BLACKLIST_FILE_URL, BLACKLIST_LOCAL_FILE_PATH, BLACKLIST_REMOTE_FILE_PATH))


def validate_settings() -> None:
    """Report field names only; configuration values can contain credentials."""
    errors = []
    for name in ("TELEGRAM_TOKEN", "FREQTRADE_BOT_TOKEN"):
        if not re.fullmatch(r"[0-9]+:[A-Za-z0-9_-]+", globals()[name]):
            errors.append(name)
    for name in ("CHAT_ID", "FREQTRADE_CHAT_ID"):
        if not re.fullmatch(r"-?[1-9][0-9]*", str(globals()[name])):
            errors.append(name)
    for name, maximum in (("CHECK_INTERVAL", 604800), ("RETRY_LIMIT", 10), ("RETRY_DELAY", 3600)):
        try:
            value = int(globals()[name])
            if not 1 <= value <= maximum:
                raise ValueError
        except (ValueError, TypeError):
            errors.append(name)
    if LANGUAGE not in ("RU", "ENG"):
        errors.append("LANGUAGE")
    if TIMEZONE not in pytz.all_timezones_set:
        errors.append("TIMEZONE")
    if not re.fullmatch(r"[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+", REPO_URL):
        errors.append("REPO_URL")
    if not valid_remote_path(REMOTE_FILE_PATH):
        errors.append("REMOTE_FILE_PATH")
    urls = ["FILE_URL"]
    paths = ["LOCAL_FILE_PATH"]
    blacklist_fields = ("BLACKLIST_FILE_URL", "BLACKLIST_LOCAL_FILE_PATH", "BLACKLIST_REMOTE_FILE_PATH")
    if any(globals()[field] for field in blacklist_fields):
        if not is_blacklist_configured():
            errors.extend(blacklist_fields)
        else:
            urls.append("BLACKLIST_FILE_URL")
            paths.append("BLACKLIST_LOCAL_FILE_PATH")
            if not valid_remote_path(BLACKLIST_REMOTE_FILE_PATH):
                errors.append("BLACKLIST_REMOTE_FILE_PATH")
    for name in urls:
        if not trusted_download_url(globals()[name]):
            errors.append(name)
    resolved: list[Path] = []
    for name in paths:
        try:
            value = globals()[name]
            path = Path(value)
            if not value or not path.parent.is_dir() or path.is_dir() or path.is_symlink():
                raise ValueError
            resolved.append(path.resolve())
            marker_path = Path(LOCAL_FILE_PATH).parent / ".monitoring-reload-pending.json"
            if path.resolve() == marker_path.resolve():
                errors.append(name)
        except (ValueError, OSError):
            errors.append(name)
    if len(resolved) > 1 and resolved[0] == resolved[1]:
        errors.append("BLACKLIST_LOCAL_FILE_PATH")
    if errors:
        raise ValueError("Invalid settings: " + ", ".join(sorted(set(errors))))
