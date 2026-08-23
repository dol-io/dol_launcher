from __future__ import annotations

from dataclasses import dataclass, field
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
from urllib.parse import quote

from .models import ConflictError, ValidationError
from .root import validate_port, validate_resource_name


_LOCAL_ADDRESSES = frozenset({"127.0.0.1", "::1"})


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class _GameHandler(SimpleHTTPRequestHandler):
    entry_name: str
    allow_lan: bool

    def _is_allowed(self) -> bool:
        if self.allow_lan or self.client_address[0] in _LOCAL_ADDRESSES:
            return True
        self.send_error(403, "LAN access is disabled")
        return False

    def do_GET(self) -> None:  # noqa: N802
        if self._is_allowed():
            super().do_GET()

    def do_HEAD(self) -> None:  # noqa: N802
        if self._is_allowed():
            super().do_HEAD()

    def translate_path(self, path: str) -> str:
        if path in {"", "/"}:
            path = "/" + quote(self.entry_name)
        return super().translate_path(path)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return


def _build_handler_class(entry_name: str, allow_lan: bool) -> type[_GameHandler]:
    return type(
        "ConfiguredGameHandler",
        (_GameHandler,),
        {"entry_name": entry_name, "allow_lan": allow_lan},
    )


@dataclass(slots=True)
class ServerHandle:
    server: ThreadingHTTPServer
    host: str
    port: int
    directory: Path
    entry: str
    _thread: threading.Thread | None = field(default=None, init=False, repr=False)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/"

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            raise ConflictError("Server is already running")
        self._thread = threading.Thread(
            target=self.server.serve_forever,
            name=f"dolctl-http-{self.port}",
            daemon=True,
        )
        self._thread.start()

    def serve_forever(self) -> None:
        self.server.serve_forever()

    def close(self) -> None:
        self.server.server_close()

    def stop(self) -> None:
        thread = self._thread
        if thread is not None and thread.is_alive():
            self.server.shutdown()
            thread.join(timeout=5)
        self._thread = None
        self.server.server_close()


def create_server(
    directory: Path,
    *,
    host: str = "127.0.0.1",
    port: int = 8799,
    allow_fallback: bool = False,
    entry_name: str = "index.html",
    allow_lan: bool = False,
) -> ServerHandle:
    directory = directory.expanduser().resolve()
    if not directory.is_dir():
        raise ValidationError(f"Server directory does not exist: {directory}")
    entry_name = validate_resource_name(entry_name, "entry HTML")
    if not (directory / entry_name).is_file():
        raise ValidationError(f"Entry HTML does not exist: {entry_name}")
    validate_port(port)

    handler_class = _build_handler_class(entry_name, allow_lan)
    handler = partial(handler_class, directory=str(directory))
    ports = range(port, min(65536, port + 50)) if allow_fallback else (port,)
    last_error: OSError | None = None
    for candidate in ports:
        try:
            server = _Server((host, candidate), handler)
        except OSError as exc:
            last_error = exc
            continue
        return ServerHandle(server, host, candidate, directory, entry_name)

    if allow_fallback:
        raise ConflictError(f"No available port found from {port}") from last_error
    raise ConflictError(f"Port is already in use: {port}") from last_error
