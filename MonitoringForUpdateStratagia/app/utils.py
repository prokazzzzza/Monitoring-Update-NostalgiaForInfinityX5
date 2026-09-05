import re
from pathlib import Path

from config import settings


def text(russian: str, english: str) -> str:
    return english if settings.LANGUAGE == "ENG" else russian


def extract_version_from_content(content: str | None) -> str | None:
    if not isinstance(content, str):
        return None
    match = re.search(r"return\s+['\"](v[0-9]+(?:\.[0-9]+)+)['\"]", content)
    return match.group(1) if match else None


def extract_version_from_file(path: str | Path) -> str | None:
    try:
        return extract_version_from_content(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError):
        return None


def format_time_interval(seconds: int | str) -> str:
    hours, remaining = divmod(int(seconds), 3600)
    minutes, seconds = divmod(remaining, 60)
    return text(f"{hours} ч. {minutes} мин. {seconds} сек.", f"{hours} h {minutes} min {seconds} sec")
