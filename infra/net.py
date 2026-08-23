from __future__ import annotations

import hashlib
import os
from pathlib import Path
import socket
from typing import Any, Callable
from urllib.parse import urlparse

import httpx


ProgressCallback = Callable[[int, int | None], None]


_USER_AGENT = "dolctl/0.2"


def is_url(value: str) -> bool:
    return urlparse(value).scheme.lower() in {"http", "https"}


def fetch_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 30.0,
) -> Any:
    request_headers = {"User-Agent": _USER_AGENT, **(headers or {})}
    with httpx.Client(
        timeout=timeout,
        headers=request_headers,
        follow_redirects=True,
    ) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.json()


def download_file(
    url: str,
    destination: Path,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 60.0,
    progress: ProgressCallback | None = None,
    expected_sha256: str | None = None,
) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(f"{destination.name}.part")
    request_headers = {"User-Agent": _USER_AGENT, **(headers or {})}
    digest = hashlib.sha256()
    downloaded = 0
    try:
        with httpx.Client(
            timeout=timeout,
            headers=request_headers,
            follow_redirects=True,
        ) as client:
            with client.stream("GET", url) as response:
                response.raise_for_status()
                header = response.headers.get("content-length", "")
                total = int(header) if header.isdigit() else None
                with partial.open("wb") as handle:
                    for chunk in response.iter_bytes():
                        if not chunk:
                            continue
                        handle.write(chunk)
                        digest.update(chunk)
                        downloaded += len(chunk)
                        if progress is not None:
                            progress(downloaded, total)
                    handle.flush()
                    os.fsync(handle.fileno())
        actual_sha256 = digest.hexdigest()
        if expected_sha256 and actual_sha256.lower() != expected_sha256.lower():
            raise ValueError(
                "Downloaded file checksum mismatch: "
                f"expected {expected_sha256}, got {actual_sha256}"
            )
        os.replace(partial, destination)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    return actual_sha256


def is_port_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def find_available_port(host: str, start_port: int, max_tries: int = 50) -> int | None:
    for port in range(start_port, min(65536, start_port + max_tries)):
        if is_port_available(host, port):
            return port
    return None
