"""
downloader.py - HTTP package download with SHA-256 integrity verification.

Features:
  - Streaming download (does not load entire file into RAM)
  - Incremental SHA-256 verification
  - Resume support via HTTP Range header for partial downloads
  - Retry with exponential backoff
"""

import hashlib
import logging
import time
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlparse

import requests

from config import AgentConfig

logger = logging.getLogger(__name__)


class DownloadError(Exception):
    pass


class ChecksumError(DownloadError):
    pass


class PackageDownloader:
    def __init__(self, config: AgentConfig) -> None:
        self._config = config
        Path(config.download_dir).mkdir(parents=True, exist_ok=True)

    def download(
        self,
        url: str,
        expected_sha256: str,
        progress_cb: Optional[Callable[[int, int], None]] = None,
    ) -> Path:
        """
        Download package from url, verify SHA-256, return local path.

        progress_cb(bytes_downloaded, total_bytes) is called after each chunk.
        Raises DownloadError or ChecksumError on failure.
        """
        filename = _filename_from_url(url)
        local_path = Path(self._config.download_dir) / filename

        def attempt() -> Path:
            return self._download_with_resume(url, local_path, expected_sha256, progress_cb)

        return self._with_retry(attempt, self._config.max_retries, self._config.retry_delay_seconds)

    def cleanup(self, path: Optional[Path]) -> None:
        if path and path.exists():
            path.unlink()
            logger.debug("Cleaned up %s", path)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _download_with_resume(
        self,
        url: str,
        local_path: Path,
        expected_sha256: str,
        progress_cb: Optional[Callable],
    ) -> Path:
        existing_size = local_path.stat().st_size if local_path.exists() else 0
        headers = {}
        if existing_size > 0:
            headers["Range"] = f"bytes={existing_size}-"
            logger.info("Resuming download from byte %d: %s", existing_size, url)
        else:
            logger.info("Starting download: %s", url)

        try:
            response = requests.get(url, headers=headers, stream=True, timeout=30)
        except requests.RequestException as e:
            raise DownloadError(f"HTTP request failed: {e}") from e

        # 206 = partial content (resume), 200 = full download
        if response.status_code == 416:
            # Server says range not satisfiable — file already complete, just verify
            logger.info("Server returned 416: file may already be complete, verifying...")
            return self._verify_checksum(local_path, expected_sha256)

        if response.status_code not in (200, 206):
            raise DownloadError(f"HTTP {response.status_code} for {url}")

        resuming = response.status_code == 206
        total_size = _parse_total_size(response, existing_size, resuming)

        hasher = hashlib.sha256()
        if resuming and existing_size > 0:
            # Hash what we already have before appending
            with open(local_path, "rb") as f:
                while chunk := f.read(self._config.download_chunk_size_bytes):
                    hasher.update(chunk)

        mode = "ab" if resuming else "wb"
        downloaded = existing_size if resuming else 0

        with open(local_path, mode) as f:
            for chunk in response.iter_content(chunk_size=self._config.download_chunk_size_bytes):
                if chunk:
                    f.write(chunk)
                    hasher.update(chunk)
                    downloaded += len(chunk)
                    if progress_cb and total_size:
                        progress_cb(downloaded, total_size)

        logger.info("Download complete: %d bytes", downloaded)
        actual = hasher.hexdigest()
        if actual != expected_sha256:
            local_path.unlink(missing_ok=True)
            raise ChecksumError(
                f"SHA-256 mismatch: expected {expected_sha256}, got {actual}. "
                "File deleted, will retry from scratch."
            )
        logger.info("SHA-256 verified OK: %s", actual)
        return local_path

    def _verify_checksum(self, path: Path, expected_sha256: str) -> Path:
        hasher = hashlib.sha256()
        with open(path, "rb") as f:
            while chunk := f.read(self._config.download_chunk_size_bytes):
                hasher.update(chunk)
        actual = hasher.hexdigest()
        if actual != expected_sha256:
            raise ChecksumError(f"SHA-256 mismatch for existing file: expected {expected_sha256}, got {actual}")
        logger.info("Existing file SHA-256 OK: %s", actual)
        return path

    def _with_retry(self, fn: Callable, max_retries: int, delay: float):
        last_error = None
        for attempt in range(1, max_retries + 1):
            try:
                return fn()
            except ChecksumError as e:
                # Checksum errors: file is corrupt, retry from scratch (no resume)
                logger.warning("Checksum error (attempt %d/%d): %s", attempt, max_retries, e)
                last_error = e
            except DownloadError as e:
                logger.warning("Download error (attempt %d/%d): %s", attempt, max_retries, e)
                last_error = e
            if attempt < max_retries:
                backoff = delay * (2 ** (attempt - 1))
                logger.info("Retrying in %.1fs...", backoff)
                time.sleep(backoff)
        raise DownloadError(f"Failed after {max_retries} attempts") from last_error


def _filename_from_url(url: str) -> str:
    return Path(urlparse(url).path).name or "package.swu"


def _parse_total_size(response: requests.Response, existing_size: int, resuming: bool) -> Optional[int]:
    content_length = response.headers.get("Content-Length")
    if content_length is None:
        return None
    chunk_size = int(content_length)
    return (existing_size + chunk_size) if resuming else chunk_size
