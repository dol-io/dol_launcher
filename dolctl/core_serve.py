from __future__ import annotations

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .infra_net import find_available_port, is_port_available
from .models import DolCtlError


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


def create_server(
    directory: Path,
    host: str = "127.0.0.1",
    port: int = 8799,
    allow_fallback: bool = False,
) -> tuple[ThreadingHTTPServer, int]:
    if allow_fallback:
        chosen = find_available_port(host, port)
        if chosen is None:
            raise DolCtlError("No available port found")
    else:
        if not is_port_available(host, port):
            raise DolCtlError(f"Port is already in use: {port}")
        chosen = port
    handler = partial(QuietHandler, directory=str(directory))
    server = ThreadingHTTPServer((host, chosen), handler)
    return server, chosen
