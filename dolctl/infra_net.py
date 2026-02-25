from __future__ import annotations

from pathlib import Path
import hashlib
import socket
from typing import Any
from urllib.parse import urlparse

import httpx


def is_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"}


def fetch_json(url: str, headers: dict[str, str] | None = None, timeout: float = 30.0) -> Any:
    with httpx.Client(timeout=timeout, headers=headers) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.json()


def download_file(
    url: str,
    dest: Path,
    headers: dict[str, str] | None = None,
    timeout: float = 60.0,
) -> str:
    dest.parent.mkdir(parents=True, exist_ok=True)
    hasher = hashlib.sha256()
    with httpx.Client(timeout=timeout, headers=headers, follow_redirects=True) as client:
        with client.stream("GET", url) as response:
            response.raise_for_status()
            with dest.open("wb") as handle:
                for chunk in response.iter_bytes():
                    if not chunk:
                        continue
                    handle.write(chunk)
                    hasher.update(chunk)
    return hasher.hexdigest()


def is_port_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def find_available_port(host: str, start_port: int, max_tries: int = 50) -> int | None:
    for offset in range(max_tries):
        port = start_port + offset
        if is_port_available(host, port):
            return port
    return None
