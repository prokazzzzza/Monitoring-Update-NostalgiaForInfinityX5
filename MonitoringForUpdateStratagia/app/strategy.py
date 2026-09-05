import ast
import asyncio
import json
import os
import stat
import tempfile
from collections.abc import Callable
from pathlib import Path
from urllib.parse import quote

import aiohttp
from config import settings
from config.logging_config import logger

from app.utils import extract_version_from_content

MAX_DOWNLOAD_BYTES = 8 * 1024 * 1024


class DownloadError(Exception):
    """Safe download error; never contains response bodies, URLs or credentials."""


def raw_file_url(repo_url: str, file_path: str) -> str:
    if repo_url != settings.REPO_URL or not settings.valid_remote_path(file_path):
        raise DownloadError("Invalid remote path")
    return f"https://raw.githubusercontent.com/{repo_url}/main/{quote(file_path, safe='/')}"


async def fetch_bytes(
    url: str, retries: int | None = None, delay: int | None = None, *, api: bool = False,
) -> bytes:
    trusted = url.startswith("https://api.github.com/repos/") if api else settings.trusted_download_url(url)
    if not trusted:
        raise DownloadError("Untrusted download URL")
    retries = int(settings.RETRY_LIMIT) if retries is None else retries
    delay = int(settings.RETRY_DELAY) if delay is None else delay
    if not 1 <= retries <= 10 or not 0 <= delay <= 3600:
        raise DownloadError("Invalid retry settings")
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30), trust_env=False) as session:
        for attempt in range(retries):
            try:
                async with session.get(url, allow_redirects=False) as response:
                    if response.status != 200:
                        raise DownloadError("Unexpected download status")
                    data = bytearray()
                    async for chunk in response.content.iter_chunked(65536):
                        if len(data) + len(chunk) > MAX_DOWNLOAD_BYTES:
                            raise DownloadError("Download exceeds size limit")
                        data.extend(chunk)
                    return bytes(data)
            except (aiohttp.ClientError, OSError, TimeoutError, DownloadError):
                logger.warning("Download attempt failed")
                if attempt + 1 < retries:
                    await asyncio.sleep(delay)
    raise DownloadError("Download failed") from None


def validate_content(
    data: bytes, *, blacklist: bool = False, path: str | Path | None = None,
    expected_version: str | None = None,
) -> str:
    try:
        content = data.decode("utf-8-sig")
        if not content.strip() or "\x00" in content:
            raise ValueError
        if blacklist:
            if content.lstrip().startswith("<"):
                raise ValueError
            if path and Path(path).suffix.lower() == ".json":
                if not isinstance(json.loads(content), (dict, list)):
                    raise ValueError
        else:
            version = extract_version_from_content(content)
            if not version or (expected_version and version != expected_version):
                raise ValueError
            ast.parse(content)
        return content
    except (ValueError, UnicodeError, SyntaxError):
        raise DownloadError("Invalid downloaded content") from None


def atomic_write(path: str | Path, data: bytes) -> None:
    """Write in the same directory; never truncate the previous destination."""
    path = Path(path)
    if path.is_symlink():
        raise DownloadError("Invalid destination")
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        if path.exists():
            os.chmod(temporary, stat.S_IMODE(path.stat().st_mode))
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


async def download_file_with_retries(
    url: str, save_path: str | Path, retries: int | None = None, delay: int | None = None, *,
    blacklist: bool = False, expected_version: str | None = None,
    before_replace: Callable[[], None] | None = None,
) -> bool:
    data = await fetch_bytes(url, retries, delay)
    validate_content(data, blacklist=blacklist, path=save_path, expected_version=expected_version)
    path = Path(save_path)
    if path.is_file() and path.read_bytes() == data:
        return False
    if before_replace:
        before_replace()
    atomic_write(path, data)
    return True


async def fetch_file_content(repo_url: str, file_path: str) -> str | None:
    try:
        return (await fetch_bytes(raw_file_url(repo_url, file_path))).decode("utf-8-sig")
    except (DownloadError, UnicodeError):
        logger.warning("Remote content unavailable")
        return None


async def check_remote_version() -> str | None:
    content = await fetch_file_content(settings.REPO_URL, settings.REMOTE_FILE_PATH)
    return extract_version_from_content(content)


async def update_blacklist_if_needed(
    force: bool = False, *, before_replace: Callable[[], None] | None = None,
) -> bool:
    if not settings.is_blacklist_configured():
        return False
    # Fetch the final content once, then compare, validate and publish those same bytes.
    # BLACKLIST_REMOTE_FILE_PATH remains required for legacy configuration parity.
    return await download_file_with_retries(
        settings.BLACKLIST_FILE_URL, settings.BLACKLIST_LOCAL_FILE_PATH,
        blacklist=True, before_replace=before_replace,
    )
